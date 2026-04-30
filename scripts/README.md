# GPSA Results Scripts

Python scripts for building and maintaining the GPSA results archive.

---

## Scripts

### build_season_index.py — Season Archive Generator

Generates a season archive `index.html` from individual dual meet result files. Automatically detects teams and divisions, and produces a responsive standings + schedule page.

#### Requirements

```bash
pip install beautifulsoup4
```

#### Usage

```bash
# From repo root
python scripts/build_season_index.py -i 2025 -o 2025

# With verbose logging
python scripts/build_season_index.py -i 2025 -o 2025 --verbose

# Non-interactive (requires divisions.csv)
python scripts/build_season_index.py -i 2025 -o 2025 --non-interactive
```

#### Arguments

| Argument | Short | Description | Required |
|----------|-------|-------------|----------|
| `--input` | `-i` | Year directory containing meet result HTML files | Yes |
| `--output` | `-o` | Output directory for archive | No (defaults to cwd) |
| `--verbose` | `-v` | Enable detailed debug logging | No |
| `--non-interactive` | | Run without prompts — requires `divisions.csv` | No |

#### divisions.csv Format

Required for automated (non-interactive) mode. Place in the year directory.

```csv
season,team_code,division
2025,WPPI,red
2025,WO,red
2025,MBKM,red
2025,COL,red
2025,RMMR,red
2025,POQ,red
2025,CV,white
2025,WYCC,white
2025,GG,white
2025,HW,white
2025,WW,white
2025,GWRA,white
2025,KCD,blue
2025,JRCC,blue
2025,RRST,blue
2025,BLMA,blue
2025,EL,blue
```

Division names are lowercase: `red`, `white`, `blue`. Use filename abbreviations for team codes — the script translates them to official codes automatically.

#### Updating Team Mappings

When teams change names or new teams join, update these maps in `build_season_index.py`:

```python
TEAM_NAME_MAP          # Full name → abbreviation
TEAM_SCHEDULE_NAME_MAP # Full name → short display name
FILENAME_ABBR_MAP      # Filename abbreviation → official abbreviation (if they differ)
```

#### Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Expected 3 divisions but detected X` | Incomplete meet data | Verify all meets are present |
| `Could not detect year from any files` | Files don't match naming pattern | Check `YYYY-MM-DD_T1_v_T2.html` format |
| `Multiple years detected` | Mixed seasons in directory | Move prior season files out |
| `ModuleNotFoundError: bs4` | BeautifulSoup not installed | `pip install beautifulsoup4` |

---

### generate_index.py — Directory Index Generator

Recursively generates branded `index.html` directory listing pages. Runs automatically via GitHub Actions on every push. Use manually to regenerate after local changes.

#### Usage

```bash
# Regenerate all indexes from repo root
python scripts/generate_index.py .

# Regenerate for a specific directory
python scripts/generate_index.py invitationals/CityMeet
```

#### What It Generates

- GPSA branded header with breadcrumb navigation
- Sorted list of files and subdirectories with icons
- Links to parent directories
- CSS served from `https://css.gpsaswimming.org`

#### Excluded Directories

`.git`, `scripts`, `assets`, `resources`, `css`

---

### bulk_process_results.py — Bulk SDIF Processor

Batch-converts SD3/ZIP files to result HTML. Primarily used for historical backfills — the n8n automation pipeline handles current season processing.

#### Usage

```bash
python scripts/bulk_process_results.py -i incoming/ -o .
```

Output is organized into `YYYY/` subdirectories automatically.

#### Arguments

| Argument | Short | Description | Required |
|----------|-------|-------------|----------|
| `--input` | `-i` | Directory containing `.sd3` and/or `.zip` files | Yes |
| `--output` | `-o` | Output directory (year subdirs created automatically) | Yes |

Logs are written to `bulk_process_results.log`.

---

## Complete Workflow: New Season

```bash
# 1. Add result HTML files to the year directory (or let n8n automation do it)
#    2025/YYYY-MM-DD_T1_v_T2.html

# 2. Ensure divisions.csv is in the year directory
#    2025/divisions.csv

# 3. Push — GitHub Actions handles the rest:
#    - build-season-archive.yml rebuilds 2025/index.html
#    - generate-indexes.yml updates root and invitationals indexes

git add 2025/
git commit -m "Add 2025 meet results"
git push
```
