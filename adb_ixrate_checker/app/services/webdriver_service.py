import logging

from app.exceptions import WebDriverError

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
except ImportError:
    webdriver = None

logger = logging.getLogger(__name__)


class WebDriverManager:
    def __init__(self, webdriver_path=None, headless=True, page_load_timeout=30):
        self._webdriver_path = webdriver_path
        self._headless = headless
        self._page_load_timeout = page_load_timeout
        self._driver = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def get_driver(self):
        if self._driver is None:
            self._driver = self._create_driver()
        return self._driver

    def close(self):
        if self._driver is not None:
            try:
                self._driver.quit()
                logger.info("WebDriver closed")
            except Exception:
                pass
            self._driver = None

    def _create_driver(self):
        if webdriver is None:
            raise WebDriverError(
                "selenium is not installed. Install with: pip install selenium"
            )

        try:
            options = Options()
            if self._headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-gpu")
            options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )

            if self._webdriver_path:
                service = Service(executable_path=self._webdriver_path)
            else:
                service = Service()

            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(self._page_load_timeout)
            logger.info("WebDriver created successfully")
            return driver
        except Exception as e:
            raise WebDriverError(f"Failed to create WebDriver: {e}") from e
