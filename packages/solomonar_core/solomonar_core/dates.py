"""Parsare de date în română (luni scrise în text) — partajat de connectoarele de parlament.

Ex.: "n. 8 sep. 1977" → date(1977, 9, 8). Tolerează cedilă/virgulă-jos și abrevieri.
"""

from __future__ import annotations

import re
from datetime import date

RE_BIRTH = re.compile(r"n\.\s*(\d{1,2})\s+([a-zăâîşţșț\.]+)\s+(\d{4})", re.IGNORECASE)

ROMANIAN_MONTHS = {
    "ian": 1, "ianuarie": 1, "feb": 2, "februarie": 2, "mar": 3, "mart": 3, "martie": 3,
    "apr": 4, "aprilie": 4, "mai": 5, "iun": 6, "iunie": 6, "iul": 7, "iulie": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "septembrie": 9, "oct": 10, "octombrie": 10,
    "noi": 11, "nov": 11, "noiembrie": 11, "dec": 12, "decembrie": 12,
}


def parse_ro_date(day_str: str, month_str: str, year_str: str) -> date | None:
    m = (
        month_str.rstrip(".").lower()
        .replace("ş", "s").replace("ţ", "t").replace("ș", "s").replace("ț", "t")
    )
    month = ROMANIAN_MONTHS.get(m) or ROMANIAN_MONTHS.get(m[:3])
    if month is None:
        return None
    try:
        return date(int(year_str), month, int(day_str))
    except (ValueError, TypeError):
        return None
