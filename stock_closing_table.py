from __future__ import annotations

import argparse
import html
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf


HKEX_TICKERS = [
    "0011",
    "0005",
    "2888",
    "1288",
    "1398",
    "3988",
    "0939",
    "3328",
    "3968",
    "0386",
    "0857",
    "0883",
    "3983",
    "1766",
    "1186",
    "0390",
    "3969",
    "2318",
    "2628",
    "0728",
    "0941",
    "0763",
    "2038",
    "1810",
    "6082",
    "0700",
    "9988",
    "9618",
    "3690",
    "9888",
    "0981",
    "1211",
    "1024",
    "3033",
    "3067",
    "0388",
    "1928",
    "3750",
    "9868",
]

SGX_TICKERS = [
    "O39",
    "D05",
    "U11",
    "U96",
    "5E2",
    "S58",
    "S63",
    "S08",
    "Z74",
    "CC3",
    "BS6",
    "BN4",
    "C09",
    "Y92",
    "G13",
    "M01",
    "F34",
    "Z59",
    "S68",
    "S59",
    "MZH",
]

COMPANY_NAME_OVERRIDES = {
    "0011.HK": "HANG SENG BANK",
}


@dataclass(frozen=True)
class Stock:
    sector: str
    display_ticker: str
    yahoo_ticker: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create CSV, XLSX, and mobile-friendly HTML tables of HKEX and SGX daily closing prices."
    )
    parser.add_argument(
        "--trading-days",
        type=int,
        default=5,
        help="How many latest trading days to show. Default is 5, roughly one market week.",
    )
    parser.add_argument(
        "--period",
        default="14d",
        help="Download period. Keep this longer than trading-days so change can use the prior close.",
    )
    parser.add_argument(
        "--outdir",
        default="outputs",
        help="Directory where CSV, XLSX, and HTML files will be written.",
    )
    parser.add_argument(
        "--adjusted",
        action="store_true",
        help="Use adjusted close values instead of raw exchange close values.",
    )
    parser.add_argument(
        "--skip-company-names",
        action="store_true",
        help="Skip yfinance company-name lookups and use tickers as the name fallback.",
    )
    return parser.parse_args()


def build_stock_list() -> list[Stock]:
    hkex = [
        Stock(sector="HKEX", display_ticker=ticker, yahoo_ticker=f"{ticker}.HK")
        for ticker in HKEX_TICKERS
    ]
    sgx = [
        Stock(sector="SGX", display_ticker=ticker, yahoo_ticker=f"{ticker}.SI")
        for ticker in SGX_TICKERS
    ]
    return hkex + sgx


def get_price_frame(yahoo_tickers: list[str], period: str, adjusted: bool) -> pd.DataFrame:
    data = yf.download(
        tickers=yahoo_tickers,
        period=period,
        interval="1d",
        progress=False,
        auto_adjust=False,
        group_by="column",
        threads=True,
    )

    price_field = "Adj Close" if adjusted else "Close"
    if isinstance(data.columns, pd.MultiIndex):
        closes = data[price_field]
    else:
        closes = data[[price_field]]
        closes.columns = yahoo_tickers[:1]

    closes = closes.reindex(columns=yahoo_tickers)

    missing_tickers = [ticker for ticker in yahoo_tickers if ticker not in closes or closes[ticker].dropna().empty]
    for ticker in missing_tickers:
        try:
            retry = yf.download(
                tickers=ticker,
                period=period,
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False,
            )
            if price_field in retry:
                closes[ticker] = retry[price_field]
        except Exception:
            pass

    closes = closes.reindex(columns=yahoo_tickers)
    closes.index = pd.to_datetime(closes.index).date
    return closes


def get_company_names(stocks: list[Stock], skip: bool) -> dict[str, str]:
    if skip:
        return {stock.yahoo_ticker: stock.display_ticker for stock in stocks}

    names = {}
    for stock in stocks:
        if stock.yahoo_ticker in COMPANY_NAME_OVERRIDES:
            names[stock.yahoo_ticker] = COMPANY_NAME_OVERRIDES[stock.yahoo_ticker]
            continue
        try:
            info = yf.Ticker(stock.yahoo_ticker).get_info()
            name = info.get("shortName") or info.get("longName") or stock.display_ticker
        except Exception:
            name = stock.display_ticker
        names[stock.yahoo_ticker] = str(name)
    return names


def build_output_table(
    stocks: list[Stock],
    closes: pd.DataFrame,
    company_names: dict[str, str],
    trading_days: int,
) -> tuple[pd.DataFrame, list[str]]:
    dates = list(closes.index)
    if len(dates) < 2:
        raise ValueError("Need at least two trading days to calculate price changes.")

    display_dates = dates[-trading_days:]
    rows = []

    for stock in stocks:
        row: dict[str, object] = {
            "Sector": stock.sector,
            "Ticker": stock.display_ticker,
            "Company Name": company_names.get(stock.yahoo_ticker, stock.display_ticker),
        }

        series = closes[stock.yahoo_ticker] if stock.yahoo_ticker in closes else pd.Series(dtype=float)
        for current_date in display_dates:
            previous_values = series.loc[:current_date].dropna()
            if previous_values.empty:
                close = pd.NA
                change = pd.NA
                pct_change = pd.NA
            else:
                close = previous_values.iloc[-1]
                prior_values = series.loc[:current_date].dropna().iloc[:-1]
                prior_close = prior_values.iloc[-1] if not prior_values.empty else pd.NA
                change = close - prior_close if not pd.isna(prior_close) else pd.NA
                pct_change = (change / prior_close) * 100 if not pd.isna(prior_close) and prior_close else pd.NA

            date_label = current_date.isoformat()
            row[f"{date_label} Close"] = close
            row[f"{date_label} Change"] = change
            row[f"{date_label} Change %"] = pct_change

        rows.append(row)

    table = pd.DataFrame(rows)
    number_columns = [column for column in table.columns if column not in {"Sector", "Ticker", "Company Name"}]
    table[number_columns] = table[number_columns].astype("Float64").round(2)
    return table, [date_value.isoformat() for date_value in display_dates]


def format_price(value: object) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):,.2f}"


def format_change(value: object) -> str:
    if pd.isna(value):
        return ""
    number = float(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{number:,.2f}"


def format_percent(value: object) -> str:
    if pd.isna(value):
        return ""
    number = float(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{number:,.2f}%"


def change_class(value: object) -> str:
    if pd.isna(value):
        return "flat"
    number = float(value)
    if number > 0:
        return "up"
    if number < 0:
        return "down"
    return "flat"


def render_html(table: pd.DataFrame, dates: list[str], title: str, source_note: str) -> str:
    generated_at = pd.Timestamp.now(tz="Asia/Jakarta").strftime("%Y-%m-%d %H:%M %Z")
    latest_column = dates[-1] if dates else ""

    date_headers = "\n".join(
        f"<th scope=\"col\" colspan=\"3\" class=\"day-start\">{date_value}</th>"
        for date_value in dates
    )
    metric_headers = "\n".join(
        "<th scope=\"col\" class=\"day-start\">Close</th><th scope=\"col\">Chg</th><th scope=\"col\">%</th>"
        for _ in dates
    )

    rows_html = []
    current_sector = None
    for _, row in table.iterrows():
        sector = str(row["Sector"])
        if sector != current_sector:
            rows_html.append(
                f"<tr class=\"sector-row\"><th scope=\"rowgroup\" colspan=\"{3 + len(dates) * 3}\">{html.escape(sector)}</th></tr>"
            )
            current_sector = sector

        cells = [
            f"<th scope=\"row\" class=\"ticker\">{html.escape(str(row['Ticker']))}</th>",
            f"<td class=\"name\">{html.escape(str(row['Company Name']))}</td>",
        ]
        for date_value in dates:
            close = row[f"{date_value} Close"]
            change = row[f"{date_value} Change"]
            pct = row[f"{date_value} Change %"]
            cls = change_class(change)
            cells.append(f"<td class=\"day-start\">{format_price(close)}</td>")
            cells.append(f"<td class=\"{cls}\">{format_change(change)}</td>")
            cells.append(f"<td class=\"{cls}\">{format_percent(pct)}</td>")
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    body_rows = "\n".join(rows_html)
    min_width = max(980, 260 + 220 * len(dates))

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="900">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #15171c;
      --muted: #68707e;
      --line: #d9dee7;
      --accent: #0b6bcb;
      --sticky: #eef4fb;
      --sector: #e6edf5;
      --up: #087443;
      --down: #b42318;
      --flat: #68707e;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #101215;
        --panel: #181b20;
        --text: #f4f6f8;
        --muted: #a8b0bd;
        --line: #333944;
        --accent: #7ab7ff;
        --sticky: #202a35;
        --sector: #252c35;
        --up: #60d394;
        --down: #ff8a80;
        --flat: #a8b0bd;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.35;
    }}
    main {{
      width: min(1280px, 100%);
      margin: 0 auto;
      padding: 18px 14px 28px;
    }}
    header {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .meta {{
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .latest {{
      color: var(--accent);
      font-size: 13px;
      white-space: nowrap;
    }}
    .table-wrap {{
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      -webkit-overflow-scrolling: touch;
      max-height: calc(100vh - 118px);
    }}
    table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      min-width: {min_width}px;
      font-variant-numeric: tabular-nums;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 9px 10px;
      text-align: right;
      white-space: nowrap;
      font-size: 13px;
    }}
    thead th {{
      position: sticky;
      top: 0;
      z-index: 3;
      background: var(--panel);
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }}
    thead tr:nth-child(2) th {{
      top: 32px;
      border-bottom: 2px solid var(--line);
    }}
    .ticker, .name, thead .sticky-left {{
      position: sticky;
      z-index: 4;
      background: var(--sticky);
    }}
    .ticker, thead .ticker-head {{
      left: 0;
      min-width: 72px;
      text-align: left;
      font-weight: 700;
    }}
    .name, thead .name-head {{
      left: 72px;
      min-width: 210px;
      max-width: 280px;
      overflow: hidden;
      text-overflow: ellipsis;
      text-align: left;
    }}
    thead .ticker-head,
    thead .name-head {{
      top: 0;
      z-index: 5;
    }}
    tbody .ticker,
    tbody .name {{
      z-index: 2;
    }}
    .sector-row th {{
      position: sticky;
      left: 0;
      z-index: 2;
      background: var(--sector);
      color: var(--text);
      text-align: left;
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .up {{ color: var(--up); font-weight: 650; }}
    .down {{ color: var(--down); font-weight: 650; }}
    .flat {{ color: var(--flat); }}
    .day-start {{
      border-left: 1px solid var(--line);
    }}
    footer {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 12px;
    }}
    @media (max-width: 720px) {{
      main {{ padding: 12px 8px 20px; }}
      header {{
        align-items: start;
        flex-direction: column;
        gap: 6px;
      }}
      h1 {{ font-size: 20px; }}
      th, td {{ padding: 8px 9px; }}
      .ticker, thead .ticker-head {{ min-width: 64px; }}
      .name, thead .name-head {{
        left: 64px;
        min-width: 170px;
        max-width: 210px;
      }}
      .table-wrap {{ max-height: calc(100vh - 104px); }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>{html.escape(title)}</h1>
        <p class="meta">Generated {generated_at}. Page auto-refreshes every 15 minutes.</p>
      </div>
      <div class="latest">Latest trading day: {html.escape(latest_column)}</div>
    </header>
    <div class="table-wrap" role="region" aria-label="Scrollable closing price table" tabindex="0">
      <table>
        <thead>
          <tr>
            <th scope="col" rowspan="2" class="sticky-left ticker-head">Ticker</th>
            <th scope="col" rowspan="2" class="sticky-left name-head">Company Name</th>
            {date_headers}
          </tr>
          <tr>
            {metric_headers}
          </tr>
        </thead>
        <tbody>
          {body_rows}
        </tbody>
      </table>
    </div>
    <footer>{html.escape(source_note)}</footer>
  </main>
</body>
</html>
"""


def write_outputs(table: pd.DataFrame, dates: list[str], outdir: Path, adjusted: bool) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    csv_path = outdir / "stock_closing_prices.csv"
    xlsx_path = outdir / "stock_closing_prices.xlsx"
    html_path = outdir / "stock_closing_prices.html"

    table.to_csv(csv_path, index=False)
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        table.to_excel(writer, sheet_name="Closing Prices", index=False)
        worksheet = writer.sheets["Closing Prices"]
        worksheet.freeze_panes = "D2"
        for column_cells in worksheet.columns:
            width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, 34)
            worksheet.column_dimensions[column_cells[0].column_letter].width = width

    price_type = "adjusted close" if adjusted else "raw close"
    source_note = (
        "Data source: Yahoo Finance via yfinance. "
        f"Values are daily {price_type} prices; changes compare with the prior available trading close."
    )
    html_path.write_text(
        render_html(table, dates, "HKEX and SGX Closing Prices", source_note),
        encoding="utf-8",
    )

    print(f"Wrote {csv_path}")
    print(f"Wrote {xlsx_path}")
    print(f"Wrote {html_path}")


def main() -> None:
    args = parse_args()
    stocks = build_stock_list()
    yahoo_tickers = [stock.yahoo_ticker for stock in stocks]
    closes = get_price_frame(yahoo_tickers, args.period, args.adjusted)
    company_names = get_company_names(stocks, args.skip_company_names)
    table, dates = build_output_table(stocks, closes, company_names, args.trading_days)
    write_outputs(table, dates, Path(args.outdir), args.adjusted)


if __name__ == "__main__":
    main()
