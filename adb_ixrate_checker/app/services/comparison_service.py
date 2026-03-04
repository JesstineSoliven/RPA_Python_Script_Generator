import logging
import datetime

from config.settings import LAG_DAYS, CURRENCY_SOURCES, TENOR_MAPS

logger = logging.getLogger(__name__)


def compare_rates(interface_rates, published_rates, tenor_map, currency,
                  tolerance=0.001):
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


def build_result_summary(check_date, results_by_currency, interface_files_used):
    total_checks = 0
    total_matches = 0
    total_mismatches = 0
    total_unavailable = 0
    total_errors = 0
    all_mismatches = []

    source_labels = {
        "CNY": "SHIBOR",
        "EUR": "Euribor",
        "NZD": "NZFMA",
    }

    currencies_detail = {}

    for currency in ["CNY", "EUR", "NZD"]:
        if currency not in results_by_currency:
            continue

        entry = results_by_currency[currency]

        if entry.get("status") == "ERROR":
            currencies_detail[currency] = {
                "source": source_labels.get(currency, currency),
                "status": "ERROR",
                "message": entry.get("message", "Unknown error"),
            }
            total_errors += 1
            continue

        file_info = interface_files_used.get(currency, {})
        comparisons = entry.get("comparisons", [])
        currency_mismatches = 0

        for comp in comparisons:
            total_checks += 1
            if comp["status"] == "UNAVAILABLE":
                total_unavailable += 1
            elif comp["status"] == "MATCH":
                total_matches += 1
            elif comp["status"] == "MISMATCH":
                total_mismatches += 1
                currency_mismatches += 1
                all_mismatches.append({
                    "currency": currency,
                    "tenor": comp["tenor"],
                    "published_tenor": comp["published_tenor"],
                    "interface_rate": comp["interface_rate"],
                    "published_rate": comp["published_rate"],
                    "difference": comp["difference"],
                    "interface_file": file_info.get("file_name", "N/A"),
                    "source": CURRENCY_SOURCES.get(currency, "N/A"),
                    "rate_date": file_info.get("file_date", "N/A"),
                })

        currency_status = "PASS" if currency_mismatches == 0 else "FAIL"

        currencies_detail[currency] = {
            "source": source_labels.get(currency, currency),
            "interface_file": file_info.get("file_name", "N/A"),
            "file_date": file_info.get("file_date", "N/A"),
            "lag_days": LAG_DAYS.get(currency, 0),
            "published_source": CURRENCY_SOURCES.get(currency, "N/A"),
            "comparisons": comparisons,
            "status": currency_status,
        }

    overall_pass = total_mismatches == 0 and total_errors == 0
    overall_status = "PASS" if overall_pass else "FAIL"

    return {
        "check_date": check_date.isoformat(),
        "report_generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "currencies": currencies_detail,
        "summary": {
            "total_checks": total_checks,
            "matches": total_matches,
            "mismatches": total_mismatches,
            "unavailable": total_unavailable,
            "errors": total_errors,
            "overall_status": overall_status,
        },
        "mismatches": all_mismatches,
    }


def determine_exit_status(result_summary):
    return 0 if result_summary["summary"]["overall_status"] == "PASS" else 1
