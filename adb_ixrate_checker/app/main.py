import logging

from app.services.interface_file_service import find_and_parse_interface_file
from app.services.rate_fetcher_service import fetch_published_rates
from app.services.comparison_service import (
    compare_rates,
    build_result_summary,
)
from app.services.webdriver_service import WebDriverManager
from app.utils.date_helpers import calculate_interface_date
from app.exceptions import AdbIxrateError
from config.settings import LAG_DAYS, TENOR_MAPS

logger = logging.getLogger(__name__)


def run_check(config):
    logger.info(
        "Starting ADB Interest Rate Index Check for %s",
        config.check_date.isoformat(),
    )
    logger.info("Currencies: %s | Tolerance: %s", config.currencies, config.tolerance)

    results_by_currency = {}
    interface_files_used = {}

    with WebDriverManager(
        webdriver_path=config.webdriver_path,
        headless=config.headless,
        page_load_timeout=config.page_load_timeout,
    ) as wdm:
        for currency in config.currencies:
            result = _process_currency(config, currency, wdm)
            results_by_currency[currency] = result["result"]
            if "file_info" in result:
                interface_files_used[currency] = result["file_info"]

    return build_result_summary(
        config.check_date, results_by_currency, interface_files_used
    )


def _process_currency(config, currency, wdm):
    logger.info("Processing %s...", currency)

    try:
        interface_date = calculate_interface_date(config.check_date, currency)
        logger.info(
            "%s: Interface date = %s (lag: %d days)",
            currency,
            interface_date.isoformat(),
            LAG_DAYS.get(currency, 0),
        )

        interface_rates, file_info = find_and_parse_interface_file(
            config.interface_folder,
            interface_date,
            currency,
            max_fallback_days=config.max_fallback_days,
        )
        logger.info("%s: Interface rates: %s", currency, interface_rates)

        actual_date = interface_date
        published_rates = fetch_published_rates(
            currency, actual_date, wdm, config
        )

        tenor_map = TENOR_MAPS.get(currency, {})
        comparisons = compare_rates(
            interface_rates, published_rates, tenor_map, currency, config.tolerance
        )

        return {
            "result": {"comparisons": comparisons},
            "file_info": file_info,
        }

    except AdbIxrateError as e:
        logger.error("%s: %s", currency, e)
        return {"result": {"status": "ERROR", "message": str(e)}}
    except Exception as e:
        logger.error("%s: Unexpected error: %s", currency, e)
        return {"result": {"status": "ERROR", "message": str(e)}}
