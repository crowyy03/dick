import re


def mask_url_secrets(url: str) -> str:
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", url)


def mask_long_string(s: str, max_len: int = 24) -> str:
    if len(s) <= max_len:
        return s
    return s[:8] + "…" + s[-8:]
