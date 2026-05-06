# HKEX and SGX Closing Price Table

This creates a mobile-friendly table where each row is a stock ticker and company name, grouped into HKEX and SGX sections. The date columns show the latest market week of daily close, price change versus the prior trading close, and percentage change.

## Run Manually

```bash
python3 stock_closing_table.py
```

Outputs are written to `outputs/`:

- `stock_closing_prices.html`: best quick view on iPhone/iPad
- `stock_closing_prices.xlsx`: best for Numbers, Excel, or Google Sheets
- `stock_closing_prices.csv`: best for data reuse

## Refresh Daily On This Mac

The included `com.local.stock-closing-prices.plist` is a macOS `launchd` template that runs the refresh at 17:30 local Mac time. That is intentionally after both HKEX and SGX regular market closes, allowing some time for Yahoo Finance data to update.

Install it with:

```bash
cp com.local.stock-closing-prices.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.local.stock-closing-prices.plist
```

The HTML page auto-refreshes every 15 minutes, so if it is open in Safari it will pick up the newly generated file after the scheduled run.

## iPhone and iPad Access

The simplest setup is to put the `outputs/` folder in iCloud Drive, then open `stock_closing_prices.html` from Files or Safari. For editing or filtering, open `stock_closing_prices.xlsx` in Numbers, Excel, or Google Sheets.

For a true always-online website, the next step would be GitHub Pages plus a scheduled GitHub Actions workflow. That avoids needing your Mac to be awake.

## GitHub Actions Website Refresh

This repo includes `.github/workflows/refresh-stock-table.yml`.

When pushed to GitHub, it can:

- run every weekday at 19:00 WIB
- install the Python dependencies
- run `python stock_closing_table.py`
- commit refreshed CSV/XLSX/HTML outputs
- publish the `outputs/` folder to GitHub Pages

After pushing this project to GitHub, enable Pages with **Source: GitHub Actions** in the repository settings. The workflow can also be run manually from the repository's **Actions** tab.

## Data Source

The script uses Yahoo Finance through `yfinance`. It is convenient and free for personal tracking, but unofficial. For a more reliable API-backed setup, use Polygon.io, Tiingo, Alpha Vantage, or Nasdaq Data Link.

By default, the script uses raw daily `Close`. Add `--adjusted` if you want adjusted close values that account for splits and dividends.
