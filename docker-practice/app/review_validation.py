"""
Автоматическая проверка отзывов без ручной модерации:
- ссылки и типичный спам (URL, e-mail, короткие ссылки);
- ненормативная лексика (базовый список, расширяемый);
- подозрительные паттерны (чрезмерное повторение символов).
"""
from __future__ import annotations

import re
from typing import Optional

# --- Ссылки и спам ---
_URL_SCHEMES = re.compile(
    r"(https?://|ftp://|ftps://|//[^\s]+|www\.|t\.me/|telegram\.me/|"
    r"vk\.com/|wa\.me/|bit\.ly/|goo\.gl/|tinyurl\.com/|youtu\.be/|"
    r"discord\.gg/|discord\.com/)",
    re.IGNORECASE,
)
# Домен вида something.tld (латиница), минимум 2 символа в имени
_DOMAIN_LIKE = re.compile(
    r"(?<![\w/])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:ru|com|net|org|io|app|me|info|biz|рф|su|xyz|online|site|store)\b",
    re.IGNORECASE,
)
_EMAIL_LIKE = re.compile(r"\S+@\S+\.\S+")
_IP_LIKE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
)

# --- Мат и грубость (корни/слова; дополняйте список при необходимости) ---
# Сопоставление по нижнему регистру, границы слова где уместно.
_PROFANITY = (
    "хуй",
    "хуе",
    "хуё",
    "пизд",
    "ебан",
    "ебёт",
    "ебет",
    "ебал",
    "ебу",
    "ёб",
    "ебл",
    "бля",
    "сука",
    "мудак",
    "мудил",
    "говно",
    "залуп",
    "пидор",
    "пидр",
    "fuck",
    "shit",
    "bitch",
)

# Повтор одного символа подряд (спам / обход фильтров)
_REPEAT_SPAM = re.compile(r"(.)\1{9,}")


def _normalize_for_profanity(s: str) -> str:
    """Упрощённая нормализация: убрать частые замены букв в мате."""
    t = s.lower()
    for a, b in (("ё", "е"), ("@", "а"), ("0", "о"), ("3", "з"), ("$", "с")):
        t = t.replace(a, b)
    return t


def _contains_profanity(text: str) -> bool:
    n = _normalize_for_profanity(text)
    for stem in _PROFANITY:
        if stem in n:
            return True
    return False


def _contains_links_or_spam(text: str) -> bool:
    combined = f"{text} "
    if _URL_SCHEMES.search(combined):
        return True
    if _EMAIL_LIKE.search(combined):
        return True
    if _IP_LIKE.search(combined):
        return True
    if _DOMAIN_LIKE.search(combined):
        return True
    return False


def _contains_repeat_spam(text: str) -> bool:
    return bool(_REPEAT_SPAM.search(text))


def validate_review_text(*, name: str, text: str) -> Optional[str]:
    """
    Проверяет имя и текст отзыва.
    Возвращает None если всё ок, иначе — короткое сообщение об ошибке для пользователя.
    """
    check = f"{name}\n{text}"

    if _contains_repeat_spam(name) or _contains_repeat_spam(text):
        return "Слишком много повторяющихся символов — похоже на спам."

    if _contains_links_or_spam(check):
        return "Нельзя указывать ссылки, e-mail и похожие на них фрагменты."

    if _contains_profanity(check):
        return "Пожалуйста, без ненормативной лексики."

    return None
