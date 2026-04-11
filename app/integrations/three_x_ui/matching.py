"""Сопоставление идентификаторов клиента с панелью (разный регистр, пробелы, UUID)."""

from __future__ import annotations


def normalize_panel_email(s: str | None) -> str:
    return (s or "").strip().casefold()


def emails_match_panel(a: str | None, b: str | None) -> bool:
    return normalize_panel_email(a) == normalize_panel_email(b)


def normalize_panel_uuid(u: str | None) -> str:
    return (u or "").replace("-", "").strip().lower()
