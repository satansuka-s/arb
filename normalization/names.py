from __future__ import annotations

import re
import unicodedata


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower().replace("ё", "е")
    value = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", value)
    value = re.sub(r"[^\w\s]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def compact_name(value: str) -> str:
    return normalize_name(value).replace(" ", "")
