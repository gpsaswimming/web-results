import argparse
import csv
import os
import logging
import sys
from bs4 import BeautifulSoup
from collections import defaultdict
from datetime import datetime

# --- Configuration ---
# This section contains team name mappings that are static across seasons.

# Maps the full team names found in result files to their official abbreviations.
# This map is crucial for linking results to the correct team for standings.
TEAM_NAME_MAP = {
    "Beaconsdale Blue Marlins": "BLMAR",
    "Beechwood Sharks": "BW",
    "Colony Cudas": "COL",
    "Coventry Sailfish Swim Team": "CV",
    "Elizabeth Lake Tideriders": "EL",
    "George Wythe Wahoos": "GWRA",
    "Wythe Wahoos": "WYTHE",
    "Glendale Gators": "GG",
    "Hidenwood Tarpons": "HW",
    "James River Country Club": "JRCC",
    "Kiln Creek Dolphins": "KCD",
    "Marlbank Mudtoads": "MBKMT",
    "Northampton Marlins": "NHM",
    "Poquoson Barracudas": "POQ",
    "Riverdale Rays": "RRST",
    "Running Man Manta Rays": "RMMR",
    "Wendwood Wahoos": "WW",
    "Village Green Patriots": "VG",
    "Willow Oaks Stingrays": "WO",
    "Windy Point Piranhas": "WPPIR",
    "WYCC Sea Turtles": "WYCC",
    "WYCC Seaturtles": "WYCC"
}

# Maps full team names to the shorter names used in the schedule table.
TEAM_SCHEDULE_NAME_MAP = {
    "Beaconsdale Blue Marlins": "Beaconsdale",
    "Beechwood Sharks": "Beechwood",
    "Colony Cudas": "Colony",
    "Coventry Sailfish Swim Team": "Coventry",
    "Elizabeth Lake Tideriders": "Elizabeth Lake",
    "George Wythe Wahoos": "George Wythe",
    "Wythe Wahoos": "Wythe",
    "Glendale Gators": "Glendale",
    "Hidenwood Tarpons": "Hidenwood",
    "James River Country Club": "James River",
    "Kiln Creek Dolphins": "Kiln Creek",
    "Marlbank Mudtoads": "Marlbank",
    "Northampton Marlins": "Northampton",
    "Poquoson Barracudas": "Poquoson",
    "Riverdale Rays": "Riverdale",
    "Running Man Manta Rays": "Running Man",
    "Wendwood Wahoos": "Wendwood",
    "Village Green Patriots": "Village Green",
    "Willow Oaks Stingrays": "Willow Oaks",
    "Windy Point Piranhas": "Windy Point",
    "WYCC Sea Turtles": "Warwick Yacht",
    "WYCC Seaturtles": "Warwick Yacht"
}

# Maps truncated filename abbreviations to their official, full-length counterparts.
FILENAME_ABBR_MAP = {
    "BBM": "BLMAR",
    "GPWYCC": "WYCC",
    "MBKM": "MBKMT",
    "WPPI": "WPPIR",
    "BLMA": "BLMAR"
}


# --- CSV Division Loading ---
def load_divisions_from_csv(csv_path, filename_abbr_map):
    """
    Load division assignments from a CSV file.

    CSV format:
        season,team_code,division
        2025,WPPI,red
        2025,WO,red
        ...

    Args:
        csv_path: Path to the divisions.csv file
        filename_abbr_map: Map to translate filename abbreviations to official codes

    Returns:
        Dict mapping division names (capitalized) to lists of team abbreviations,
        or None if file doesn't exist or is invalid.
    """
    if not os.path.exists(csv_path):
        logging.debug(f"divisions.csv not found at: {csv_path}")
        return None

    try:
        division_assignments = {'Red': [], 'White': [], 'Blue': []}

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                team_code = row.get('team_code', '').strip()
                division = row.get('division', '').strip().lower()

                if not team_code or not division:
                    continue

                # Translate filename abbreviation to official abbreviation
                official_abbr = filename_abbr_map.get(team_code, team_code)

                # Capitalize division name for internal use
                division_cap = division.capitalize()

                if division_cap in division_assignments:
                    division_assignments[division_cap].append(official_abbr)
                else:
                    logging.warning(f"Unknown division '{division}' for team {team_code}")

        # Validate we have teams in each division
        empty_divisions = [d for d, teams in division_assignments.items() if not teams]
        if empty_divisions:
            logging.warning(f"Empty divisions in CSV: {empty_divisions}")

        total_teams = sum(len(teams) for teams in division_assignments.values())
        logging.info(f"Loaded {total_teams} team assignments from divisions.csv")

        for div_name, teams in division_assignments.items():
            logging.debug(f"  {div_name}: {teams}")

        return division_assignments

    except Exception as e:
        logging.error(f"Error reading divisions.csv: {e}")
        return None


def validate_divisions_against_teams(division_assignments, detected_teams):
    """
    Validate that all teams detected in results have division assignments.

    Args:
        division_assignments: Dict from load_divisions_from_csv()
        detected_teams: Set of team abbreviations detected from result files

    Returns:
        Tuple (is_valid: bool, missing_teams: set, extra_teams: set)
        - missing_teams: Teams in results but not in CSV (critical)
        - extra_teams: Teams in CSV but not in results (warning only)
    """
    # Flatten all teams from division assignments
    csv_teams = set()
    for teams in division_assignments.values():
        csv_teams.update(teams)

    missing_teams = detected_teams - csv_teams
    extra_teams = csv_teams - detected_teams

    is_valid = len(missing_teams) == 0

    return is_valid, missing_teams, extra_teams


# --- Logging Setup ---
def setup_logging(verbose=False):
    """Configure logging with appropriate level and format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def detect_year_from_files(input_dir):
    """
    Extracts the season year from meet result filenames.

    Returns:
        The detected year as an integer, or None if no valid files found.
    """
    html_files = [f for f in os.listdir(input_dir) if f.endswith('.html')]
    years_found = set()

    for filename in html_files:
        # Extract date from filename (YYYY-MM-DD_HOME_v_AWAY.html)
        parts = filename.replace('.html', '').split('_')
        if len(parts) >= 4 and parts[2].lower() == 'v':
            try:
                date_str = parts[0]
                year = int(date_str.split('-')[0])
                years_found.add(year)
            except (ValueError, IndexError):
                continue

    if not years_found:
        return None

    if len(years_found) > 1:
        logging.warning(f"Multiple years detected in files: {sorted(years_found)}")
        # Use the most common year (or earliest if tie)
        year = min(years_found)
        logging.info(f"Using year: {year}")
        return year

    year = years_found.pop()
    logging.info(f"Detected season year: {year}")
    return year


def detect_team_clusters(input_dir, team_name_map, filename_abbr_map):
    """
    Analyzes all meet files to detect which teams compete against each other.
    Teams that compete together are in the same division.

    Returns:
        List of sets, where each set contains team abbreviations in the same division.
    """
    logging.info(f"Scanning directory: {input_dir}")

    # Track which teams have competed against each other
    opponents = defaultdict(set)
    all_teams = set()

    html_files = [f for f in os.listdir(input_dir) if f.endswith('.html')]
    logging.info(f"Found {len(html_files)} HTML files to analyze")

    for filename in html_files:
        # Extract teams from filename (YYYY-MM-DD_HOME_v_AWAY.html)
        parts = filename.replace('.html', '').split('_')
        if len(parts) < 4 or parts[2].lower() != 'v':
            logging.debug(f"Skipping non-meet file: {filename}")
            continue

        # Get official abbreviations
        home_abbr = filename_abbr_map.get(parts[1], parts[1])
        away_abbr = filename_abbr_map.get(parts[3], parts[3])

        # Record that these teams competed
        opponents[home_abbr].add(away_abbr)
        opponents[away_abbr].add(home_abbr)
        all_teams.add(home_abbr)
        all_teams.add(away_abbr)

        logging.debug(f"Found meet: {home_abbr} vs {away_abbr}")

    logging.info(f"Detected {len(all_teams)} unique teams")

    # Cluster teams into divisions using opponent relationships
    clusters = []
    remaining_teams = all_teams.copy()

    while remaining_teams:
        # Start a new cluster with an arbitrary team
        seed_team = remaining_teams.pop()
        cluster = {seed_team}

        # Add all teams that competed against anyone in this cluster
        changed = True
        while changed:
            changed = False
            for team in list(remaining_teams):
                # If this team competed against anyone in the cluster, add it
                if any(team in opponents[cluster_member] for cluster_member in cluster):
                    cluster.add(team)
                    remaining_teams.remove(team)
                    changed = True

        clusters.append(cluster)
        logging.info(f"Detected division cluster with {len(cluster)} teams")

    return clusters


def prompt_division_assignment(clusters, team_name_map):
    """
    Prompts the user to assign each cluster to a division (Red, White, or Blue).

    Returns:
        Dict mapping division names to lists of team abbreviations.
    """
    division_names = ['Red', 'White', 'Blue']
    available_divisions = division_names.copy()
    division_assignments = {}

    # Reverse map for displaying full team names
    inverted_team_map = {v: k for k, v in team_name_map.items()}

    print("\n" + "="*80)
    print("DIVISION ASSIGNMENT")
    print("="*80)
    print(f"\nDetected {len(clusters)} team groupings from meet results.")
    print("Please assign each group to a division.\n")

    for i, cluster in enumerate(clusters, 1):
        # Sort teams alphabetically for consistent display
        sorted_teams = sorted(cluster)

        print(f"\n{'─'*80}")
        print(f"GROUP {i} - Teams that competed together:")
        print(f"{'─'*80}")

        for team_abbr in sorted_teams:
            full_name = inverted_team_map.get(team_abbr, team_abbr)
            print(f"  • {team_abbr:8} - {full_name}")

        # If this is the last cluster, assign it automatically
        if len(available_divisions) == 1:
            assigned_division = available_divisions[0]
            print(f"\n→ Automatically assigned to: {assigned_division} Division")
            division_assignments[assigned_division] = sorted_teams
            break

        # Prompt for division assignment
        print(f"\nAvailable divisions:")
        for idx, div_name in enumerate(available_divisions, 1):
            print(f"  {idx}. {div_name}")

        while True:
            try:
                choice = input(f"\nSelect division for Group {i} (1-{len(available_divisions)}): ").strip()
                choice_idx = int(choice) - 1

                if 0 <= choice_idx < len(available_divisions):
                    assigned_division = available_divisions[choice_idx]
                    division_assignments[assigned_division] = sorted_teams
                    available_divisions.remove(assigned_division)
                    print(f"✓ Assigned to {assigned_division} Division")
                    break
                else:
                    print(f"Please enter a number between 1 and {len(available_divisions)}")
            except ValueError:
                print(f"Invalid input. Please enter a number between 1 and {len(available_divisions)}")
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user.")
                sys.exit(0)

    print("\n" + "="*80)
    print("DIVISION ASSIGNMENTS COMPLETE")
    print("="*80)
    for div_name in division_names:
        if div_name in division_assignments:
            teams = division_assignments[div_name]
            print(f"\n{div_name} Division ({len(teams)} teams):")
            for team in teams:
                full_name = inverted_team_map.get(team, team)
                print(f"  • {team:8} - {full_name}")
    print()

    return division_assignments


def parse_meet_file(file_path, team_name_map, schedule_name_map, filename_abbr_map):
    """Parses a single meet result file to extract teams and scores, using the filename to determine home/away."""
    try:
        # --- Extract Home/Away from filename (e.g., "YYYY-MM-DD_HOME_v_AWAY.html") ---
        basename = os.path.basename(file_path)
        parts = basename.replace('.html', '').split('_')

        if len(parts) < 4 or parts[2].lower() != 'v':
            logging.warning(f"Filename {basename} does not match 'DATE_HOME_v_AWAY.html' format. Skipping.")
            return None
        
        date_str = parts[0]
        # Get the official abbreviation from the filename, using the map as a translator
        home_abbr_from_file = filename_abbr_map.get(parts[1], parts[1])
        away_abbr_from_file = filename_abbr_map.get(parts[3], parts[3])
        
        with open(file_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        # Find the team scores table
        scores_header = soup.find('h2', string='Team Scores')
        if not scores_header: return None
        scores_table = scores_header.find_next('table')
        if not scores_table: return None
        rows = scores_table.find('tbody').find_all('tr')
        if len(rows) < 2: return None

        # Extract team data from table
        teamA_name = rows[0].find_all('td')[0].text.strip()
        teamA_score = float(rows[0].find_all('td')[1].text.strip())
        teamB_name = rows[1].find_all('td')[0].text.strip()
        teamB_score = float(rows[1].find_all('td')[1].text.strip())
        
        teamA_abbr = team_name_map.get(teamA_name)
        teamB_abbr = team_name_map.get(teamB_name)

        if not teamA_abbr or not teamB_abbr:
            logging.warning(f"Could not map team names in {basename} to abbreviations. Skipping.")
            return None

        # --- Match table data to filename data to assign home/away correctly ---
        if teamA_abbr == home_abbr_from_file and teamB_abbr == away_abbr_from_file:
            home_name, home_score = teamA_name, teamA_score
            away_name, away_score = teamB_name, teamB_score
        elif teamB_abbr == home_abbr_from_file and teamA_abbr == away_abbr_from_file:
            home_name, home_score = teamB_name, teamB_score
            away_name, away_score = teamA_name, teamA_score
        else:
            logging.warning(f"Teams in filename {basename} do not match teams in score table. Skipping.")
            return None

        return {
            "date": datetime.strptime(date_str, '%Y-%m-%d'),
            "home_name": home_name,
            "home_abbr": home_abbr_from_file,
            "home_schedule_name": schedule_name_map.get(home_name, home_name),
            "home_score": home_score,
            "away_name": away_name,
            "away_abbr": away_abbr_from_file,
            "away_schedule_name": schedule_name_map.get(away_name, away_name),
            "away_score": away_score,
            "file_name": basename
        }
    except Exception as e:
        logging.warning(f"Could not process file {file_path}. Error: {e}")
        return None

def generate_html(meets_by_division, division_assignments, year):
    """Generates the final HTML output file from the processed meet data."""
    
    # --- Calculate Standings ---
    standings = defaultdict(lambda: {'wins': 0, 'losses': 0})
    for division in meets_by_division:
        for meet in meets_by_division[division]:
            # Determine winner and loser
            winner_abbr = meet['home_abbr'] if meet['home_score'] > meet['away_score'] else meet['away_abbr']
            loser_abbr = meet['away_abbr'] if meet['home_score'] > meet['away_score'] else meet['home_abbr']
            standings[winner_abbr]['wins'] += 1
            standings[loser_abbr]['losses'] += 1

    # --- Start HTML Generation ---
    html_output = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GPSA {year} Season Archive</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

    <!-- Favicon Links -->
    <link rel="apple-touch-icon" sizes="180x180" href="https://d1nmxxg9d5tdo.cloudfront.net/875/files/apple-touch-icon.png?1651502524">
    <link rel="icon" type="image/png" sizes="32x32" href="https://d1nmxxg9d5tdo.cloudfront.net/875/files/favicon-32x32.png?1651502547">
    <link rel="icon" type="image/png" sizes="16x16" href="https://d1nmxxg9d5tdo.cloudfront.net/875/files/favicon-16x16.png?1651502535">

    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    fontFamily: {{ sans: ['Inter', 'sans-serif'] }},
                    colors: {{ 'gpsa-blue': '#002366', 'gpsa-blue-light': '#0033a0', 'gpsa-red': '#d9242b' }}
                }}
            }}
        }}
    </script>

    <style>
        /* GPSA Embedded Styles for Season Archive */
        body {{
            font-family: 'Inter', sans-serif;
            background-color: #f0f2f5;
            color: #1f2937;
        }}

        .gpsa-header {{
            background-color: #002366;
            color: white;
        }}

        .gpsa-header img {{
            border-radius: 50%;
        }}

        .gpsa-header-subtitle {{
            margin-top: 0.25rem;
            font-size: 0.875rem;
            text-align: center;
            color: #d1d5db;
        }}

        @media (min-width: 640px) {{
            .gpsa-header-subtitle {{
                font-size: 1rem;
            }}
        }}

        /* Responsive table text sizing */
        .table-date {{
            font-size: 0.75rem; /* 12px on mobile */
        }}

        .table-text {{
            font-size: 0.875rem; /* 14px on mobile */
        }}

        .table-header {{
            font-size: 0.875rem; /* 14px on mobile */
            padding: 0.25rem 0.5rem;
        }}

        .table-cell {{
            padding: 0.25rem 0.5rem;
        }}

        /* Date format responsive display */
        .date-full {{
            display: none; /* Hide full date on mobile */
        }}

        .date-abbr {{
            display: inline; /* Show abbreviated date on mobile */
        }}

        @media (min-width: 640px) {{
            .table-date {{
                font-size: 0.875rem; /* 14px on tablet */
            }}

            .table-text {{
                font-size: 1rem; /* 16px on tablet */
            }}

            .table-header {{
                font-size: 1rem; /* 16px on tablet */
                padding: 0.5rem;
            }}

            .table-cell {{
                padding: 0.5rem;
            }}

            /* Switch to full date format on tablet+ */
            .date-full {{
                display: inline;
            }}

            .date-abbr {{
                display: none;
            }}
        }}

        @media (min-width: 768px) {{
            .table-header {{
                font-size: 1.125rem; /* 18px on desktop */
            }}
        }}

        @media print {{
            .no-print {{
                display: none !important;
            }}

            body, .container {{
                margin: 0;
                padding: 0;
                border: none;
                box-shadow: none;
            }}
        }}
    </style>
</head>
<body>
    <main class="container mx-auto p-4 sm:p-6 lg:p-8">
        <div class="max-w-7xl mx-auto">
            <header id="top" class="gpsa-header p-4 shadow-md flex items-center justify-center no-print mb-6 rounded-lg">
                <img src="https://publicity.gpsaswimming.org/assets/gpsa_logo.png"
                     alt="GPSA Logo"
                     class="h-16 w-16 md:h-20 md:w-20 mr-4 rounded-full"
                     onerror="this.onerror=null; this.src='https://placehold.co/100x100/002366/FFFFFF?text=GPSA';">
                <div>
                    <h1 class="text-2xl sm:text-3xl md:text-4xl font-bold">GPSA {year} Season Archive</h1>
                    <p class="gpsa-header-subtitle">Season Results and Standings</p>
                </div>
            </header>

            <div class="bg-white rounded-xl shadow-lg p-4 mb-8 flex flex-wrap justify-around gap-2 sm:gap-4">
                <a href="#red" class="text-base sm:text-lg md:text-xl font-bold text-gpsa-red hover:text-gpsa-blue transition-colors duration-300">Red Division</a>
                <a href="#white" class="text-base sm:text-lg md:text-xl font-bold text-gpsa-red hover:text-gpsa-blue transition-colors duration-300">White Division</a>
                <a href="#blue" class="text-base sm:text-lg md:text-xl font-bold text-gpsa-red hover:text-gpsa-blue transition-colors duration-300">Blue Division</a>
            </div>
"""
    # --- Loop Through Divisions to Build Tables ---
    for division_name in ['Red', 'White', 'Blue']:
        division_id = division_name.lower()
        html_output += f'<div id="{division_id}" class="bg-white rounded-xl shadow-lg p-4 sm:p-6 mb-8 overflow-x-auto">'
        html_output += f'<h2 class="text-xl sm:text-2xl font-bold mb-4 sm:mb-6 text-gray-700">{division_name} Division</h2>'

        # --- Meet Schedule Table ---
        html_output += '<table class="w-full border-collapse min-w-full">'
        html_output += '<thead><tr class="border-b border-black"><th class="w-1/5 table-header bg-gpsa-red text-white text-center align-middle">DATE</th><th class="w-1/5 table-header bg-gpsa-red text-white text-center align-middle">HOME</th><th class="w-1/12 table-header bg-gpsa-red text-white text-center align-middle">SCORE</th><th class="w-1/5 table-header bg-gpsa-red text-white text-center align-middle">VISITOR</th><th class="w-1/12 table-header bg-gpsa-red text-white text-center align-middle">SCORE</th><th class="w-1/5 table-header bg-gpsa-red text-white text-center align-middle">BEST TIMES</th></tr></thead><tbody>'
        
        # Group meets by date
        meets_grouped_by_date = defaultdict(list)
        for meet in meets_by_division.get(division_name, []):
            meets_grouped_by_date[meet['date']].append(meet)

        for date, meets_on_date in sorted(meets_grouped_by_date.items()):
            # Generate both full and abbreviated date formats
            full_date = date.strftime("%A %B %d").upper()
            abbr_date = date.strftime("%a %b %d").upper()
            date_cell = f'<td class="table-cell table-date text-center align-middle" rowspan="{len(meets_on_date)}"><span class="date-abbr">{abbr_date}</span><span class="date-full">{full_date}</span></td>'
            for i, meet in enumerate(meets_on_date):
                html_output += '<tr class="border-b border-black">'
                if i == 0:
                    html_output += date_cell

                home_score_str = f"<strong>{meet['home_score']}</strong>" if meet['home_score'] > meet['away_score'] else str(meet['home_score'])
                visitor_score_str = f"<strong>{meet['away_score']}</strong>" if meet['away_score'] > meet['home_score'] else str(meet['away_score'])

                html_output += f"<td class='table-cell table-text text-center align-middle'>{meet['home_schedule_name']}</td>"
                html_output += f"<td class='table-cell table-text text-center align-middle'>{home_score_str}</td>"
                html_output += f"<td class='table-cell table-text text-center align-middle'>{meet['away_schedule_name']}</td>"
                html_output += f"<td class='table-cell table-text text-center align-middle'>{visitor_score_str}</td>"
                html_output += f"<td class='table-cell table-text text-center align-middle'><a href='{meet['file_name']}' target='_blank' class='text-gpsa-blue-light underline font-medium hover:text-gpsa-red'>Results</a></td>"
                html_output += '</tr>'
        html_output += '</tbody></table><div class="my-8"></div>'

        # --- Standings Table ---
        html_output += '<table class="w-full border-collapse min-w-full">'
        html_output += '<thead><tr class="border-b border-black"><th class="table-header bg-gpsa-red text-white text-center align-middle">Team</th><th class="table-header bg-gpsa-red text-white text-center align-middle">Win</th><th class="table-header bg-gpsa-red text-white text-center align-middle">Loss</th></tr></thead><tbody>'

        division_teams = division_assignments.get(division_name, [])
        # Sort teams by wins (descending)
        sorted_teams = sorted(division_teams, key=lambda abbr: standings[abbr]['wins'], reverse=True)
        
        # Find the full name from the inverted map for display
        inverted_team_map = {v: k for k, v in TEAM_NAME_MAP.items()}

        for team_abbr in sorted_teams:
            team_full_name = inverted_team_map.get(team_abbr, team_abbr)
            win_loss = standings[team_abbr]
            html_output += f"<tr class='border-b border-black'><td class='table-cell table-text text-left align-middle'>{team_abbr} &ndash; {team_full_name}</td><td class='table-cell table-text text-center align-middle'>{win_loss['wins']}</td><td class='table-cell table-text text-center align-middle'>{win_loss['losses']}</td></tr>"
        html_output += '</tbody></table>'
        html_output += '<div class="mt-4 sm:mt-6 flex justify-end"><a href="#top" class="text-sm sm:text-base text-gpsa-blue-light hover:text-gpsa-red font-medium">Back to Top &uarr;</a></div></div>'

    html_output += '</div></main></body></html>'
    return html_output

def main():
    """Main function to process a directory of meet files and generate an archive."""
    parser = argparse.ArgumentParser(
        description="Generate a GPSA season archive from a directory of meet result files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build_season_index.py -i results/2025
  python build_season_index.py -i results/2025 -o results/2025
  python build_season_index.py -i ../2024_results -o ./output --verbose

The script automatically detects:
  - Season year from meet filenames
  - Division groupings based on which teams competed together
        """
    )
    parser.add_argument('-i', '--input', dest='input_dir', type=str, required=True,
                        help='Path to the directory containing meet result HTML files')
    parser.add_argument('-o', '--output', dest='output_dir', type=str, default='.',
                        help='Directory where the archive HTML will be saved (default: current directory)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging output')
    parser.add_argument('--non-interactive', action='store_true',
                        help='Run without prompts (requires divisions.csv in input directory)')
    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose)

    # Validate input directory
    if not os.path.isdir(args.input_dir):
        logging.error(f"Input directory does not exist: {args.input_dir}")
        sys.exit(1)

    # Validate output directory
    if not os.path.isdir(args.output_dir):
        logging.error(f"Output directory does not exist: {args.output_dir}")
        sys.exit(1)

    # Step 1: Auto-detect season year from filenames
    logging.info("="*80)
    logging.info("GPSA Season Archive Generator")
    logging.info("="*80)
    logging.info("\nStep 1: Detecting season year from filenames...")

    year = detect_year_from_files(args.input_dir)
    if year is None:
        logging.error("Could not detect year from any files in the input directory.")
        logging.error("Ensure files follow the naming pattern: YYYY-MM-DD_TEAM1_v_TEAM2.html")
        sys.exit(1)

    # Step 2: Detect team clusters from meet results
    logging.info("\nStep 2: Analyzing meet results to detect team groupings...")
    clusters = detect_team_clusters(args.input_dir, TEAM_NAME_MAP, FILENAME_ABBR_MAP)

    if len(clusters) != 3:
        logging.warning(f"Expected 3 divisions but detected {len(clusters)} team clusters.")
        logging.warning("This may indicate incomplete meet data or unusual division structure.")
        if not args.non_interactive:
            response = input("\nDo you want to continue anyway? (y/n): ").strip().lower()
            if response != 'y':
                logging.info("Operation cancelled by user.")
                sys.exit(0)

    # Step 3: Load or prompt for division assignments
    logging.info("\nStep 3: Determining division assignments...")

    csv_path = os.path.join(args.input_dir, 'divisions.csv')
    division_assignments = None

    # Try to load from CSV first
    if os.path.exists(csv_path):
        logging.info(f"Found divisions.csv at: {csv_path}")
        division_assignments = load_divisions_from_csv(csv_path, FILENAME_ABBR_MAP)

        if division_assignments:
            # Validate against detected teams
            all_detected = set()
            for cluster in clusters:
                all_detected.update(cluster)

            is_valid, missing, extra = validate_divisions_against_teams(
                division_assignments, all_detected
            )

            if missing:
                logging.error(f"Teams in results but not in divisions.csv: {missing}")
                if args.non_interactive:
                    logging.error("Cannot proceed in non-interactive mode with missing team assignments.")
                    sys.exit(1)
                # In interactive mode, fall through to prompt
                logging.info("Falling back to interactive division assignment...")
                division_assignments = None

            if extra:
                logging.warning(f"Teams in divisions.csv but not in results: {extra}")
                logging.warning("These teams will appear in standings with 0-0 records.")

    # Fall back to interactive prompt if needed
    if division_assignments is None:
        if args.non_interactive:
            logging.error("No valid divisions.csv found and --non-interactive specified.")
            logging.error(f"Create a divisions.csv file at: {csv_path}")
            sys.exit(1)

        # Use interactive prompt
        division_assignments = prompt_division_assignment(clusters, TEAM_NAME_MAP)

    # Create reverse lookup: team -> division
    team_to_division = {team: division for division, teams in division_assignments.items() for team in teams}

    # Step 4: Process all meet files
    logging.info("\nStep 4: Processing meet result files...")
    all_meets = []
    html_files = [f for f in os.listdir(args.input_dir) if f.endswith('.html')]

    for i, filename in enumerate(html_files, 1):
        file_path = os.path.join(args.input_dir, filename)
        logging.debug(f"[{i}/{len(html_files)}] Processing {filename}")

        meet_data = parse_meet_file(file_path, TEAM_NAME_MAP, TEAM_SCHEDULE_NAME_MAP, FILENAME_ABBR_MAP)
        if meet_data:
            # Assign division based on the home team
            division = team_to_division.get(meet_data['home_abbr'])
            if division:
                meet_data['division'] = division
                all_meets.append(meet_data)
                logging.debug(f"  ✓ Added to {division} Division")
            else:
                logging.warning(f"  ✗ Team {meet_data['home_abbr']} not found in any division")

    logging.info(f"Successfully processed {len(all_meets)} meet results")

    # Step 5: Group meets by division
    logging.info("\nStep 5: Organizing meets by division...")
    meets_by_division = defaultdict(list)
    for meet in all_meets:
        meets_by_division[meet['division']].append(meet)

    # Sort meets within each division by date
    for division in meets_by_division:
        meets_by_division[division].sort(key=lambda x: x['date'])
        logging.info(f"  {division} Division: {len(meets_by_division[division])} meets")

    # Step 6: Generate HTML archive
    logging.info("\nStep 6: Generating HTML archive...")
    final_html = generate_html(meets_by_division, division_assignments, year)

    # Step 7: Save output file
    output_filename = "index.html"
    output_path = os.path.join(args.output_dir, output_filename)

    logging.info(f"Writing output to: {output_path}")
    with open(output_path, "w", encoding='utf-8') as file:
        file.write(final_html)

    logging.info("\n" + "="*80)
    logging.info(f"✓ Successfully generated {output_filename}")
    logging.info("="*80)

if __name__ == "__main__":
    main()
