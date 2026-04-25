from __future__ import annotations

from speclink.core.logging import format_stats


def test_format_stats_multiple_keys():
    result = format_stats({"changed": 5, "unchanged": 3})
    assert "[stat.key]changed[/] [stat.val]5[/]" in result
    assert "[stat.key]unchanged[/] [stat.val]3[/]" in result
    assert "[stat.sep]·[/]" in result


def test_format_stats_empty():
    assert format_stats({}) == ""


def test_format_stats_int_and_float():
    result = format_stats({"count": 10, "ratio": 0.95})
    assert "[stat.val]10[/]" in result
    assert "[stat.val]0.95[/]" in result
