"""
Unit tests for app/review_validation.py.

All tests are pure-logic: no database, no HTTP client.
validate_review_text(*, name, text) returns:
  - None  → input is clean
  - str   → human-readable rejection reason

Check order inside the function:
  1. Repeat-spam  (10+ identical consecutive chars in name OR text)
  2. Links / spam (URLs, e-mails, IP addresses, domain-like patterns)
  3. Profanity    (Russian & English roots, with normalization)
"""
from __future__ import annotations

import pytest

from app.review_validation import validate_review_text

# ── helpers ────────────────────────────────────────────────────────────────────

def _ok(name: str = "Ольга", text: str = "Прекрасный букет, советую!") -> None:
    """Assert that the given name+text is accepted."""
    assert validate_review_text(name=name, text=text) is None


def _bad(name: str = "User", text: str = "bad text") -> str:
    """Assert that the given name+text is rejected and return the reason."""
    result = validate_review_text(name=name, text=text)
    assert result is not None, "Expected rejection but got None"
    return result


# ══════════════════════════════════════════════════════════════════════════════
# VALID INPUTS
# ══════════════════════════════════════════════════════════════════════════════

class TestValidInputs:
    def test_plain_russian_text(self):
        _ok(name="Ольга", text="Очень красивые цветы, буду заказывать ещё.")

    def test_plain_english_text(self):
        _ok(name="Anna", text="Great bouquet and fast delivery.")

    def test_numbers_in_text_are_allowed(self):
        _ok(name="User1", text="Ordered 3 times, always 5 stars quality.")

    def test_punctuation_allowed(self):
        _ok(name="A-B", text="Wow... amazing! Totally 10/10.")

    def test_hyphen_in_name_allowed(self):
        _ok(name="Мария-Иванова", text="Цветы свежие, упаковка аккуратная.")

    def test_nine_identical_chars_in_text_allowed(self):
        # Threshold is 10+; 9 consecutive identical chars must pass.
        _ok(name="User", text="aaaaaaaaa nice.")

    def test_nine_identical_chars_in_name_allowed(self):
        _ok(name="aaaaaaaaa", text="Good product.")


# ══════════════════════════════════════════════════════════════════════════════
# REPEAT-SPAM DETECTION
# ══════════════════════════════════════════════════════════════════════════════

class TestRepeatSpam:
    def test_ten_same_chars_in_text_rejected(self):
        result = _bad(text="aaaaaaaaaa")
        assert result == "Слишком много повторяющихся символов — похоже на спам."

    def test_eleven_same_chars_rejected(self):
        _bad(text="aaaaaaaaaaa")

    def test_repeat_spam_in_name_rejected(self):
        result = validate_review_text(name="aaaaaaaaaa", text="Normal text.")
        assert result is not None
        assert "спам" in result

    def test_repeat_spam_mid_sentence(self):
        # spam chars don't have to be at start
        _bad(text="Отличный магазин!!!!!!!!!! рекомендую")

    def test_repeat_spam_checked_before_links(self):
        # Both violations present; repeat-spam is caught first.
        result = validate_review_text(
            name="User", text="aaaaaaaaaa http://example.com"
        )
        assert result == "Слишком много повторяющихся символов — похоже на спам."

    def test_repeat_spam_checked_before_profanity(self):
        result = validate_review_text(name="User", text="aaaaaaaaaa fuck")
        assert result == "Слишком много повторяющихся символов — похоже на спам."


# ══════════════════════════════════════════════════════════════════════════════
# LINK / SPAM DETECTION
# ══════════════════════════════════════════════════════════════════════════════

class TestLinksAndSpam:

    # — URL schemes ————————————————————————————————————————————————————————————

    def test_http_url_in_text_rejected(self):
        result = _bad(text="Смотрите тут: http://example.com")
        assert result == "Нельзя указывать ссылки, e-mail и похожие на них фрагменты."

    def test_https_url_in_text_rejected(self):
        _bad(text="Visit https://shop.ru please")

    def test_ftp_url_rejected(self):
        _bad(text="Download at ftp://files.net/archive")

    def test_www_prefix_rejected(self):
        _bad(text="Go to www.example.com for details")

    def test_telegram_tme_link_rejected(self):
        _bad(text="Join our channel: t.me/flowers_shop")

    def test_telegram_full_link_rejected(self):
        _bad(text="telegram.me/bestshop")

    def test_vk_link_rejected(self):
        _bad(text="vk.com/flowershop")

    def test_whatsapp_link_rejected(self):
        _bad(text="Write me wa.me/79001234567")

    def test_bitly_shortener_rejected(self):
        _bad(text="Check bit.ly/abc123")

    def test_youtu_be_rejected(self):
        _bad(text="Watch this: youtu.be/dQw4w9WgXcQ")

    def test_discord_invite_rejected(self):
        _bad(text="Join discord.gg/mycommunity")

    # — Domain-like patterns ———————————————————————————————————————————————————

    def test_domain_ru_rejected(self):
        _bad(text="Лучший магазин myshop.ru!")

    def test_domain_com_rejected(self):
        _bad(text="Visit coolstore.com")

    def test_domain_io_rejected(self):
        _bad(text="Try newapp.io")

    def test_domain_online_rejected(self):
        _bad(text="Check flowers.online")

    # — E-mail ─────────────────────────────────────────────────────────────────

    def test_email_in_text_rejected(self):
        _bad(text="Contact me at user@example.com")

    def test_email_in_name_rejected(self):
        result = validate_review_text(name="spammer@mail.ru", text="Good text.")
        assert result is not None

    # — IP address ─────────────────────────────────────────────────────────────

    def test_ipv4_address_rejected(self):
        _bad(text="Server is at 192.168.1.1 – check it out")

    def test_ip_at_start_of_text_rejected(self):
        _bad(text="10.0.0.1 is the admin panel")

    # — Link in name ───────────────────────────────────────────────────────────

    def test_url_in_name_rejected(self):
        result = validate_review_text(name="http://spam.ru", text="Nice shop.")
        assert result is not None


# ══════════════════════════════════════════════════════════════════════════════
# PROFANITY DETECTION
# ══════════════════════════════════════════════════════════════════════════════

class TestProfanity:

    # — Direct matches ─────────────────────────────────────────────────────────

    def test_russian_root_huy_rejected(self):
        result = _bad(text="Это полный хуй какой-то.")
        assert result == "Пожалуйста, без ненормативной лексики."

    def test_russian_root_pizd_rejected(self):
        _bad(text="Пиздец этому магазину.")

    def test_russian_bla_rejected(self):
        _bad(text="Блядь, цветы завяли через час!")

    def test_russian_suka_rejected(self):
        _bad(text="Такая сука медленная доставка.")

    def test_russian_mudak_rejected(self):
        _bad(text="Менеджер — полный мудак.")

    def test_russian_govno_rejected(self):
        _bad(text="Говно, а не цветы.")

    def test_english_fuck_rejected(self):
        result = _bad(text="This is fucking terrible quality.")
        assert result == "Пожалуйста, без ненормативной лексики."

    def test_english_shit_rejected(self):
        _bad(text="What a shit quality.")

    def test_english_bitch_rejected(self):
        _bad(text="You are a bitch.")

    # — Case-insensitivity ─────────────────────────────────────────────────────

    def test_uppercase_english_profanity_rejected(self):
        _bad(text="FUCK this place!")

    def test_mixed_case_russian_profanity_rejected(self):
        _bad(text="Говно полное.")

    # — Normalization: ё → е ───────────────────────────────────────────────────

    def test_profanity_yo_to_ye_normalization(self):
        # "Ёбаный" → normalizes to "ебаный" → matches stem "ебан"
        _bad(text="Ёбаный магазин!")

    # — Normalization: 0 → о ───────────────────────────────────────────────────

    def test_profanity_zero_to_o_normalization(self):
        # "г0вно" → "говно" after 0→о substitution
        _bad(text="Г0вно, а не сервис.")

    # — Normalization: @ → а ───────────────────────────────────────────────────

    def test_profanity_at_to_a_normalization(self):
        # "сук@" → "сука" after @→а substitution
        _bad(text="сук@!")

    # — Normalization: $ → с ───────────────────────────────────────────────────

    def test_profanity_dollar_to_s_normalization(self):
        # "$ука" → "сука" after $→с substitution
        _bad(text="$ука какая доставка.")

    # — Profanity in name field ────────────────────────────────────────────────

    def test_profanity_in_name_rejected(self):
        result = validate_review_text(name="хуйня", text="Normal text.")
        assert result is not None
        assert "лексик" in result

    # — Normalization: 3 → з ───────────────────────────────────────────────────

    def test_profanity_three_to_z_normalization(self):
        # "3алуп" → "залуп" after 3→з substitution; "залуп" is in _PROFANITY
        _bad(text="Полный 3алупа магазин!")

    # — Profanity checked after link detection ─────────────────────────────────

    def test_link_caught_before_profanity(self):
        # Both violations; links are checked before profanity.
        result = validate_review_text(name="User", text="fuck https://spam.ru")
        assert result == "Нельзя указывать ссылки, e-mail и похожие на них фрагменты."


# ══════════════════════════════════════════════════════════════════════════════
# ADDITIONAL URL SCHEMES (not covered above)
# ══════════════════════════════════════════════════════════════════════════════

class TestAdditionalUrlSchemes:
    """
    The _URL_SCHEMES regex covers several patterns that weren't individually
    tested in TestLinksAndSpam. These tests ensure full coverage of the regex.
    """

    def test_ftps_scheme_rejected(self):
        # ftps:// is explicitly in the pattern alongside ftp://
        _bad(text="Secure FTP: ftps://files.example.com")

    def test_goo_gl_shortener_rejected(self):
        _bad(text="Short link: goo.gl/abc123")

    def test_tinyurl_shortener_rejected(self):
        _bad(text="See this: tinyurl.com/mylink")

    def test_discord_com_rejected(self):
        # discord.com/ (not just discord.gg/) is in the pattern
        _bad(text="Join discord.com/invite/xyz")

    def test_double_slash_url_rejected(self):
        # "//domain/path" pattern (protocol-relative URL)
        _bad(text="Go to //shop.example/page")
