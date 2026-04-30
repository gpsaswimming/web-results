# results

GPSA meet results archive, served at `results.gpsaswimming.org`.

## Structure

```text
/
├── 2022/                          # Dual meet results by season
├── 2023/
├── 2024/
├── 2025/
│   ├── YYYY-MM-DD_T1_v_T2.html   # Individual meet result files
│   ├── divisions.csv              # Division assignments (required for archive builder)
│   └── index.html                 # Auto-generated season archive — do not edit manually
├── 2026/
├── invitationals/                 # Historical invitational static files
│   ├── CityMeet/
│   ├── SummerSplashInvitational/
│   └── MiniMeet/
└── scripts/                       # Python build and maintenance scripts
```

## How Results Get Published

Meet results are processed by the n8n automation pipeline:

1. SD3 file received → publicity API server processes it → HTML result generated
2. Result HTML pushed to the appropriate `YYYY/` directory
3. GitHub Actions automatically rebuilds the season archive (`index.html`)

Directory indexes for `invitationals/` and the root are regenerated automatically on any push.

## Adding Results Manually

Place result HTML in the correct year directory following the naming convention:

```text
YYYY/YYYY-MM-DD_TEAM1_v_TEAM2.html
```

Ensure `divisions.csv` exists in the year directory before pushing — the archive builder requires it.

## Scripts

See `scripts/README.md` for documentation on the build and maintenance scripts.
