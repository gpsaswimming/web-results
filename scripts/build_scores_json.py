#!/usr/bin/env python3
"""
Generate a machine-readable scores.json for a season directory.

This is the cross-repo data feed consumed by the meet-schedule site
(meet-schedule.gpsaswimming.org), which fetches it client-side to show each
dual meet's final score and a link to its result page. See web-results/CLAUDE.md.

Score extraction is NOT reimplemented here — it reuses parse_meet_file() and the
team-name maps from build_season_index.py, the same code that builds the season
standings. Only swum meets (files with a "Team Scores" table) appear in the output;
absence from the JSON means "not yet swum" on the schedule side.

Run: python scripts/build_scores_json.py -i 2025 -o 2025
"""

import argparse
import glob
import json
import logging
import os
import sys

from build_season_index import (
    FILENAME_ABBR_MAP,
    TEAM_NAME_MAP,
    TEAM_SCHEDULE_NAME_MAP,
    parse_meet_file,
)

RESULTS_BASE_URL = "https://results.gpsaswimming.org"


def build_scores(input_dir):
    """Parse every dual meet file in input_dir into a sorted list of score records."""
    records = []
    pattern = os.path.join(input_dir, "*_v_*.html")
    for file_path in sorted(glob.glob(pattern)):
        meet = parse_meet_file(
            file_path, TEAM_NAME_MAP, TEAM_SCHEDULE_NAME_MAP, FILENAME_ABBR_MAP
        )
        if not meet:
            continue
        year = meet["date"].year
        records.append({
            "date": meet["date"].strftime("%Y-%m-%d"),
            "home": meet["home_abbr"],
            "away": meet["away_abbr"],
            # Short schedule display names — the stable join key for the schedule
            # site (abbreviations drift, e.g. Wythe is GWRA vs WYTHE).
            "home_name": meet["home_schedule_name"],
            "away_name": meet["away_schedule_name"],
            "home_score": meet["home_score"],
            "away_score": meet["away_score"],
            "url": f"{RESULTS_BASE_URL}/{year}/{meet['file_name']}",
        })

    records.sort(key=lambda r: (r["date"], r["home"]))
    return records


def main():
    parser = argparse.ArgumentParser(
        description="Generate scores.json for a season directory of meet result files."
    )
    parser.add_argument("-i", "--input", dest="input_dir", required=True,
                        help="Season directory containing meet result HTML files")
    parser.add_argument("-o", "--output", dest="output_dir", default=".",
                        help="Directory to write scores.json (default: current directory)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if not os.path.isdir(args.input_dir):
        logging.error(f"Input directory does not exist: {args.input_dir}")
        sys.exit(1)
    if not os.path.isdir(args.output_dir):
        logging.error(f"Output directory does not exist: {args.output_dir}")
        sys.exit(1)

    records = build_scores(args.input_dir)
    out_path = os.path.join(args.output_dir, "scores.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
        f.write("\n")

    logging.info(f"Wrote {len(records)} meet scores to {out_path}")


if __name__ == "__main__":
    main()
