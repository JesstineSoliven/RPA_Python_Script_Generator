# Dependencies: pip install requests selenium
# Requires: Google Chrome browser and matching ChromeDriver
import sys
import os
import argparse
import logging
import datetime
import json
import re
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait, Select
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException,
        NoSuchElementException,
        WebDriverException,
    )
except ImportError:
    webdriver = None


# =============================================================================
# CONFIGURATION
# =============================================================================

LAG_DAYS = {
    "CNY": 1,
    "EUR": 2,
    "NZD": 0,
}

CNY_TENOR_MAP = {
    "S1M": "1M",
    "S3M": "3M",
    "S6M": "6M",
    "S9M": "9M",
    "S1Y": "1Y",
}

EUR_TENOR_MAP = {
    "1MT": "1 month",
    "3MT": "3 months",
    "6MT": "6 months",
    "1YT": "12 months",
}

NZD_TENOR_MAP = {
    "1MT": "1 Month",
    "2MT": "2 Month",
    "3MT": "3 Month",
    "4MT": "4 Month",
    "5MT": "5 Month",
    "6MT": "6 Month",
}

TENOR_MAPS = {
    "CNY": CNY_TENOR_MAP,
    "EUR": EUR_TENOR_MAP,
    "NZD": NZD_TENOR_MAP,
}

INTERFACE_FILE_PATTERNS = [
    "ADB_IXRATE_{date}.txt",
    "ADB_SO_IXRATE_{date}.txt",
]

SHIBOR_API_URL = "https://www.shibor.org/ags/ms/cm-u-bk-shibor/ShiborHis"
EURIBOR_URL = "https://www.euribor-rates.eu/en/current-euribor-rates/"
NZFMA_URL = "https://www.nzfma.org/data/search.aspx"

CURRENCY_SOURCES = {
    "CNY": "SHIBOR API (https://www.shibor.org)",
    "EUR": EURIBOR_URL,
    "NZD": NZFMA_URL,
}


# =============================================================================
# DATE CALCULATION
# =============================================================================

def calculate_interface_date(check_date, currency):
    lag = LAG_DAYS.get(currency, 0)
    return check_date - datetime.timedelta(days=lag)


def format_date_for_filename(dt):
    return dt.strftime("%Y%m%d")


# =============================================================================
# INTERFACE FILE PARSING
# =============================================================================

def find_interface_file(folder, target_date, max_fallback_days=3):
    folder_path = Path(folder)
    if not folder_path.is_dir():
        raise FileNotFoundError(f"Interface folder does not exist: {folder}")

    for day_offset in range(max_fallback_days + 1):
        search_date = target_date - datetime.timedelta(days=day_offset)
        date_str = format_date_for_filename(search_date)
        for pattern in INTERFACE_FILE_PATTERNS:
            file_name = pattern.format(date=date_str)
            file_path = folder_path / file_name
            if file_path.is_file():
                if day_offset > 0:
                    logging.warning(
                        "Interface file not found for %s, using fallback date %s",
                        target_date.isoformat(),
                        search_date.isoformat(),
                    )
                return str(file_path), search_date
    raise FileNotFoundError(
        f"No interface file found for date {target_date.isoformat()} "
        f"(searched {max_fallback_days + 1} days back) in {folder}"
    )


def parse_interface_file(file_path):
    rates = {}
    header_date = None

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue

            if parts[0] == "D" and len(parts) >= 7:
                try:
                    currency = parts[1]
                    tenor = parts[2]
                    rate = float(parts[3])
                    year = int(parts[4])
                    month = int(parts[5])
                    day = int(parts[6])
                    if currency not in rates:
                        rates[currency] = {}
                    rates[currency][tenor] = rate
                    if header_date is None:
                        header_date = datetime.date(year, month, day)
                except (ValueError, IndexError) as e:
                    logging.warning("Skipping malformed data line: %s (%s)", line, e)

    if not rates:
        raise RuntimeError(f"No rate data found in interface file: {file_path}")

    return {"header_date": header_date, "rates": rates}


# =============================================================================
# WEBDRIVER MANAGEMENT
# =============================================================================

def create_webdriver(webdriver_path=None, headless=True):
    if webdriver is None:
        raise RuntimeError(
            "selenium is not installed. Install with: pip install selenium"
        )

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    if webdriver_path:
        service = Service(executable_path=webdriver_path)
    else:
        service = Service()

    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    return driver


# =============================================================================
# SHIBOR (CNY) RATE FETCHING
# =============================================================================

def fetch_shibor_rates(rate_date):
    if requests is None:
        raise RuntimeError(
            "requests is not installed. Install with: pip install requests"
        )

    date_str = rate_date.strftime("%Y-%m-%d")
    params = {"lang": "en", "startDate": date_str, "endDate": date_str}

    logging.info("Fetching SHIBOR rates for %s via API", date_str)

    try:
        response = requests.get(SHIBOR_API_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        raise RuntimeError(f"SHIBOR API request failed: {e}") from e

    records = data.get("records", [])
    if not records:
        raise RuntimeError(f"No SHIBOR data found for {date_str}")

    record = records[0]
    result = {}
    for tenor in ["1M", "3M", "6M", "9M", "1Y"]:
        value = record.get(tenor)
        if value is not None and str(value).strip():
            try:
                result[tenor] = float(value)
            except ValueError:
                logging.warning("Could not parse SHIBOR tenor %s value: %s", tenor, value)

    if not result:
        raise RuntimeError(f"No valid SHIBOR tenor rates found for {date_str}")

    logging.info("SHIBOR rates fetched: %s", result)
    return result


def fetch_shibor_rates_selenium(rate_date, driver):
    date_str = rate_date.strftime("%Y-%m-%d")
    logging.info("Fetching SHIBOR rates for %s via Selenium fallback", date_str)

    url = "https://www.shibor.org/shibor/web/html/shibor.html"
    driver.get(url)

    wait = WebDriverWait(driver, 15)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
    except TimeoutException:
        raise RuntimeError("SHIBOR page did not load within timeout")

    tables = driver.find_elements(By.CSS_SELECTOR, "table")
    result = {}
    tenor_keywords = {
        "1M": ["1m", "1 month", "1month"],
        "3M": ["3m", "3 month", "3month"],
        "6M": ["6m", "6 month", "6month"],
        "9M": ["9m", "9 month", "9month"],
        "1Y": ["1y", "1 year", "1year", "12m"],
    }

    for table in tables:
        rows = table.find_elements(By.TAG_NAME, "tr")
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 2:
                label = cells[0].text.strip().lower()
                for tenor, keywords in tenor_keywords.items():
                    if any(kw in label for kw in keywords):
                        try:
                            rate_text = cells[1].text.strip().replace("%", "")
                            result[tenor] = float(rate_text)
                        except ValueError:
                            pass

    if not result:
        raise RuntimeError(f"No SHIBOR rates found via Selenium for {date_str}")

    logging.info("SHIBOR rates fetched via Selenium: %s", result)
    return result


# =============================================================================
# EURIBOR (EUR) RATE FETCHING
# =============================================================================

def fetch_euribor_rates(rate_date, driver):
    date_str = rate_date.strftime("%Y-%m-%d")
    logging.info("Fetching Euribor rates for %s via Selenium", date_str)

    driver.get(EURIBOR_URL)

    wait = WebDriverWait(driver, 15)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
    except TimeoutException:
        raise RuntimeError("Euribor page did not load within timeout")

    tables = driver.find_elements(By.CSS_SELECTOR, "table")
    if not tables:
        raise RuntimeError("No tables found on Euribor page")

    target_date_formats = [
        rate_date.strftime("%-m/%-d/%Y"),
        rate_date.strftime("%m/%d/%Y"),
        rate_date.strftime("%d/%m/%Y"),
        rate_date.strftime("%-d/%-m/%Y"),
        rate_date.strftime("%Y-%m-%d"),
        rate_date.strftime("%d-%m-%Y"),
        rate_date.strftime("%B %-d, %Y"),
        rate_date.strftime("%b %-d, %Y"),
    ]

    result = {}
    maturity_map = {
        "1 week": None,
        "1 month": "1 month",
        "3 months": "3 months",
        "6 months": "6 months",
        "12 months": "12 months",
    }

    for table in tables:
        rows = table.find_elements(By.TAG_NAME, "tr")
        if not rows:
            continue

        header_cells = rows[0].find_elements(By.TAG_NAME, "th")
        if not header_cells:
            header_cells = rows[0].find_elements(By.TAG_NAME, "td")

        date_col_idx = None
        for idx, cell in enumerate(header_cells):
            cell_text = cell.text.strip()
            for fmt in target_date_formats:
                if fmt in cell_text:
                    date_col_idx = idx
                    break
            if date_col_idx is not None:
                break

        if date_col_idx is None:
            if len(header_cells) > 1:
                date_col_idx = 1
                logging.warning(
                    "Target date %s not found in Euribor table headers, "
                    "using first data column (most recent)",
                    date_str,
                )
            else:
                continue

        for row in rows[1:]:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) <= date_col_idx:
                continue
            label = cells[0].text.strip().lower()
            for mat_key, mapped in maturity_map.items():
                if mapped is not None and mat_key in label:
                    rate_text = cells[date_col_idx].text.strip()
                    rate_text = rate_text.replace("%", "").replace(",", ".").strip()
                    if rate_text and rate_text != "-":
                        try:
                            result[mapped] = float(rate_text)
                        except ValueError:
                            logging.warning(
                                "Could not parse Euribor rate for %s: %s",
                                mat_key,
                                rate_text,
                            )

        if result:
            break

    if not result:
        raise RuntimeError(
            f"No Euribor rates extracted for {date_str}. "
            "The page structure may have changed."
        )

    logging.info("Euribor rates fetched: %s", result)
    return result


# =============================================================================
# NZFMA (NZD) RATE FETCHING
# =============================================================================

def fetch_nzfma_rates(rate_date, driver):
    date_str = rate_date.strftime("%Y-%m-%d")
    logging.info("Fetching NZFMA rates for %s via Selenium", date_str)

    driver.get(NZFMA_URL)

    wait = WebDriverWait(driver, 15)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "select, input")))
    except TimeoutException:
        raise RuntimeError("NZFMA page did not load within timeout")

    try:
        selects = driver.find_elements(By.CSS_SELECTOR, "select")
        report_select = None
        for sel in selects:
            options = sel.find_elements(By.TAG_NAME, "option")
            for opt in options:
                opt_text = opt.text.strip().lower()
                if "bank bill" in opt_text or "bkbm" in opt_text:
                    report_select = sel
                    Select(report_select).select_by_visible_text(opt.text.strip())
                    logging.info("Selected report type: %s", opt.text.strip())
                    break
            if report_select is not None:
                break

        date_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='date']")
        date_formats_to_try = [
            rate_date.strftime("%d/%m/%Y"),
            rate_date.strftime("%m/%d/%Y"),
            rate_date.strftime("%Y-%m-%d"),
            rate_date.strftime("%d-%m-%Y"),
        ]

        for date_input in date_inputs:
            input_id = date_input.get_attribute("id") or ""
            input_name = date_input.get_attribute("name") or ""
            if "date" in input_id.lower() or "date" in input_name.lower():
                date_input.clear()
                date_input.send_keys(date_formats_to_try[0])
                logging.info("Entered date %s into field: %s", date_formats_to_try[0], input_id or input_name)
                break

        submit_buttons = driver.find_elements(By.CSS_SELECTOR, "input[type='submit'], button[type='submit'], input[value='Search'], input[value='Go']")
        if not submit_buttons:
            submit_buttons = driver.find_elements(By.XPATH, "//input[@type='submit'] | //button[contains(text(),'Search')] | //button[contains(text(),'Go')]")
        if submit_buttons:
            submit_buttons[0].click()
            logging.info("Clicked submit button")

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))

    except (TimeoutException, NoSuchElementException) as e:
        raise RuntimeError(f"NZFMA form interaction failed: {e}") from e

    result = {}
    tenor_keywords = {
        "1 Month": ["1 month", "30 day", "1m"],
        "2 Month": ["2 month", "60 day", "2m"],
        "3 Month": ["3 month", "90 day", "3m"],
        "4 Month": ["4 month", "120 day", "4m"],
        "5 Month": ["5 month", "150 day", "5m"],
        "6 Month": ["6 month", "180 day", "6m"],
    }

    tables = driver.find_elements(By.CSS_SELECTOR, "table")
    for table in tables:
        table_text = table.text.lower()
        if "bank bill" not in table_text and "bkbm" not in table_text and "reference" not in table_text:
            if len(tables) > 1:
                continue

        rows = table.find_elements(By.TAG_NAME, "tr")
        header_row = None
        avg_col_idx = None

        for row in rows:
            headers = row.find_elements(By.TAG_NAME, "th")
            if headers:
                for idx, h in enumerate(headers):
                    if "avg" in h.text.strip().lower() or "average" in h.text.strip().lower():
                        avg_col_idx = idx
                        break
                header_row = row
                break

        if avg_col_idx is None:
            avg_col_idx = 1

        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) <= avg_col_idx:
                continue
            label = cells[0].text.strip().lower()
            for tenor_key, keywords in tenor_keywords.items():
                if any(kw in label for kw in keywords):
                    rate_text = cells[avg_col_idx].text.strip()
                    rate_text = rate_text.replace("%", "").replace(",", ".").strip()
                    if rate_text and rate_text != "-":
                        try:
                            result[tenor_key] = float(rate_text)
                        except ValueError:
                            logging.warning(
                                "Could not parse NZFMA rate for %s: %s",
                                tenor_key,
                                rate_text,
                            )

        if result:
            break

    if not result:
        raise RuntimeError(
            f"No NZFMA rates extracted for {date_str}. "
            "The page structure may have changed or data may not be available yet."
        )

    logging.info("NZFMA rates fetched: %s", result)
    return result


# =============================================================================
# COMPARISON LOGIC
# =============================================================================

def compare_rates(interface_rates, published_rates, tenor_map, currency, tolerance=0.001):
    results = []
    for iface_tenor, pub_tenor in tenor_map.items():
        iface_rate = interface_rates.get(iface_tenor)
        pub_rate = published_rates.get(pub_tenor)

        if iface_rate is None:
            continue

        if pub_rate is None:
            results.append({
                "currency": currency,
                "tenor": iface_tenor,
                "published_tenor": pub_tenor,
                "interface_rate": iface_rate,
                "published_rate": None,
                "difference": None,
                "status": "UNAVAILABLE",
            })
            continue

        diff = abs(iface_rate - pub_rate)
        status = "MATCH" if diff <= tolerance else "MISMATCH"
        results.append({
            "currency": currency,
            "tenor": iface_tenor,
            "published_tenor": pub_tenor,
            "interface_rate": iface_rate,
            "published_rate": pub_rate,
            "difference": round(diff, 6),
            "status": status,
        })

    return results


# =============================================================================
# REPORT GENERATION
# =============================================================================

def build_comparison_report(check_date, results_by_currency, interface_files_used):
    sep = "=" * 80
    lines = []
    lines.append(sep)
    lines.append("ADB INTEREST RATE INDEX CHECK REPORT")
    lines.append(sep)
    lines.append(f"Check Date       : {check_date.isoformat()}")
    lines.append(f"Report Generated : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(sep)
    lines.append("")

    total_checks = 0
    total_matches = 0
    total_mismatches = 0
    total_unavailable = 0
    total_errors = 0
    mismatches = []

    source_labels = {
        "CNY": "SHIBOR",
        "EUR": "Euribor",
        "NZD": "NZFMA",
    }

    for currency in ["CNY", "EUR", "NZD"]:
        if currency not in results_by_currency:
            continue

        entry = results_by_currency[currency]
        label = source_labels.get(currency, currency)
        lines.append(f"--- {currency} ({label}) ---")

        if entry.get("status") == "ERROR":
            lines.append(f"  ERROR: {entry.get('message', 'Unknown error')}")
            lines.append("")
            total_errors += 1
            continue

        file_info = interface_files_used.get(currency, {})
        file_name = file_info.get("file_name", "N/A")
        file_date = file_info.get("file_date", "N/A")
        lag = LAG_DAYS.get(currency, 0)
        source = CURRENCY_SOURCES.get(currency, "N/A")

        lines.append(f"  Interface File   : {file_name} (Date: {file_date}, Lag: {lag} day{'s' if lag != 1 else ''})")
        lines.append(f"  Published Source : {source}")
        lines.append(f"  Rate Date        : {file_date}")
        lines.append("")

        comparisons = entry.get("comparisons", [])

        header = f"  {'Tenor':<10}{'Interface Rate':>16}{'Published Rate':>16}{'Difference':>14}{'Status':>14}"
        lines.append(header)
        lines.append(f"  {'-' * 8:<10}{'-' * 14:>16}{'-' * 14:>16}{'-' * 12:>14}{'-' * 10:>14}")

        for comp in comparisons:
            total_checks += 1
            tenor = comp["tenor"]
            iface_rate = f"{comp['interface_rate']:.4f}" if comp["interface_rate"] is not None else "N/A"

            if comp["status"] == "UNAVAILABLE":
                pub_rate = "N/A"
                diff = "N/A"
                total_unavailable += 1
            else:
                pub_rate = f"{comp['published_rate']:.4f}" if comp["published_rate"] is not None else "N/A"
                diff = f"{comp['difference']:.4f}" if comp["difference"] is not None else "N/A"
                if comp["status"] == "MATCH":
                    total_matches += 1
                elif comp["status"] == "MISMATCH":
                    total_mismatches += 1
                    mismatches.append({
                        "currency": currency,
                        "tenor": tenor,
                        "published_tenor": comp["published_tenor"],
                        "interface_rate": comp["interface_rate"],
                        "published_rate": comp["published_rate"],
                        "difference": comp["difference"],
                        "file_name": file_name,
                        "source": source,
                        "rate_date": file_date,
                    })

            status = comp["status"]
            lines.append(f"  {tenor:<10}{iface_rate:>16}{pub_rate:>16}{diff:>14}{status:>14}")

        lines.append("")

    overall_pass = total_mismatches == 0 and total_errors == 0
    overall_status = "PASS" if overall_pass else "FAIL"

    lines.append(sep)
    lines.append("SUMMARY")
    lines.append(sep)
    lines.append(f"Total Checks     : {total_checks}")
    lines.append(f"Matches          : {total_matches}")
    lines.append(f"Mismatches       : {total_mismatches}")
    lines.append(f"Unavailable      : {total_unavailable}")
    lines.append(f"Errors           : {total_errors}")
    lines.append(f"Overall Status   : {overall_status}")

    if mismatches:
        lines.append("")
        lines.append(sep)
        lines.append("MISMATCH DETAILS (for ITD notification)")
        lines.append(sep)
        lines.append("The following discrepancies require ITD correction:")
        lines.append("")
        for i, mm in enumerate(mismatches, 1):
            lines.append(f"  {i}. {mm['currency']} / {mm['tenor']} ({mm['published_tenor']})")
            lines.append(f"     - Interface File Rate  : {mm['interface_rate']:.4f}")
            lines.append(f"     - Published Rate       : {mm['published_rate']:.4f}")
            lines.append(f"     - Difference           : {mm['difference']:.4f}")
            lines.append(f"     - Interface File       : {mm['file_name']}")
            lines.append(f"     - Published Source     : {mm['source']}")
            lines.append(f"     - Rate Date            : {mm['rate_date']}")
            lines.append("")
        lines.append("ACTION: Email ITD with the above discrepancy details for correction.")

    lines.append(sep)
    lines.append(f"EXIT_CODE: {0 if overall_pass else 1}")

    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="ADB Interest Rate Index Checker - Compares interface file rates against published sources"
    )
    parser.add_argument(
        "check_date",
        type=str,
        help="Date to check in YYYY-MM-DD format",
    )
    parser.add_argument(
        "interface_folder",
        type=str,
        nargs="?",
        default=os.environ.get("ADB_INTERFACE_FOLDER", ""),
        help="Path to folder containing interface files",
    )
    parser.add_argument(
        "--currencies",
        type=str,
        default="CNY,EUR,NZD",
        help="Comma-separated list of currencies to check (default: CNY,EUR,NZD)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.001,
        help="Numeric tolerance for rate comparison (default: 0.001)",
    )
    parser.add_argument(
        "--webdriver-path",
        type=str,
        default=os.environ.get("ADB_WEBDRIVER_PATH"),
        help="Path to ChromeDriver executable",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser with visible window",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )

    try:
        check_date = datetime.datetime.strptime(args.check_date, "%Y-%m-%d").date()
    except ValueError:
        logging.error("Invalid date format: %s. Expected YYYY-MM-DD.", args.check_date)
        sys.exit(1)

    interface_folder = args.interface_folder
    if not interface_folder:
        logging.error("Interface folder not specified. Provide as argument or set ADB_INTERFACE_FOLDER.")
        sys.exit(1)

    currencies = [c.strip().upper() for c in args.currencies.split(",")]
    tolerance = args.tolerance
    headless = not args.no_headless

    logging.info("Starting ADB Interest Rate Index Check for %s", check_date.isoformat())
    logging.info("Currencies: %s | Tolerance: %s", currencies, tolerance)

    results_by_currency = {}
    interface_files_used = {}
    driver = None
    needs_browser = any(c in currencies for c in ["EUR", "NZD"])

    try:
        if needs_browser:
            try:
                driver = create_webdriver(
                    webdriver_path=args.webdriver_path,
                    headless=headless,
                )
                logging.info("WebDriver created successfully")
            except Exception as e:
                logging.error("Failed to create WebDriver: %s", e)
                for c in currencies:
                    if c in ["EUR", "NZD"]:
                        results_by_currency[c] = {
                            "status": "ERROR",
                            "message": f"WebDriver creation failed: {e}",
                        }
                currencies = [c for c in currencies if c not in ["EUR", "NZD"]]

        for currency in currencies:
            logging.info("Processing %s...", currency)

            try:
                interface_date = calculate_interface_date(check_date, currency)
                logging.info(
                    "%s: Interface date = %s (lag: %d days)",
                    currency,
                    interface_date.isoformat(),
                    LAG_DAYS.get(currency, 0),
                )

                file_path, actual_date = find_interface_file(interface_folder, interface_date)
                file_name = Path(file_path).name
                logging.info("%s: Using interface file: %s", currency, file_name)

                interface_files_used[currency] = {
                    "file_name": file_name,
                    "file_path": file_path,
                    "file_date": actual_date.isoformat(),
                }

                file_data = parse_interface_file(file_path)
                if currency not in file_data["rates"]:
                    for alt_pattern in INTERFACE_FILE_PATTERNS:
                        alt_name = alt_pattern.format(date=format_date_for_filename(actual_date))
                        alt_path = Path(interface_folder) / alt_name
                        if alt_path.is_file() and str(alt_path) != file_path:
                            alt_data = parse_interface_file(str(alt_path))
                            if currency in alt_data["rates"]:
                                file_data = alt_data
                                file_name = alt_path.name
                                interface_files_used[currency]["file_name"] = file_name
                                interface_files_used[currency]["file_path"] = str(alt_path)
                                logging.info("%s: Found in alternate file: %s", currency, file_name)
                                break

                if currency not in file_data["rates"]:
                    raise RuntimeError(
                        f"Currency {currency} not found in interface file(s) for date {actual_date.isoformat()}"
                    )

                interface_rates = file_data["rates"][currency]
                logging.info("%s: Interface rates: %s", currency, interface_rates)

                if currency == "CNY":
                    try:
                        published_rates = fetch_shibor_rates(actual_date)
                    except RuntimeError as e:
                        logging.warning("SHIBOR API failed: %s. Trying Selenium fallback.", e)
                        if driver is None:
                            driver = create_webdriver(
                                webdriver_path=args.webdriver_path,
                                headless=headless,
                            )
                        published_rates = fetch_shibor_rates_selenium(actual_date, driver)
                elif currency == "EUR":
                    published_rates = fetch_euribor_rates(actual_date, driver)
                elif currency == "NZD":
                    published_rates = fetch_nzfma_rates(actual_date, driver)
                else:
                    raise RuntimeError(f"Unsupported currency: {currency}")

                tenor_map = TENOR_MAPS.get(currency, {})
                comparisons = compare_rates(
                    interface_rates, published_rates, tenor_map, currency, tolerance
                )
                results_by_currency[currency] = {"comparisons": comparisons}

            except FileNotFoundError as e:
                logging.error("%s: Interface file not found: %s", currency, e)
                results_by_currency[currency] = {"status": "ERROR", "message": str(e)}
            except RuntimeError as e:
                logging.error("%s: %s", currency, e)
                results_by_currency[currency] = {"status": "ERROR", "message": str(e)}
            except Exception as e:
                logging.error("%s: Unexpected error: %s", currency, e)
                results_by_currency[currency] = {"status": "ERROR", "message": str(e)}

    finally:
        if driver is not None:
            try:
                driver.quit()
                logging.info("WebDriver closed")
            except Exception:
                pass

    report = build_comparison_report(check_date, results_by_currency, interface_files_used)
    print(report)

    has_mismatch = any(
        any(c.get("status") == "MISMATCH" for c in entry.get("comparisons", []))
        for entry in results_by_currency.values()
        if entry.get("status") != "ERROR"
    )
    has_error = any(
        entry.get("status") == "ERROR" for entry in results_by_currency.values()
    )

    sys.exit(1 if (has_mismatch or has_error) else 0)


if __name__ == "__main__":
    main()
