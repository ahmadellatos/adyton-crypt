"""Unit tests for the shared password-strength logic (pure, no Qt)."""

from ui.password_strength import (
    CHECKLIST_ITEMS,
    STRENGTH_COLORS,
    STRENGTH_LABELS,
    generate_password,
    is_strong,
    password_rules,
    pw_strength,
)

# 14 chars, no dictionary words, all four character classes present.
STRONG_PW = "Zr4!qP9mWk2$tL"


def test_pw_strength_empty_is_minus_one():
    assert pw_strength("") == -1


def test_pw_strength_in_range_for_nonempty():
    score = pw_strength(STRONG_PW)
    assert 0 <= score < len(STRENGTH_COLORS)
    assert 0 <= score < len(STRENGTH_LABELS)


def test_password_rules_align_with_checklist():
    rules = password_rules(STRONG_PW)
    assert len(rules) == len(CHECKLIST_ITEMS)
    assert all(rules)


def test_password_rules_flags_each_missing_class():
    assert password_rules("short") == [False, False, True, False, False]
    assert password_rules("alllowercase1!") == [True, False, True, True, True]
    assert password_rules("ALLUPPERCASE1!") == [True, True, False, True, True]
    assert password_rules("NoDigits!!") == [True, True, True, False, True]
    assert password_rules("NoSymbol123") == [True, True, True, True, False]


def test_is_strong_gate():
    assert is_strong(STRONG_PW) is True
    assert is_strong("weak") is False  # fails the checklist outright
    assert is_strong("") is False
    # Passing the checklist is necessary but not sufficient: a short password
    # that misses a character class can never clear the gate.
    assert is_strong("Abcdef1") is False  # 7 chars, no symbol


def test_generate_password_always_passes_rules():
    for _ in range(50):
        pw = generate_password()
        assert all(password_rules(pw))
        assert is_strong(pw)


def test_generate_password_respects_length():
    assert len(generate_password(24)) == 24
