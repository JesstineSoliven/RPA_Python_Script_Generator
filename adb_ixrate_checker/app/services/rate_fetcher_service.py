import logging

from app.exceptions import RateFetchError
from config.settings import (
    SHIBOR_API_URL,
    SHIBOR_WEB_URL,
    EURIBOR_URL,
    NZFMA_URL,
    DEFAULTS,
)

try:
    import requests
except ImportError:
    requests = None

try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait, Select
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
except ImportError:
    pass

logger = logging.getLogger(__name__)


def fetch_published_rates(currency, rate_date, wdm, config):
    if currency == "CNY":
        try:
            return _fetch_shibor_rates_api(rate_date, config)
        except RateFetchError as e:
            logger.warning("SHIBOR API failed: %s. Trying Selenium fallback.", e)
            driver = wdm.get_driver()
            return _fetch_shibor_rates_selenium(rate_date, driver, config)
    elif currency == "EUR":
        driver = wdm.get_driver()
        return _fetch_euribor_rates(rate_date, driver, config)
    elif currency == "NZD":
        driver = wdm.get_driver()
        return _fetch_nzfma_rates(rate_date, driver, config)
    else:
        raise RateFetchError(f"Unsupported currency: {currency}")


def _fetch_shibor_rates_api(rate_date, config):
    if requests is None:
        raise RateFetchError(
            "requests is not installed. Install with: pip install requests"
        )

    date_str = rate_date.strftime("%Y-%m-%d")
    params = {"lang": "en", "startDate": date_str, "endDate": date_str}
    timeout = getattr(config, "api_request_timeout", DEFAULTS["api_request_timeout"])

    logger.info("Fetching SHIBOR rates for %s via API", date_str)

    try:
        response = requests.get(SHIBOR_API_URL, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        raise RateFetchError(f"SHIBOR API request failed: {e}") from e

    records = data.get("records", [])
    if not records:
        raise RateFetchError(f"No SHIBOR data found for {date_str}")

    record = records[0]
    result = {}
    for tenor in ["1M", "3M", "6M", "9M", "1Y"]:
        value = record.get(tenor)
        if value is not None and str(value).strip():
            try:
                result[tenor] = float(value)
            except ValueError:
                logger.warning(
                    "Could not parse SHIBOR tenor %s value: %s", tenor, value
                )

    if not result:
        raise RateFetchError(f"No valid SHIBOR tenor rates found for {date_str}")

    logger.info("SHIBOR rates fetched: %s", result)
    return result


def _fetch_shibor_rates_selenium(rate_date, driver, config):
    date_str = rate_date.strftime("%Y-%m-%d")
    logger.info("Fetching SHIBOR rates for %s via Selenium fallback", date_str)

    wait_timeout = getattr(config, "wait_timeout", DEFAULTS["wait_timeout"])
    driver.get(SHIBOR_WEB_URL)

    wait = WebDriverWait(driver, wait_timeout)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
    except TimeoutException:
        raise RateFetchError("SHIBOR page did not load within timeout")

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
        raise RateFetchError(
            f"No SHIBOR rates found via Selenium for {date_str}"
        )

    logger.info("SHIBOR rates fetched via Selenium: %s", result)
    return result


def _fetch_euribor_rates(rate_date, driver, config):
    date_str = rate_date.strftime("%Y-%m-%d")
    logger.info("Fetching Euribor rates for %s via Selenium", date_str)

    wait_timeout = getattr(config, "wait_timeout", DEFAULTS["wait_timeout"])
    driver.get(EURIBOR_URL)

    wait = WebDriverWait(driver, wait_timeout)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
    except TimeoutException:
        raise RateFetchError("Euribor page did not load within timeout")

    tables = driver.find_elements(By.CSS_SELECTOR, "table")
    if not tables:
        raise RateFetchError("No tables found on Euribor page")

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
                logger.warning(
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
                            logger.warning(
                                "Could not parse Euribor rate for %s: %s",
                                mat_key,
                                rate_text,
                            )

        if result:
            break

    if not result:
        raise RateFetchError(
            f"No Euribor rates extracted for {date_str}. "
            "The page structure may have changed."
        )

    logger.info("Euribor rates fetched: %s", result)
    return result


def _fetch_nzfma_rates(rate_date, driver, config):
    date_str = rate_date.strftime("%Y-%m-%d")
    logger.info("Fetching NZFMA rates for %s via Selenium", date_str)

    wait_timeout = getattr(config, "wait_timeout", DEFAULTS["wait_timeout"])
    driver.get(NZFMA_URL)

    wait = WebDriverWait(driver, wait_timeout)
    try:
        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "select, input"))
        )
    except TimeoutException:
        raise RateFetchError("NZFMA page did not load within timeout")

    try:
        selects = driver.find_elements(By.CSS_SELECTOR, "select")
        report_select = None
        for sel in selects:
            options = sel.find_elements(By.TAG_NAME, "option")
            for opt in options:
                opt_text = opt.text.strip().lower()
                if "bank bill" in opt_text or "bkbm" in opt_text:
                    report_select = sel
                    Select(report_select).select_by_visible_text(
                        opt.text.strip()
                    )
                    logger.info("Selected report type: %s", opt.text.strip())
                    break
            if report_select is not None:
                break

        date_inputs = driver.find_elements(
            By.CSS_SELECTOR, "input[type='text'], input[type='date']"
        )
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
                logger.info(
                    "Entered date %s into field: %s",
                    date_formats_to_try[0],
                    input_id or input_name,
                )
                break

        submit_buttons = driver.find_elements(
            By.CSS_SELECTOR,
            "input[type='submit'], button[type='submit'], "
            "input[value='Search'], input[value='Go']",
        )
        if not submit_buttons:
            submit_buttons = driver.find_elements(
                By.XPATH,
                "//input[@type='submit'] | "
                "//button[contains(text(),'Search')] | "
                "//button[contains(text(),'Go')]",
            )
        if submit_buttons:
            submit_buttons[0].click()
            logger.info("Clicked submit button")

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))

    except (TimeoutException, NoSuchElementException) as e:
        raise RateFetchError(f"NZFMA form interaction failed: {e}") from e

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
        if (
            "bank bill" not in table_text
            and "bkbm" not in table_text
            and "reference" not in table_text
        ):
            if len(tables) > 1:
                continue

        rows = table.find_elements(By.TAG_NAME, "tr")
        avg_col_idx = None

        for row in rows:
            headers = row.find_elements(By.TAG_NAME, "th")
            if headers:
                for idx, h in enumerate(headers):
                    h_text = h.text.strip().lower()
                    if "avg" in h_text or "average" in h_text:
                        avg_col_idx = idx
                        break
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
                    rate_text = (
                        rate_text.replace("%", "").replace(",", ".").strip()
                    )
                    if rate_text and rate_text != "-":
                        try:
                            result[tenor_key] = float(rate_text)
                        except ValueError:
                            logger.warning(
                                "Could not parse NZFMA rate for %s: %s",
                                tenor_key,
                                rate_text,
                            )

        if result:
            break

    if not result:
        raise RateFetchError(
            f"No NZFMA rates extracted for {date_str}. "
            "The page structure may have changed or data may not be available yet."
        )

    logger.info("NZFMA rates fetched: %s", result)
    return result
