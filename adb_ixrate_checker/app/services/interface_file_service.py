import logging
import datetime
from pathlib import Path

from app.exceptions import InterfaceFileNotFoundError, InterfaceFileParseError
from app.utils.date_helpers import format_date_for_filename
from config.settings import INTERFACE_FILE_PATTERNS

logger = logging.getLogger(__name__)


def find_interface_file(folder, target_date, max_fallback_days=3):
    folder_path = Path(folder)
    if not folder_path.is_dir():
        raise InterfaceFileNotFoundError(
            f"Interface folder does not exist: {folder}"
        )

    for day_offset in range(max_fallback_days + 1):
        search_date = target_date - datetime.timedelta(days=day_offset)
        date_str = format_date_for_filename(search_date)
        for pattern in INTERFACE_FILE_PATTERNS:
            file_name = pattern.format(date=date_str)
            file_path = folder_path / file_name
            if file_path.is_file():
                if day_offset > 0:
                    logger.warning(
                        "Interface file not found for %s, using fallback date %s",
                        target_date.isoformat(),
                        search_date.isoformat(),
                    )
                return str(file_path), search_date

    raise InterfaceFileNotFoundError(
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
                    logger.warning(
                        "Skipping malformed data line: %s (%s)", line, e
                    )

    if not rates:
        raise InterfaceFileParseError(
            f"No rate data found in interface file: {file_path}"
        )

    return {"header_date": header_date, "rates": rates}


def find_and_parse_interface_file(interface_folder, interface_date, currency,
                                  max_fallback_days=3):
    file_path, actual_date = find_interface_file(
        interface_folder, interface_date, max_fallback_days
    )
    file_name = Path(file_path).name
    logger.info("%s: Using interface file: %s", currency, file_name)

    file_data = parse_interface_file(file_path)

    if currency not in file_data["rates"]:
        date_str = format_date_for_filename(actual_date)
        for pattern in INTERFACE_FILE_PATTERNS:
            alt_name = pattern.format(date=date_str)
            alt_path = Path(interface_folder) / alt_name
            if alt_path.is_file() and str(alt_path) != file_path:
                alt_data = parse_interface_file(str(alt_path))
                if currency in alt_data["rates"]:
                    file_data = alt_data
                    file_name = alt_path.name
                    file_path = str(alt_path)
                    logger.info(
                        "%s: Found in alternate file: %s", currency, file_name
                    )
                    break

    if currency not in file_data["rates"]:
        raise InterfaceFileParseError(
            f"Currency {currency} not found in interface file(s) "
            f"for date {actual_date.isoformat()}"
        )

    file_info = {
        "file_name": file_name,
        "file_path": file_path,
        "file_date": actual_date.isoformat(),
    }

    return file_data["rates"][currency], file_info
