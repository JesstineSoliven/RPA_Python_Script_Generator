import datetime

from app.exceptions import ConfigurationError
from config.settings import DEFAULTS


class AppConfig:
    def __init__(self):
        self.check_date = None
        self.interface_folder = ""
        self.currencies = []
        self.tolerance = 0.001
        self.webdriver_path = None
        self.headless = True
        self.log_level = "INFO"
        self.max_fallback_days = 3
        self.page_load_timeout = 30
        self.wait_timeout = 15
        self.api_request_timeout = 30


def load_config(args):
    config = AppConfig()

    try:
        config.check_date = datetime.datetime.strptime(
            args.check_date, "%Y-%m-%d"
        ).date()
    except ValueError:
        raise ConfigurationError(
            f"Invalid date format: {args.check_date}. Expected YYYY-MM-DD."
        )

    config.interface_folder = args.interface_folder or DEFAULTS["interface_folder"]
    if not config.interface_folder:
        raise ConfigurationError(
            "Interface folder not specified. "
            "Provide as argument or set ADB_INTERFACE_FOLDER in .env."
        )

    currencies_str = args.currencies or DEFAULTS["currencies"]
    config.currencies = [c.strip().upper() for c in currencies_str.split(",")]

    config.tolerance = (
        args.tolerance if args.tolerance is not None else DEFAULTS["tolerance"]
    )
    config.webdriver_path = args.webdriver_path or DEFAULTS["webdriver_path"]
    config.headless = not args.no_headless if hasattr(args, "no_headless") else DEFAULTS["headless"]
    config.log_level = args.log_level or DEFAULTS["log_level"]
    config.max_fallback_days = DEFAULTS["max_fallback_days"]
    config.page_load_timeout = DEFAULTS["page_load_timeout"]
    config.wait_timeout = DEFAULTS["wait_timeout"]
    config.api_request_timeout = DEFAULTS["api_request_timeout"]

    return config
