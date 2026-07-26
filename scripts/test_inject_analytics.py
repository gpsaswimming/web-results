#!/usr/bin/env python3
"""Tests for inject_analytics — proves the deploy-time injector before it runs on
the real ~200 result pages. Run: python scripts/test_inject_analytics.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inject_analytics import SNIPPET, WEBSITE_ID, inject  # noqa: E402


def test_injects_before_head_close():
    out, status = inject("<html><head><title>Meet</title></head><body>x</body></html>")
    assert status == "injected"
    assert SNIPPET in out
    assert out.index(SNIPPET) < out.index("</head>")  # inserted inside <head>


def test_case_insensitive_head():
    out, status = inject("<HTML><HEAD></HEAD></HTML>")
    assert status == "injected"
    assert SNIPPET in out


def test_idempotent():
    once, _ = inject("<head></head>")
    twice, status = inject(once)
    assert status == "present"
    assert twice == once
    assert twice.count(WEBSITE_ID) == 1  # never doubles up


def test_no_head_is_left_untouched():
    src = "<div>fragment, no head</div>"
    out, status = inject(src)
    assert status == "no-head"
    assert out == src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"all {len(fns)} inject_analytics tests passed")
