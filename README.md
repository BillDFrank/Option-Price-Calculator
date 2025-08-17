# Option Price Calculator

This project is a web-based Option Price Calculator built with Flask and Materialize CSS. It allows users to calculate the price of European call and put options using the Black-Scholes model, as well as compute implied volatility or implied stock price given the other parameters. The app also provides visualizations and the calculation of option Greeks.

## Features

- **Black-Scholes Pricing:** Calculate the theoretical price of European call and put options.
- **Implied Volatility & Stock Price:** Compute implied volatility or implied stock price by leaving one of the optional fields blank.
- **Automatic Risk-Free Rate:** Fetches the latest 10-year US Treasury yield from the FRED API to use as the risk-free rate.
- **Option Greeks:** Displays Delta, Gamma, Vega, Theta, and Rho for the calculated scenario.
- **Interactive Graphs:** Visualizes how the option price changes with respect to stock price, volatility, time to expiration, and risk-free rate using Plotly.
- **Modern UI:** Responsive and visually appealing interface using Materialize CSS, with support for dark mode.
- **Clear All:** Instantly reset all fields and re-fetch the risk-free rate.

## Usage

1. **Install dependencies:**
	```bash
	pip install -r requirements.txt
	```
2. **(Optional) Set FRED API Key:**
	- To avoid rate limits, set your FRED API key as an environment variable:
	  ```bash
	  set FRED_API_KEY=your_fred_api_key
	  ```
3. **Run the app:**
	```bash
	python app.py
	```
4. **Open your browser:**
	- Visit [http://localhost:5000](http://localhost:5000)

## How It Works

1. **Input Parameters:**
	- Mandatory: Option Type (call/put), Strike Price, Expiration Date, Risk-Free Rate (auto-fetched).
	- Optional: Volatility, Stock Price, Option Price (leave exactly one blank to compute it).
2. **Calculation:**
	- The app uses the Black-Scholes formula to compute the missing value and the Greeks.
3. **Visualization:**
	- Interactive graphs show how the option price responds to changes in key parameters.

## Technologies Used

- Python, Flask
- Materialize CSS
- Plotly
- FRED API (for risk-free rate)

