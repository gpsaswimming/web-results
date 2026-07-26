#!/usr/bin/env python3
"""Deploy-time analytics injection for results.gpsaswimming.org.

Idempotently inserts the Umami analytics <script> immediately before the first
</head> of every HTML page under the given root, unless it is already present.

Runs in CI on the staged tree right before `pages deploy .` (see
.github/workflows/deploy.yml): nothing is committed, so the repo stays clean and
every page — historical result files, generated indexes, season archives — is
instrumented on every deploy, including files added in the future.

Deliberately a surgical string splice rather than an HTML-parser round-trip, so a
page is byte-for-byte unchanged except for the single inserted line.
"""
import re
import sys
from pathlib import Path

WEBSITE_ID = "8e0ed974-8a97-4eee-b087-201235f0e538"
SNIPPET = (
    '<script defer src="https://citadel.dadalorian.com/stardust" '
    f'data-website-id="{WEBSITE_ID}"></script>'
)

# First closing head tag, tolerant of whitespace/case (e.g. </head>, </HEAD >).
_HEAD_CLOSE = re.compile(r"</head\s*>", re.IGNORECASE)


def inject(html):
    """Return (new_html, status) where status is 'injected' | 'present' | 'no-head'.

    Idempotent: if this website id is already anywhere in the document, the HTML is
    returned unchanged.
    """
    if WEBSITE_ID in html:
        return html, "present"
    match = _HEAD_CLOSE.search(html)
    if not match:
        return html, "no-head"
    at = match.start()
    return html[:at] + SNIPPET + "\n" + html[at:], "injected"


def main(root):
    counts = {"injected": 0, "present": 0, "no-head": 0}
    for path in sorted(Path(root).rglob("*.html")):
        new_html, status = inject(path.read_text(encoding="utf-8"))
        counts[status] += 1
        if status == "injected":
            path.write_text(new_html, encoding="utf-8")
        elif status == "no-head":
            print(f"  WARN no </head>, skipped: {path}", file=sys.stderr)
    print(
        f"analytics: injected {counts['injected']}, "
        f"already-present {counts['present']}, no-head {counts['no-head']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
