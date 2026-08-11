import pytest
from modules.command_service.parser import CommandParser


def test_command_parser_indonesian_satisfaction_intents():
    parser = CommandParser(match_threshold=70.0)

    test_cases = [
        ("sangat puas", "sangat puas", 5),
        ("saya sangat puas sekali dengan pelayanannya", "sangat puas", 5),
        ("puas", "puas", 4),
        ("memuaskan", "puas", 4),
        ("cukup puas", "cukup puas", 3),
        ("lumayan lah", "cukup puas", 3),
        ("tidak puas", "tidak puas", 2),
        ("kecewa", "tidak puas", 2),
        ("sangat tidak puas", "sangat tidak puas", 1),
        ("sangat kecewa sekali", "sangat tidak puas", 1),
    ]

    for input_text, expected_intent, expected_score in test_cases:
        res = parser.parse(input_text)
        assert res.intent == expected_intent, f"Failed for '{input_text}': got '{res.intent}'"
        assert res.score == expected_score, f"Failed score for '{input_text}': got {res.score}"
        assert res.status == "success"


def test_command_parser_low_confidence():
    parser = CommandParser(match_threshold=75.0)
    res = parser.parse("xyz123 random words unmatched")
    assert res.status in ("low_confidence", "unknown")
    assert res.score == 0
