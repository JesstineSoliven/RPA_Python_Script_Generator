import sys
import os
import argparse
import logging
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.logger import setup_logging
from app.config import load_config
from app.main import run_check
from app.exceptions import AdbIxrateError
from app.services.comparison_service import determine_exit_status
from app.utils.output_helpers import print_success, print_error


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="ADB Interest Rate Index Checker - "
        "Compares interface file rates against published sources"
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
        default=None,
        help="Comma-separated list of currencies to check (default: CNY,EUR,NZD)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help="Numeric tolerance for rate comparison (default: 0.001)",
    )
    parser.add_argument(
        "--webdriver-path",
        type=str,
        default=None,
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
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    log_level = args.log_level or os.environ.get("ADB_LOG_LEVEL", "INFO")
    setup_logging(log_level)

    logger = logging.getLogger(__name__)

    try:
        config = load_config(args)
        result = run_check(config)
        exit_code = determine_exit_status(result)

        if exit_code == 0:
            print_success(
                "All interest rate index checks passed.", result
            )
        else:
            print_success(
                "Interest rate index check completed with issues.", result
            )

        sys.exit(exit_code)

    except AdbIxrateError as e:
        logger.error("Application error: %s", e)
        logger.debug(traceback.format_exc())
        print_error(str(e))
        sys.exit(1)

    except Exception as e:
        logger.error("Unexpected error: %s", e)
        logger.error(traceback.format_exc())
        print_error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
