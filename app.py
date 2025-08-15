# app.py
from flask import Flask, render_template_string, request, redirect, url_for, flash
import os
import math
import datetime
import uuid
import requests
import plotly.graph_objs as go
import plotly.offline as pyo
from scipy.stats import norm

app = Flask(__name__)
# Read secret key from environment for production (Render). Falls back to a default for local/dev.
app.secret_key = os.environ.get('SECRET_KEY', 'your_generated_secret_key')

# ----------------------
# Custom Jinja Filter
# ----------------------


@app.template_filter('format_number')
def format_number(value):
    try:
        return f"{value:.2f}"
    except Exception:
        return value

# ----------------------
# FRED API Integration
# ----------------------


def get_treasury_rate(api_key=None):
    """
    Fetch the latest 10-year treasury yield (series DGS10) from FRED.
    Accepts an optional api_key. If not provided it will read from the
    environment variable FRED_API_KEY. Returns the yield as a float
    (in percent) or None on error.
    """
    url = "https://api.stlouisfed.org/fred/series/observations"
    key = api_key or os.environ.get('FRED_API_KEY')
    params = {
        "series_id": "DGS10",
        "file_type": "json",
        "sort_order": "desc",  # most recent observation first
        "limit": 1
    }
    if key:
        params["api_key"] = key
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get("observations"):
            latest_obs = data["observations"][0]
            rate = latest_obs.get("value")
            if rate in ("", "."):
                return None
            return float(rate)
    except Exception as e:
        # don't expose sensitive info in logs
        print("Error fetching treasury rate:", str(e))
    return None

# ----------------------
# Black-Scholes Functions
# ----------------------


def black_scholes_price(option_type, S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S/K) + (r + sigma**2/2)*T) / (sigma*math.sqrt(T))
    d2 = d1 - sigma*math.sqrt(T)
    if option_type.lower() == 'call':
        return S * norm.cdf(d1) - K * math.exp(-r*T) * norm.cdf(d2)
    else:
        return K * math.exp(-r*T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def compute_implied_volatility(option_type, S, K, T, r, market_price, tol=1e-6, max_iter=100):
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
        sigma -= diff/vega
    return sigma


def compute_implied_stock(option_type, S_guess, K, T, r, sigma, market_price, tol=1e-6, max_iter=100):
    S = S_guess
    for i in range(max_iter):
        price = black_scholes_price(option_type, S, K, T, r, sigma)
        d1 = (math.log(S/K) + (r + sigma**2/2)*T) / (sigma*math.sqrt(T))
        delta = norm.cdf(d1) if option_type.lower(
        ) == 'call' else norm.cdf(d1) - 1
        if abs(delta) < 1e-6:
            break
        diff = price - market_price
        if abs(diff) < tol:
            return S
        S -= diff/delta
    return S


def compute_greeks(option_type, S, K, T, r, sigma):
    d1 = (math.log(S/K) + (r + sigma**2/2)*T) / (sigma*math.sqrt(T))
    d2 = d1 - sigma*math.sqrt(T)
    delta = norm.cdf(d1) if option_type.lower() == 'call' else norm.cdf(d1) - 1
    gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
    vega = S * norm.pdf(d1) * math.sqrt(T)
    if option_type.lower() == 'call':
        theta = (-S * norm.pdf(d1)*sigma/(2*math.sqrt(T)) -
                 r*K*math.exp(-r*T)*norm.cdf(d2))
        rho = K*T*math.exp(-r*T)*norm.cdf(d2)
    else:
        theta = (-S * norm.pdf(d1)*sigma/(2*math.sqrt(T)) +
                 r*K*math.exp(-r*T)*norm.cdf(-d2))
        rho = -K*T*math.exp(-r*T)*norm.cdf(-d2)
    return {'Delta': delta, 'Gamma': gamma, 'Vega': vega, 'Theta': theta, 'Rho': rho}


# ---------------------------
# HTML Template (Materialize)
# ---------------------------
# Mandatory: Option Type, Strike Price, Expiration Date, Risk-Free Rate.
# Optional: Volatility, Stock Price, Option Price (exactly one must be empty).
# A "Clear All" button reloads the page and re-fetches the risk-free rate.
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
      html, body { margin: 0; padding: 0; }
      body { padding-top: 0; }
      nav { margin-bottom: 0; }
      .dark-mode {
        background-color: #23272e !important;
        color: #f5f5f5 !important;
      }
      .dark-mode .card,
      .dark-mode .card-content,
      .dark-mode .card-title,
      .dark-mode label,
      .dark-mode p,
      .dark-mode .input-field input,
      .dark-mode .input-field textarea,
      .dark-mode .input-field select,
      .dark-mode .input-field .select-dropdown,
      .dark-mode .input-field input::placeholder,
      .dark-mode .input-field input[type="text"],
      .dark-mode .input-field input[type="number"],
      .dark-mode .input-field input[type="date"],
      .dark-mode .input-field .caret,
      .dark-mode .input-field .dropdown-content li > span {
        color: #f5f5f5 !important;
      }
      .dark-mode .input-field input:focus + label,
      .dark-mode .input-field input:valid + label,
      .dark-mode .input-field input:invalid + label,
      .dark-mode .input-field textarea:focus + label,
      .dark-mode .input-field textarea:valid + label,
      .dark-mode .input-field textarea:invalid + label {
        color: #90caf9 !important;
      }
      .dark-mode .select-dropdown.dropdown-content li span {
        color: #23272e !important;
      }
      .dark-mode .select-wrapper input.select-dropdown {
        background-color: #23272e !important;
        color: #f5f5f5 !important;
      }
      .dark-mode .dropdown-content {
        background-color: #23272e !important;
      }
      .dark-mode .card {
        background-color: #2c313a !important;
      }
      .dark-mode .divider {
        background-color: #616161 !important;
      }
      .dark-mode .btn,
      .dark-mode .btn:hover {
        background-color: #1976d2 !important;
        color: #fff !important;
      }
      .dark-mode .input-field input,
      .dark-mode .input-field textarea {
        border-bottom: 1px solid #90caf9 !important;
        box-shadow: 0 1px 0 0 #90caf9 !important;
      }
      .dark-mode .input-field input:focus,
      .dark-mode .input-field textarea:focus {
        border-bottom: 2px solid #90caf9 !important;
        box-shadow: 0 1px 0 0 #90caf9 !important;
      }
      .dark-mode .red-border input:not([readonly]),
      .dark-mode .red-border textarea:not([readonly]) {
        border-bottom: 2px solid #ef5350 !important;
        box-shadow: 0 1px 0 0 #ef5350 !important;
      }
      .dark-mode .green-border input:not([readonly]),
      .dark-mode .green-border textarea:not([readonly]) {
        border-bottom: 2px solid #66bb6a !important;
        box-shadow: 0 1px 0 0 #66bb6a !important;
      }
      .red-border input:not([readonly]), .red-border textarea:not([readonly]) { border-bottom: 2px solid red !important; box-shadow: 0 1px 0 0 red !important; }
      .green-border input:not([readonly]), .green-border textarea:not([readonly]) { border-bottom: 2px solid green !important; box-shadow: 0 1px 0 0 green !important; }
      .results-card { margin-bottom: 15px; }
      .toggle-table { margin-bottom: 15px; }
      .datepicker-modal { z-index: 10000; }
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
                <!-- Mandatory Fields -->
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
                  <!-- Strike Price -->
                  <div class="input-field col s12 red-border">
                    <input id="strike_price" type="number" step="0.01" name="strike_price" value="{{ scenario.strike_price if scenario.strike_price is not none else '' }}">
                    <label for="strike_price" class="{% if scenario.strike_price %}active{% endif %}">Strike Price *</label>
                  </div>
                  <!-- Expiration Date -->
                  <div class="input-field col s12 red-border">
                    <input id="expiration_date" type="text" class="datepicker" name="expiration_date" value="{{ scenario.expiration_date if scenario.expiration_date is not none else '' }}">
                    <label for="expiration_date" class="{% if scenario.expiration_date %}active{% endif %}">Expiration Date *</label>
                  </div>
                  <!-- Risk-Free Rate -->
                  <div class="input-field col s12 red-border">
                    <input id="risk_free_rate" type="number" step="0.01" name="risk_free_rate" value="{{ scenario.risk_free_rate if scenario.risk_free_rate is not none else '' }}">
                    <label for="risk_free_rate" class="{% if scenario.risk_free_rate %}active{% endif %}">Risk-Free Rate (%) *</label>
                  </div>
                </div>
                <div class="divider"></div>
                <!-- Optional Fields -->
                <div class="row">
                  <p>Fill exactly two of the following (Volatility, Stock Price, Option Price) and leave one blank. The blank field will turn green.</p>
                  <!-- Volatility -->
                  <div class="input-field col s12 {% if option_field_status.volatility %}{{ 'red-border' if option_field_status.volatility=='red' else 'green-border' }}{% endif %}">
                    <input id="volatility" type="number" step="0.01" name="volatility" value="{{ scenario.volatility if scenario.volatility is not none else '' }}">
                    <label for="volatility" class="{% if scenario.volatility %}active{% endif %}">Volatility (%)</label>
                  </div>
                  <!-- Stock Price -->
                  <div class="input-field col s12 {% if option_field_status.stock_price %}{{ 'red-border' if option_field_status.stock_price=='red' else 'green-border' }}{% endif %}">
                    <input id="stock_price" type="number" step="0.01" name="stock_price" value="{{ scenario.stock_price if scenario.stock_price is not none else '' }}">
                    <label for="stock_price" class="{% if scenario.stock_price %}active{% endif %}">Stock Price</label>
                  </div>
                  <!-- Option Price -->
                  <div class="input-field col s12 {% if option_field_status.option_price %}{{ 'red-border' if option_field_status.option_price=='red' else 'green-border' }}{% endif %}">
                    <input id="option_price" type="number" step="0.01" name="option_price" value="{{ scenario.option_price if scenario.option_price is not none else '' }}">
                    <label for="option_price" class="{% if scenario.option_price %}active{% endif %}">Option Price</label>
                  </div>
                </div>
                <div class="row">
                  <div class="col s6">
                    <button class="btn waves-effect waves-light" type="submit" name="action" value="calculate">Calculate Option Variable</button>
                  </div>
                  <div class="col s6">
                    <button class="btn waves-effect waves-light" type="button" onclick="clearForm()">Clear All</button>
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
              <p>The missing field (highlighted in green) has been computed:</p>
              <ul>
                {% if computed_field == 'volatility' %}
                  <li><strong>Volatility:</strong> {{ results.computed_value*100|round(2) }} %</li>
                {% elif computed_field == 'stock_price' %}
                  <li><strong>Stock Price:</strong> {{ results.computed_value|round(2) }}</li>
                {% elif computed_field == 'option_price' %}
                  <li><strong>Option Price:</strong> {{ results.computed_value|format_number }}</li>
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
          <!-- Graphs (each in its own card) -->
          <div class="card results-card">
            <div class="card-content">
              <span class="card-title">Option Price vs Stock Price</span>
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

      <!-- Bottom: Greek Explanations -->
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

    <!-- Materialize, jQuery, and Datepicker Initialization -->
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
      // Clear the form by submitting a GET request to the root (resets all fields and re-fetches risk-free rate)
      function clearForm() {
        window.location.href = '/';
      }
    </script>
  </body>
</html>
"""

# -----------------------------
# Routes and Calculation Logic
# -----------------------------


@app.route('/', methods=['GET', 'POST'])
def index():
    # Initialize scenario dictionary (no underlying_price field)
    scenario = {
        "option_type": None,
        "strike_price": None,
        "expiration_date": None,
        "risk_free_rate": None,
        "volatility": None,
        "stock_price": None,
        "option_price": None
    }
    # On GET, fetch the risk-free rate automatically from FRED.
    if request.method == 'GET':
        # Try to fetch the latest 10y treasury yield. The FRED API key can be
        # supplied via the FRED_API_KEY environment variable. If not present,
        # the call will still be attempted without a key (may be rate-limited).
        fetched_rate = get_treasury_rate()
        if fetched_rate is not None:
            scenario["risk_free_rate"] = f"{fetched_rate:.2f}"
    # Optional field statuses: start as red.
    option_field_status = {
        "volatility": "red",
        "stock_price": "red",
        "option_price": "red"
    }
    results = None
    greeks = {}
    graph_stock = graph_vol = graph_T = graph_r = ""
    computed_field = None

    if request.method == 'POST':
        form = request.form
        # Mandatory fields
        scenario["option_type"] = form.get("option_type")
        scenario["strike_price"] = form.get("strike_price")
        scenario["expiration_date"] = form.get("expiration_date")
        scenario["risk_free_rate"] = form.get("risk_free_rate")
        # Optional fields
        scenario["volatility"] = form.get("volatility")
        scenario["stock_price"] = form.get("stock_price")
        scenario["option_price"] = form.get("option_price")

        mandatory = ["option_type", "strike_price",
                     "expiration_date", "risk_free_rate"]
        for field in mandatory:
            if not scenario[field] or scenario[field].strip() == "":
                flash(
                    f"Mandatory field {field.replace('_',' ').title()} is required.")
                return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status=option_field_status)
        try:
            K = float(scenario["strike_price"])
            expiration = datetime.datetime.strptime(
                scenario["expiration_date"], "%Y-%m-%d").date()
            today = datetime.date.today()
            T = max((expiration - today).days / 365.25, 0.001)
            r = float(scenario["risk_free_rate"])/100.0
        except Exception as e:
            flash("Error parsing mandatory fields: " + str(e))
            return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status=option_field_status)

        empty_optional = [key for key in ["volatility", "stock_price", "option_price"]
                          if not scenario[key] or scenario[key].strip() == ""]
        if len(empty_optional) != 1:
            flash("Please leave exactly ONE of the optional fields (Volatility, Stock Price, Option Price) empty for calculation.")
            option_field_status = {k: "red" for k in option_field_status}
            return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status=option_field_status)
        computed_field = empty_optional[0]

        try:
            if scenario["volatility"] and scenario["volatility"].strip() != "":
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

        computed_value = None
        try:
            if computed_field == "volatility":
                if option_mkt is None or S_opt is None:
                    raise ValueError(
                        "To compute volatility, both Stock Price and Option Price must be provided.")
                computed_value = compute_implied_volatility(
                    scenario["option_type"], S_opt, K, T, r, option_mkt)
                scenario["volatility"] = str(round(computed_value*100, 2))
            elif computed_field == "stock_price":
                if sigma is None or option_mkt is None:
                    raise ValueError(
                        "To compute stock price, both Volatility and Option Price must be provided.")
                computed_value = compute_implied_stock(
                    scenario["option_type"], K, K, T, r, sigma, option_mkt)
                scenario["stock_price"] = str(round(computed_value, 2))
            elif computed_field == "option_price":
                if sigma is None:
                    raise ValueError(
                        "To compute option price, Volatility must be provided.")
                computed_value = black_scholes_price(
                    scenario["option_type"], S_opt, K, T, r, sigma)
                if computed_value < 0.01:
                    computed_value = 0.01
                scenario["option_price"] = f"{computed_value:.2f}"
            option_field_status[computed_field] = "green"
            for key in option_field_status:
                if key != computed_field:
                    option_field_status[key] = "red"
        except Exception as e:
            flash("Error during calculation: " + str(e))
            return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status=option_field_status)

        if scenario["stock_price"] and scenario["stock_price"].strip() != "":
            S_used = float(scenario["stock_price"])
        else:
            S_used = computed_value
        sigma_used = computed_value if computed_field == "volatility" else sigma

        greeks = compute_greeks(
            scenario["option_type"], S_used, K, T, r, sigma_used)

        S_vals = [S_used * x for x in [0.8 + 0.01*i for i in range(41)]]
        prices1 = [black_scholes_price(
            scenario["option_type"], s, K, T, r, sigma_used) for s in S_vals]
        fig1 = go.Figure(data=[go.Scatter(x=S_vals, y=prices1, mode='lines', name='Option Price')],
                         layout=go.Layout(title='Option Price vs Stock Price',
                                          xaxis=dict(title='Stock Price'),
                                          yaxis=dict(title='Option Price')))
        graph_stock = pyo.plot(fig1, output_type='div', include_plotlyjs='cdn')

        sigma_vals = [sigma_used *
                      x for x in [0.5 + 0.02*i for i in range(51)]]
        prices2 = [black_scholes_price(
            scenario["option_type"], S_used, K, T, r, s) for s in sigma_vals]
        fig2 = go.Figure(data=[go.Scatter(x=[x*100 for x in sigma_vals], y=prices2, mode='lines', name='Option Price')],
                         layout=go.Layout(title='Option Price vs Volatility',
                                          xaxis=dict(title='Volatility (%)'),
                                          yaxis=dict(title='Option Price')))
        graph_vol = pyo.plot(fig2, output_type='div', include_plotlyjs='cdn')

        T_vals = [T * (0.1 + 0.02*i) for i in range(91)]
        prices3 = [black_scholes_price(
            scenario["option_type"], S_used, K, t, r, sigma_used) for t in T_vals]
        fig3 = go.Figure(data=[go.Scatter(x=T_vals, y=prices3, mode='lines', name='Option Price')],
                         layout=go.Layout(title='Option Price vs Time to Expiration',
                                          xaxis=dict(
                                              title='Time to Expiration (years)'),
                                          yaxis=dict(title='Option Price')))
        graph_T = pyo.plot(fig3, output_type='div', include_plotlyjs='cdn')

        r_vals = [r * x for x in [0 + 0.01*i for i in range(101)]]
        prices4 = [black_scholes_price(
            scenario["option_type"], S_used, K, T, rv, sigma_used) for rv in r_vals]
        fig4 = go.Figure(data=[go.Scatter(x=[rv*100 for rv in r_vals], y=prices4, mode='lines', name='Option Price')],
                         layout=go.Layout(title='Option Price vs Risk-Free Rate',
                                          xaxis=dict(
                                              title='Risk-Free Rate (%)'),
                                          yaxis=dict(title='Option Price')))
        graph_r = pyo.plot(fig4, output_type='div', include_plotlyjs='cdn')

        results = {"computed_field": computed_field,
                   "computed_value": computed_value}

    return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status=option_field_status,
                                  results=results, greeks=greeks, graph_stock=graph_stock, graph_vol=graph_vol,
                                  graph_T=graph_T, graph_r=graph_r, computed_field=computed_field)


@app.route('/load/<scenario_id>')
def load_scenario(scenario_id):
    scenario = SCENARIOS.get(scenario_id)
    if not scenario:
        flash("Scenario not found.")
        return redirect(url_for('index'))
    return render_template_string(HTML_TEMPLATE, scenario=scenario, option_field_status={})


if __name__ == '__main__':
    # Use environment PORT and bind to 0.0.0.0 for cloud hosts like Render.
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0'
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host=host, port=port, debug=debug)
