import datetime

from config.settings import LAG_DAYS


def calculate_interface_date(check_date, currency):
    lag = LAG_DAYS.get(currency, 0)
    return check_date - datetime.timedelta(days=lag)


def format_date_for_filename(dt):
    return dt.strftime("%Y%m%d")
