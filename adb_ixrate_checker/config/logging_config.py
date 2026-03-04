import os
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE_PATH = LOG_DIR / "app.log"
LOG_LEVEL = os.getenv("ADB_LOG_LEVEL", "INFO")
