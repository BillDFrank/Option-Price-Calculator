# app.py
from flask import Flask, render_template_string, request, redirect, url_for, flash
import math, datetime, uuid
import plotly.graph_objs as go
import plotly.offline as pyo
from scipy.stats import norm

app = Flask(__name__)
app.secret_key = 'your_generated_secret_key'  # Replace with a securely generated key

# Global dictionary for saving scenarios (in‐memory, not persistent)
SCENARIOS = {}

# Helper functions for Black–Scholes

def black_scholes_price(option_type, S, K, T, r, sigma):
    """Compute the Black–Scholes option price for a call or put."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S/K) + (r + sigma**2/2)*T) / (sigma*math.sqrt(T))
    d2 = d1 - sigma*math.sqrt(T)
    if option_type.lower() == 'call':
        price = S * norm.cdf(d1) - K * math.exp(-r*T) * norm.cdf(d2)
    else:  # put
        price = K * math.exp(-r*T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return price

def compute_implied_volatility(option_type, S, K, T, r, market_price, tol=1e-6, max_iter=100):
    """Compute implied volatility using Newton–Raphson."""
    sigma = 0.2  # initial guess
    for i in range(max_iter):
        price = black_scholes_price(option_type, S, K, T, r, sigma)
        d1 = (math.log(S/K) + (r + sigma**2/2)*T) / (sigma*math.sqrt(T))
        vega = S * norm.pdf(d1) * math.sqrt(T)
        if vega == 0:
            break
        diff = price - market_price
        if abs(diff) < tol:
            return sigma
        sigma = sigma - diff/vega
    return sigma

def compute_implied_stock(option_type, S_guess, K, T, r, sigma, market_price, tol=1e-6, max_iter=100):
    """Compute implied underlying stock price (solve for S) using Newton–Raphson.
       Note: This is not standard but can be computed numerically."""
    S = S_guess
    for i in range(max_iter):
        price = black_scholes_price(option_type, S, K, T, r, sigma)
        # Derivative with respect to S is Delta
        d1 = (math.log(S/K) + (r + sigma**2/2)*T) / (sigma*math.sqrt(T))
        if option_type.lower() == 'call':
            delta = norm.cdf(d1)
        else:
            delta = norm.cdf(d1) - 1
        if abs(delta) < 1e-6:
            break
        diff = price - market_price
        if abs(diff) < tol:
            return S
        S = S - diff/delta
    return S

def compute_greeks(option_type, S, K, T, r, sigma):
    """Compute the Black–Scholes Greeks: Delta, Gamma, Vega, Theta, and Rho."""
    d1 = (math.log(S/K) + (r + sigma**2/2)*T) / (sigma*math.sqrt(T))
    d2 = d1 - sigma*math.sqrt(T)
    delta = norm.cdf(d1) if option_type.lower()=='call' else norm.cdf(d1) - 1
    gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
    vega = S * norm.pdf(d1) * math.sqrt(T)
    if option_type.lower() == 'call':
        theta = (-S * norm.pdf(d1)*sigma/(2*math.sqrt(T)) 
                 - r*K*math.exp(-r*T)*norm.cdf(d2))
        rho = K*T*math.exp(-r*T)*norm.cdf(d2)
    else:
        theta = (-S * norm.pdf(d1)*sigma/(2*math.sqrt(T)) 
                 + r*K*math.exp(-r*T)*norm.cdf(-d2))
        rho = -K*T*math.exp(-r*T)*norm.cdf(-d2)
    return {
        'Delta': delta,
        'Gamma': gamma,
        'Vega': vega,
        'Theta': theta,
        'Rho': rho
    }

# The HTML template using Materialize CSS.
# It uses a navbar at the top; on the left are the inputs, and on the right the results and graphs.
# The mandatory fields always show with a red border until filled.
# In the optional section (Volatility, Stock Price, Option Price), the empty field turns green
# when exactly one of them is empty. (The calculated value is then inserted in that field.)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8">
    <title>Stock Option Price Calculator</title>
    <!-- Materialize CSS and Material Icons -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/css/materialize.min.css">
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    <style>
      html, body {
        margin: 0;
        padding: 0;
      }
      body {
        padding-top: 0;
      }
      nav {
        margin-bottom: 0;
      }
      .dark-mode {
        background-color: #424242 !important;
        color: #fff !important;
      }
      .dark-mode .card, .dark-mode .card-content, .dark-mode .card-title, .dark-mode label, .dark-mode p {
        color: #fff !important;
      }
      .red-border input:not([readonly]),
      .red-border textarea:not([readonly]) {
        border-bottom: 2px solid red !important;
        box-shadow: 0 1px 0 0 red !important;
      }
      .green-border input:not([readonly]),
      .green-border textarea:not([readonly]) {
        border-bottom: 2px solid green !important;
        box-shadow: 0 1px 0 0 green !important;
      }
      .input-field label.active {
        color: #000;
      }
      /* Ensure calendar (datepicker) input shows properly */
      .datepicker-modal { z-index: 10000; }
      .results-card { margin-bottom: 15px; }
      .toggle-table { margin-bottom: 15px; }
    </style>
  </head>
  <body id="body">
    <!-- Navbar -->
    <nav class="blue">
      <div class="nav-wrapper container">
        <a href="#" class="brand-logo">Option Price Calculator</a>
        <ul id="nav-mobile" class="right">
          <li><a href="#" onclick="toggleDarkMode()"><i class="material-icons">brightness_6</i></a></li>
        </ul>
      </div>
    </nav>
    
    <div class="container">
      {% with messages = get_flashed_messages() %}
        {% if messages %}
          <div class="card-panel red lighten-2">
            <ul>
              {% for msg in messages %}
                <li>{{ msg }}</li>
              {% endfor %}
            </ul>
          </div>
        {% endif %}
      {% endwith %}
      
      <div class="row">
        <!-- Left Column: Inputs -->
        <div class="col s12 m6">
          <div class="card">
            <div class="card-content">
              <span class="card-title">Input Parameters</span>
              <form method="POST" action="{{ url_for('index') }}">
                <!-- Mandatory fields -->
                <div class="row">
                  <!-- Option Type -->
                  <div class="input-field col s12">
                    <select name="option_type" id="option_type">
                      <option value="" disabled {% if not scenario.option_type %}selected{% endif %}>Choose your option</option>
                      <option value="call" {% if scenario.option_type=='call' %}selected{% endif %}>Call</option>
                      <option value="put" {% if scenario.option_type=='put' %}selected{% endif %}>Put</option>
                    </select>
                    <label>Option Type *</label>
                  </div>
                  <!-- Underlying Price (mandatory) -->
                  <div class="input-field col s12 red-border">
                    <input id="underlying_price" type="number" step="0.01" name="underlying_price" value="{{ scenario.underlying_price if scenario.underlying_price is not none else '' }}">
                    <label for="underlying_price" class="{% if scenario.underlying_price %}active{% endif %}">Underlying Price *</label>
                  </div>
                  <!-- Strike Price -->
                  <div class="input-field col s12 red-border">
                    <input id="strike_price" type="number" step="0.01" name="strike_price" value="{{ scenario.strike_price if scenario.strike_price is not none else '' }}">
                    <label for="strike_price" class="{% if scenario.strike_price %}active{% endif %}">Strike Price *</label>
                  </div>
                  <!-- Expiration Date (calendar) -->
                  <div class="input-field col s12 red-border">
                    <input id="expiration_date" type="text" class="datepicker" name="expiration_date" value="{{ scenario.expiration_date if scenario.expiration_date is not none else '' }}">
                    <label for="expiration_date" class="{% if scenario.expiration_date %}active{% endif %}">Expiration Date *</label>
                  </div>
                  <!-- Risk-free Rate -->
                  <div class="input-field col s12 red-border">
                    <input id="risk_free_rate" type="number" step="0.01" name="risk_free_rate" value="{{ scenario.risk_free_rate if scenario.risk_free_rate is not none else '' }}">
                    <label for="risk_free_rate" class="{% if scenario.risk_free_rate %}active{% endif %}">Risk-Free Rate (%) *</label>
                  </div>
                </div>
                <div class="divider"></div>
                <!-- Optional fields (option fields) -->
                <div class="row">
                  <p>Fill exactly two of the following (they are optional) and leave one blank to calculate it. The empty field will be highlighted in green when ready for calculation.</p>
                  <!-- Volatility -->
                  <div class="input-field col s12 {% if option_field_status.volatility %}{{ 'red-border' if option_field_status.volatility=='red' else 'green-border' }}{% endif %}">
                    <input id="volatility" type="number" step="0.01" name="volatility" value="{{ scenario.volatility if scenario.volatility is not none else '' }}">
                    <label for="volatility" class="{% if scenario.volatility %}active{% endif %}">Volatility (%)</label>
                  </div>
                  <!-- Stock Price (optional override; if blank, use mandatory Underlying Price) -->
                  <div class="input-field col s12 {% if option_field_status.stock_price %}{{ 'red-border' if option_field_status.stock_price=='red' else 'green-border' }}{% endif %}">
                    <input id="stock_price" type="number" step="0.01" name="stock_price" value="{{ scenario.stock_price if scenario.stock_price is not none else '' }}">
                    <label for="stock_price" class="{% if scenario.stock_price %}active{% endif %}">Stock Price (for calculation)</label>
                  </div>
                  <!-- Option Price -->
                  <div class="input-field col s12 {% if option_field_status.option_price %}{{ 'red-border' if option_field_status.option_price=='red' else 'green-border' }}{% endif %}">
                    <input id="option_price" type="number" step="0.01" name="option_price" value="{{ scenario.option_price if scenario.option_price is not none else '' }}">
                    <label for="option_price" class="{% if scenario.option_price %}active{% endif %}">Option Price</label>
                  </div>
                </div>
                <div class="row">
                  <div class="col s12">
                    <button class="btn waves-effect waves-light" type="submit" name="action" value="calculate">Calculate Option Variable</button>
                  </div>
                </div>
              </form>
            </div>
          </div>
        </div>
        
        <!-- Right Column: Results, Greeks and Graphs -->
        <div class="col s12 m6">
          {% if results %}
          <div class="card results-card">
            <div class="card-content">
              <span class="card-title">Calculated Optional Field</span>
              <p>The missing field has been computed and is shown below (highlighted in green):</p>
              <ul>
                {% if computed_field == 'volatility' %}
                  <li><strong>Volatility:</strong> {{ results.computed_value*100|round(2) }} %</li>
                {% elif computed_field == 'stock_price' %}
                  <li><strong>Stock Price:</strong> {{ results.computed_value|round(2) }}</li>
                {% elif computed_field == 'option_price' %}
                  <li><strong>Option Price:</strong> {{ results.computed_value|round(2) }}</li>
                {% endif %}
              </ul>
            </div>
          </div>
          <div class="card results-card">
            <div class="card-content">
              <span class="card-title">Greeks</span>
              <p><strong>Delta:</strong> {{ greeks.Delta|round(4) }}</p>
              <p><strong>Gamma:</strong> {{ greeks.Gamma|round(4) }}</p>
              <p><strong>Vega:</strong> {{ greeks.Vega|round(4) }}</p>
              <p><strong>Theta:</strong> {{ greeks.Theta|round(4) }}</p>
              <p><strong>Rho:</strong> {{ greeks.Rho|round(4) }}</p>
            </div>
          </div>
          <!-- Graphs (each graph is in its own card) -->
          <div class="card results-card">
            <div class="card-content">
              <span class="card-title">Option Price vs Underlying Price</span>
              <div id="graph_stock">{{ graph_stock|safe }}</div>
            </div>
          </div>
          <div class="card results-card">
            <div class="card-content">
              <span class="card-title">Option Price vs Volatility</span>
              <div id="graph_vol">{{ graph_vol|safe }}</div>
            </div>
          </div>
          <div class="card results-card">
            <div class="card-content">
              <span class="card-title">Option Price vs Time to Expiration</span>
              <div id="graph_T">{{ graph_T|safe }}</div>
            </div>
          </div>
          <div class="card results-card">
            <div class="card-content">
              <span class="card-title">Option Price vs Risk-Free Rate</span>
              <div id="graph_r">{{ graph_r|safe }}</div>
            </div>
          </div>
          {% endif %}
        </div>
      </div>
      
      <!-- Bottom: Explanation of Greeks -->
      <div class="card">
        <div class="card-content">
          <span class="card-title">Greek Explanations</span>
          <p><strong>Delta:</strong> The rate of change of the option price with respect to changes in the underlying asset's price.</p>
          <p><strong>Gamma:</strong> The rate of change in Delta with respect to changes in the underlying price.</p>
          <p><strong>Vega:</strong> The sensitivity of the option price to changes in the volatility of the underlying asset.</p>
          <p><strong>Theta:</strong> The sensitivity of the option price to the passage of time (time decay).</p>
          <p><strong>Rho:</strong> The sensitivity of the option price to changes in the risk-free interest rate.</p>
        </div>
      </div>
    </div>
    
    <!-- Materialize and jQuery, plus initialization of datepicker -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/js/materialize.min.js"></script>
    <script>
      document.addEventListener('DOMContentLoaded', function() {
        var selects = document.querySelectorAll('select');
        M.FormSelect.init(selects);
        var dateElems = document.querySelectorAll('.datepicker');
        M.Datepicker.init(dateElems, {format: 'yyyy-mm-dd'});
      });
      function toggleDarkMode() {
        document.getElementById("body").classList.toggle("dark-mode");
      }
      function toggleAdjustableFields() {
        var optionType = document.getElementById("option_type").value;
        // (Optional: you could hide or show additional fields based on option type if desired)
      }
    </script>
  </body>
</html>
"""

# Route
@app.route('/', methods=['GET','POST'])
def index():
    # Initialize dictionaries for scenario and optional field statuses
    scenario = {
        "option_type": None,
        "underlying_price": None,
        "strike_price": None,
        "expiration_date": None,
        "risk_free_rate": None,
        # Optional fields:
        "volatility": None,
        "stock_price": None,
        "option_price": None
    }
    # For optional fields, we set status for highlighting:
    option_field_status = {
        "volatility": "red",
        "stock_price": "red",
        "option_price": "red"
    }
    results = None
    greeks = {}
    # Variables for graphs
    graph_stock = graph_vol = graph_T = graph_r = ""
    
    if request.method == 'POST':
        form = request.form
        # Mandatory fields:
        scenario["option_type"] = form.get("option_type")
        scenario["underlying_price"] = form.get("underlying_price")
        scenario["strike_price"] = form.get("strike_price")
        scenario["expiration_date"] = form.get("expiration_date")
        scenario["risk_free_rate"] = form.get("risk_free_rate")
        # Optional fields:
        scenario["volatility"] = form.get("volatility")
        scenario["stock_price"] = form.get("stock_price")
        scenario["option_price"] = form.get("option_price")
        
        # Check mandatory fields
        mandatory = ["option_type", "underlying_price", "strike_price", "expiration_date", "risk_free_rate"]
        for field in mandatory:
            if not scenario[field] or scenario[field].strip()=="":
                flash(f"Mandatory field {field.replace('_',' ').title()} is required.")
                return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status=option_field_status)
        
        # Convert mandatory fields to numbers/dates
        try:
            S_mand = float(scenario["underlying_price"])
            K = float(scenario["strike_price"])
            # Parse expiration date; assume format yyyy-mm-dd
            expiration = datetime.datetime.strptime(scenario["expiration_date"], "%Y-%m-%d").date()
            today = datetime.date.today()
            T = max((expiration - today).days / 365.25, 0.001)  # in years
            r = float(scenario["risk_free_rate"])/100.0  # convert percentage to decimal
        except Exception as e:
            flash("Error in parsing mandatory fields: " + str(e))
            return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status=option_field_status)
        
        # For the calculation, use the optional "stock_price" if provided; otherwise use S_mand.
        if scenario["stock_price"] and scenario["stock_price"].strip() != "":
            S = float(scenario["stock_price"])
        else:
            S = S_mand
        
        # Count how many of the optional fields are empty
        empty_optional = [key for key in ["volatility", "stock_price", "option_price"]
                          if not scenario[key] or scenario[key].strip()==""]
        if len(empty_optional) != 1:
            flash("Please leave exactly ONE of the optional fields (Volatility, Stock Price, Option Price) empty for calculation.")
            # Keep all optional fields red.
            option_field_status = {k:"red" for k in option_field_status}
            return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status=option_field_status)
        
        computed_field = empty_optional[0]
        # For the two provided optional fields, convert to numbers (if not empty)
        try:
            if scenario["volatility"] and scenario["volatility"].strip() != "":
                # Assume user enters percentage (e.g., 20 for 20%)
                sigma = float(scenario["volatility"])/100.0
            else:
                sigma = None
            if scenario["stock_price"] and scenario["stock_price"].strip() != "":
                S_opt = float(scenario["stock_price"])
            else:
                S_opt = None
            if scenario["option_price"] and scenario["option_price"].strip() != "":
                option_mkt = float(scenario["option_price"])
            else:
                option_mkt = None
        except Exception as e:
            flash("Error converting optional fields: " + str(e))
            return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status=option_field_status)
        
        # Depending on which optional field is blank, compute it.
        computed_value = None
        try:
            if computed_field == "volatility":
                # Must have option price and stock price provided.
                if option_mkt is None or S_opt is None:
                    raise ValueError("To compute volatility, option price and stock price must be provided.")
                computed_value = compute_implied_volatility(scenario["option_type"], S_opt, K, T, r, option_mkt)
                # Update scenario (store as percentage)
                scenario["volatility"] = str(round(computed_value*100, 2))
            elif computed_field == "stock_price":
                # Must have volatility and option price provided.
                if sigma is None or option_mkt is None:
                    raise ValueError("To compute stock price, volatility and option price must be provided.")
                # Use an initial guess equal to S_mand.
                computed_value = compute_implied_stock(scenario["option_type"], S_mand, K, T, r, sigma, option_mkt)
                scenario["stock_price"] = str(round(computed_value, 2))
            elif computed_field == "option_price":
                # Compute the theoretical option price
                if sigma is None:
                    raise ValueError("To compute option price, volatility must be provided.")
                computed_value = black_scholes_price(scenario["option_type"], S, K, T, r, sigma)
                scenario["option_price"] = str(round(computed_value, 2))
            # Set the computed optional field’s status to green
            option_field_status[computed_field] = "green"
            # The other two remain red.
            for key in option_field_status:
                if key != computed_field:
                    option_field_status[key] = "red"
        except Exception as e:
            flash("Error during calculation: " + str(e))
            return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status=option_field_status)
        
        # Compute Greeks using the values used for the Black-Scholes formula.
        # (Use S = S_opt if provided; else S_mand)
        if sigma is None:
            # If we computed sigma, then use computed_value as sigma.
            sigma_used = computed_value
        else:
            sigma_used = sigma
        # For underlying price, use S_opt if provided; otherwise S_mand.
        S_used = S_opt if S_opt is not None else S_mand
        
        greeks = compute_greeks(scenario["option_type"], S_used, K, T, r, sigma_used)
        
        # Prepare graphs. We create four graphs:
        # 1. Option Price vs Stock Price (vary S from 0.8*S_used to 1.2*S_used)
        S_vals = [S_used * x for x in [0.8 + 0.01*i for i in range(41)]]
        prices1 = [black_scholes_price(scenario["option_type"], s, K, T, r, sigma_used) for s in S_vals]
        fig1 = go.Figure(data=[go.Scatter(x=S_vals, y=prices1, mode='lines', name='Option Price')],
                         layout=go.Layout(title='Option Price vs Underlying Price',
                                            xaxis=dict(title='Underlying Price'),
                                            yaxis=dict(title='Option Price')))
        graph_stock = pyo.plot(fig1, output_type='div', include_plotlyjs='cdn')
        
        # 2. Option Price vs Volatility (vary sigma from 0.5*sigma_used to 1.5*sigma_used)
        sigma_vals = [sigma_used * x for x in [0.5 + 0.02*i for i in range(51)]]
        prices2 = [black_scholes_price(scenario["option_type"], S_used, K, T, r, s) for s in sigma_vals]
        fig2 = go.Figure(data=[go.Scatter(x=[x*100 for x in sigma_vals], y=prices2, mode='lines', name='Option Price')],
                         layout=go.Layout(title='Option Price vs Volatility',
                                            xaxis=dict(title='Volatility (%)'),
                                            yaxis=dict(title='Option Price')))
        graph_vol = pyo.plot(fig2, output_type='div', include_plotlyjs='cdn')
        
        # 3. Option Price vs Time to Expiration (vary T from 0.1*T to 2*T)
        T_vals = [T * (0.1 + 0.02*i) for i in range(91)]
        prices3 = [black_scholes_price(scenario["option_type"], S_used, K, t, r, sigma_used) for t in T_vals]
        fig3 = go.Figure(data=[go.Scatter(x=T_vals, y=prices3, mode='lines', name='Option Price')],
                         layout=go.Layout(title='Option Price vs Time to Expiration',
                                            xaxis=dict(title='Time to Expiration (years)'),
                                            yaxis=dict(title='Option Price')))
        graph_T = pyo.plot(fig3, output_type='div', include_plotlyjs='cdn')
        
        # 4. Option Price vs Risk-Free Rate (vary r from 0 to 2*r)
        r_vals = [r * x for x in [0 + 0.01*i for i in range(101)]]
        prices4 = [black_scholes_price(scenario["option_type"], S_used, K, T, rv, sigma_used) for rv in r_vals]
        fig4 = go.Figure(data=[go.Scatter(x=[rv*100 for rv in r_vals], y=prices4, mode='lines', name='Option Price')],
                         layout=go.Layout(title='Option Price vs Risk-Free Rate',
                                            xaxis=dict(title='Risk-Free Rate (%)'),
                                            yaxis=dict(title='Option Price')))
        graph_r = pyo.plot(fig4, output_type='div', include_plotlyjs='cdn')
        
        results = {
            "computed_field": computed_field,
            "computed_value": computed_value
        }
        
    return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status=option_field_status,
                                  results=results, greeks=greeks, graph_stock=graph_stock,
                                  graph_vol=graph_vol, graph_T=graph_T, graph_r=graph_r)

@app.route('/load/<scenario_id>')
def load_scenario(scenario_id):
    scenario = SCENARIOS.get(scenario_id)
    if not scenario:
        flash("Scenario not found.")
        return redirect(url_for('index'))
    return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status={})

if __name__ == '__main__':
    app.run(debug=True)
