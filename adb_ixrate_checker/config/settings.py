import os
from dotenv import load_dotenv

load_dotenv()

DEFAULTS = {
    "currencies": os.getenv("ADB_CURRENCIES", "CNY,EUR,NZD"),
    "tolerance": float(os.getenv("ADB_TOLERANCE", "0.001")),
    "interface_folder": os.getenv("ADB_INTERFACE_FOLDER", ""),
    "webdriver_path": os.getenv("ADB_WEBDRIVER_PATH"),
    "headless": os.getenv("ADB_HEADLESS", "true").lower() == "true",
    "log_level": os.getenv("ADB_LOG_LEVEL", "INFO"),
    "max_fallback_days": int(os.getenv("ADB_MAX_FALLBACK_DAYS", "3")),
    "page_load_timeout": int(os.getenv("ADB_PAGE_LOAD_TIMEOUT", "30")),
    "wait_timeout": int(os.getenv("ADB_WAIT_TIMEOUT", "15")),
    "api_request_timeout": int(os.getenv("ADB_API_REQUEST_TIMEOUT", "30")),
}

LAG_DAYS = {
    "CNY": int(os.getenv("ADB_LAG_CNY", "1")),
    "EUR": int(os.getenv("ADB_LAG_EUR", "2")),
    "NZD": int(os.getenv("ADB_LAG_NZD", "0")),
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

SHIBOR_API_URL = os.getenv(
    "ADB_SHIBOR_API_URL",
    "https://www.shibor.org/ags/ms/cm-u-bk-shibor/ShiborHis",
)
SHIBOR_WEB_URL = os.getenv(
    "ADB_SHIBOR_WEB_URL",
    "https://www.shibor.org/shibor/web/html/shibor.html",
)
EURIBOR_URL = os.getenv(
    "ADB_EURIBOR_URL",
    "https://www.euribor-rates.eu/en/current-euribor-rates/",
)
NZFMA_URL = os.getenv(
    "ADB_NZFMA_URL",
    "https://www.nzfma.org/data/search.aspx",
)

CURRENCY_SOURCES = {
    "CNY": f"SHIBOR API ({SHIBOR_API_URL})",
    "EUR": EURIBOR_URL,
    "NZD": NZFMA_URL,
}
