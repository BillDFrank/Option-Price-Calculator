# Option Price Calculator

A small Flask web app that computes Black-Scholes option prices, implied volatility/stock via numerical methods, displays Greeks, and plots interactive graphs using Plotly.

## Files
- `app.py` - Main Flask application.
- `requirements.txt` - Python dependencies.

## Quick start (local)

1. Create a virtual environment and install dependencies:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

2. (Optional) Set environment variables for development. You can set a secret key and FRED API key to fetch the risk-free rate automatically:

```powershell
$env:SECRET_KEY = "changeme"
$env:FRED_API_KEY = "<your_fred_api_key>"
```

3. Run the app:

```powershell
$env:FLASK_APP = 'app.py'; flask run
```

Open http://127.0.0.1:5000 in your browser.

## Deploying to Render.com

This app is compatible with Render's web service. Render expects the web server to bind to `0.0.0.0` and use the `PORT` environment variable.

Render setup steps (summary):

1. Create a new Web Service on Render and connect your GitHub repo.
2. Set the build command to:

```
pip install -r requirements.txt
```

3. Set the start command to (Render will provide `$PORT`):

```
gunicorn app:app --bind 0.0.0.0:$PORT
```

4. Add environment variables in the Render dashboard:
- `SECRET_KEY` - a secure random string
- `FRED_API_KEY` - (optional) your FRED API key to auto-fetch the 10y treasury yield

Render will install dependencies and start the app using Gunicorn.

## Notes and small changes made
- `app.py` now reads `SECRET_KEY` and `FRED_API_KEY` from the environment. This avoids committing secrets into source.
- A small timeout was added to the FRED request to avoid long blocking calls.

## Troubleshooting
- If you see errors about missing packages on Render, pin or update versions in `requirements.txt`.
- If Plotly graphs don't render, ensure that the produced HTML includes Plotly's CDN (the app uses `include_plotlyjs='cdn'`).

If you want, I can also add a `Procfile` or a Render `render.yaml` for full config automation.
