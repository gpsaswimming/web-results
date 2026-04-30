#!/usr/bin/env python3
"""
GPSA Bulk Meet Results Processor
Processes SDIF (.sd3) files and generates formatted HTML result pages.
Supports .zip file extraction and automatic year-based organization.
"""

import argparse
import logging
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bulk_process_results.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# SDIF Constants
STROKE_MAP = {
    '1': 'Freestyle',
    '2': 'Backstroke',
    '3': 'Breaststroke',
    '4': 'Butterfly',
    '5': 'IM',
    '6': 'Freestyle Relay',
    '7': 'Medley Relay'
}

GENDER_MAP = {
    'M': 'Boys',
    'F': 'Girls',
    'X': 'Mixed'
}

LOGO_URL = 'https://publicity.gpsaswimming.org/assets/gpsa_logo.png'


class SDIFParser:
    """Parses SDIF format swim meet data files."""

    def __init__(self):
        self.meet = {}
        self.teams = {}
        self.events = {}
        self.current_team_code = None
        self.last_relay_result = None

    def parse(self, content: str) -> Dict:
        """Parse SDIF file content and return structured data."""
        lines = content.split('\n')

        for line in lines:
            if len(line) < 2:
                continue

            code = line[0:2]

            try:
                if code == 'B1':
                    self._parse_b1(line)
                elif code == 'B2':
                    self._parse_b2(line)
                elif code == 'C1':
                    self._parse_c1(line)
                elif code == 'D0':
                    self._parse_d0(line)
                elif code == 'E0':
                    self._parse_e0(line)
                elif code == 'F0':
                    self._parse_f0(line)
            except Exception as e:
                logger.warning(f"Error parsing line (code {code}): {str(e)}")
                continue

        # Generate meet title for dual meets
        self._generate_meet_title()

        # Sort event results by place
        for event in self.events.values():
            event['results'].sort(key=lambda x: x['place'])

        return {
            'meet': self.meet,
            'teams': self.teams,
            'events': self.events
        }

    def _parse_b1(self, line: str):
        """Parse B1 record - Meet information."""
        self.meet['name'] = line[11:41].strip()
        self.meet['startDate'] = line[121:129].strip()  # MMDDYYYY
        self.last_relay_result = None

    def _parse_b2(self, line: str):
        """Parse B2 record - Host team information."""
        if 'hostName' not in self.meet:
            self.meet['hostName'] = line[11:41].strip()

    def _parse_c1(self, line: str):
        """Parse C1 record - Team information."""
        raw_team_code = line[11:17].strip()
        team_name = line[17:47].strip()
        self.current_team_code = raw_team_code

        if raw_team_code not in self.teams:
            display_code = raw_team_code
            if display_code.startswith('VA'):
                display_code = display_code[2:]

            self.teams[raw_team_code] = {
                'name': team_name,
                'score': 0.0,
                'code': display_code
            }

        self.last_relay_result = None

    def _parse_d0(self, line: str):
        """Parse D0 record - Individual swimmer result."""
        self.last_relay_result = None

        if len(line) < 142:
            return

        event_num = line[72:76].strip()
        if not event_num or event_num == '0':
            return

        swimmer_name = line[11:39].strip()
        final_time = line[115:123].strip()
        place_str = line[135:138].strip()
        points_str = line[138:142].strip()

        if not place_str:
            return

        place = int(place_str)
        points = float(points_str) if points_str else 0.0

        if event_num not in self.events:
            self.events[event_num] = self._create_event_object(line, 'Individual')

        if place and self.current_team_code:
            self.events[event_num]['results'].append({
                'place': place,
                'swimmer': swimmer_name,
                'teamCode': self.teams[self.current_team_code]['code'],
                'time': final_time,
                'points': points
            })

            if self.current_team_code in self.teams:
                self.teams[self.current_team_code]['score'] += points

    def _parse_e0(self, line: str):
        """Parse E0 record - Relay team result."""
        if len(line) < 99:
            return

        event_num = line[26:30].strip()
        if not event_num or event_num == '0':
            return

        relay_team_char = line[11:12].strip()
        relay_final_time = line[72:80].strip()
        relay_place_str = line[92:95].strip()
        relay_points_str = line[95:99].strip()

        if not relay_place_str:
            self.last_relay_result = None
            return

        relay_place = int(relay_place_str)
        relay_points = float(relay_points_str) if relay_points_str else 0.0

        if event_num not in self.events:
            self.events[event_num] = self._create_event_object(line, 'Relay')

        if relay_place and self.current_team_code:
            team_name = self.teams.get(self.current_team_code, {}).get('name', self.current_team_code)
            team_code = self.teams.get(self.current_team_code, {}).get('code', '')

            relay_result = {
                'place': relay_place,
                'swimmer': f"{team_name} '{relay_team_char}'",
                'teamCode': team_code,
                'time': relay_final_time,
                'points': relay_points,
                'swimmers': []
            }

            self.events[event_num]['results'].append(relay_result)
            self.last_relay_result = relay_result

            if self.current_team_code in self.teams:
                self.teams[self.current_team_code]['score'] += relay_points
        else:
            self.last_relay_result = None

    def _parse_f0(self, line: str):
        """Parse F0 record - Individual relay swimmer names."""
        if self.last_relay_result and len(line) >= 50:
            swimmer_name = line[22:50].strip()
            if swimmer_name:
                self.last_relay_result['swimmers'].append(swimmer_name)

    def _create_event_object(self, line: str, event_type: str) -> Dict:
        """Create event object from SDIF line."""
        if event_type == 'Individual':
            gender_code = line[66:67] if len(line) > 66 else ''
            age_code = line[76:80] if len(line) >= 80 else ''
            distance = line[67:71].strip() if len(line) >= 71 else ''
            stroke_code = line[71:72] if len(line) >= 72 else ''
        else:  # Relay
            gender_code = line[20:21] if len(line) > 20 else ''
            age_code = line[30:34] if len(line) >= 34 else ''
            distance = line[21:25].strip() if len(line) >= 25 else ''
            stroke_code = line[25:26] if len(line) >= 26 else ''

        gender = GENDER_MAP.get(gender_code, 'Unknown')
        age = self._parse_age_code(age_code)
        stroke = STROKE_MAP.get(stroke_code, f'Stroke {stroke_code}')

        # For relays with 'Open' age group, omit age to save space
        if event_type == 'Relay' and age == 'Open':
            age = ''

        description = f"{gender} {age} {distance}m {stroke}".strip()
        description = ' '.join(description.split())  # Normalize whitespace

        return {
            'description': description,
            'results': [],
            'type': event_type
        }

    def _parse_age_code(self, age_code: str) -> str:
        """Parse age code into human-readable format."""
        if not age_code or len(age_code) < 4:
            return 'Open'

        lower_str = age_code[0:2]
        upper_str = age_code[2:4]

        if lower_str == 'UN' and upper_str == 'OV':
            return 'Open'

        if lower_str == 'UN':
            try:
                upper_age = int(upper_str)
                return f'{upper_age} & Under'
            except ValueError:
                return 'Open'

        if upper_str == 'OV':
            try:
                lower_age = int(lower_str)
                return f'{lower_age} & Over'
            except ValueError:
                return 'Open'

        try:
            lower_age = int(lower_str)
            upper_age = int(upper_str)

            if lower_age == upper_age:
                return str(lower_age)

            return f'{lower_age}-{upper_age}'
        except ValueError:
            return 'Open'

    def _generate_meet_title(self):
        """Generate meet title for dual meets."""
        team_list = list(self.teams.values())

        if 'hostName' in self.meet and 'startDate' in self.meet and len(team_list) == 2:
            start_date = self.meet['startDate']
            if len(start_date) == 8:
                year = start_date[4:]
                host_name = self.meet['hostName']

                away_team = None
                for team in team_list:
                    if team['name'] != host_name:
                        away_team = team
                        break

                if away_team:
                    self.meet['name'] = f"{year} {host_name} v. {away_team['name']}"


class HTMLGenerator:
    """Generates HTML output from parsed SDIF data."""

    @staticmethod
    def generate(data: Dict, logo_url: str = LOGO_URL) -> str:
        """Generate complete HTML document."""
        meet = data['meet']
        teams = data['teams']
        events = data['events']

        # Extract winners
        winners = []
        for event_num in sorted(events.keys(), key=lambda x: int(x)):
            event = events[event_num]
            winner = next((r for r in event['results'] if r['place'] == 1), None)
            if winner:
                winners.append({
                    'eventNum': event_num,
                    'description': event['description'],
                    'winnerData': winner,
                    'type': event['type']
                })

        # Generate winners table rows
        winners_rows = []
        for w in winners:
            result = w['winnerData']

            if w['type'] == 'Relay' and result.get('swimmers'):
                winner_cell = '<br>'.join(result['swimmers'])
            else:
                winner_cell = result['swimmer']

            winners_rows.append(
                f'<tr><td class="center">{w["eventNum"]}</td>'
                f'<td>{w["description"]}</td>'
                f'<td>{winner_cell}</td>'
                f'<td class="center">{result.get("teamCode", "")}</td>'
                f'<td class="center">{result["time"]}</td></tr>'
            )

        winners_html = '\n'.join(winners_rows)

        # Generate scores table rows
        sorted_teams = sorted(teams.values(), key=lambda x: x['score'], reverse=True)
        scores_rows = '\n'.join(
            f'<tr><td>{team["name"]}</td><td>{team["score"]:.1f}</td></tr>'
            for team in sorted_teams
        )

        meet_name = meet.get('name', 'Swim Meet Results')
        generation_date = datetime.now().strftime('%Y-%m-%d')

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{meet_name}</title>

    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

    <!-- Favicon Links -->
    <link rel="apple-touch-icon" sizes="180x180" href="https://d1nmxxg9d5tdo.cloudfront.net/875/files/apple-touch-icon.png?1651502524">
    <link rel="icon" type="image/png" sizes="32x32" href="https://d1nmxxg9d5tdo.cloudfront.net/875/files/favicon-32x32.png?1651502547">
    <link rel="icon" type="image/png" sizes="16x16" href="https://d1nmxxg9d5tdo.cloudfront.net/875/files/favicon-16x16.png?1651502535">
    <link rel="manifest" href="https://d1nmxxg9d5tdo.cloudfront.net/875/files/site.webmanifest?1651502732">
    <link rel="mask-icon" href="https://d1nmxxg9d5tdo.cloudfront.net/875/files/safari-pinned-tab.svg?1651502580" color="#5bbad5">
    <meta name="msapplication-TileColor" content="#da532c">
    <meta name="theme-color" content="#ffffff">

    <style>
        /* Base Styles */
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            background-color: #f0f2f5;
            padding: 1rem;
        }}

        .container {{
            max-width: 1280px;
            margin: 0 auto;
            padding: 1.5rem;
            background-color: #fff;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            border-radius: 0.75rem;
        }}

        /* Header Styles */
        header {{
            background-color: #002366;
            color: white;
            padding: 2rem;
            text-align: center;
            border-radius: 0.75rem 0.75rem 0 0;
            margin: -1.5rem -1.5rem 2rem -1.5rem;
        }}

        header img {{
            width: 80px;
            height: 80px;
            margin-bottom: 1rem;
            border-radius: 50%;
            object-fit: cover;
        }}

        header h1 {{
            font-size: 2rem;
            font-weight: 700;
            color: white;
            margin: 0;
        }}

        /* Typography */
        h2 {{
            color: #002366;
            font-size: 1.875rem;
            font-weight: 700;
            text-align: center;
            margin-top: 2.5rem;
            margin-bottom: 1.5rem;
            padding-bottom: 0.75rem;
            border-bottom: 3px solid #d9242b;
        }}

        h2:first-of-type {{
            margin-top: 0;
        }}

        /* Table Styles */
        .table-wrapper {{
            overflow-x: auto;
            margin-bottom: 2rem;
        }}

        .table-wrapper.narrow {{
            max-width: 900px;
            margin-left: auto;
            margin-right: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
        }}

        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            vertical-align: top;
            border: 1px solid #e5e7eb;
        }}

        /* Center-aligned columns */
        .center {{
            text-align: center;
        }}

        thead {{
            background-color: #002366;
            color: white;
        }}

        thead th {{
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }}

        tbody tr {{
            background-color: #ffffff;
        }}

        tbody tr:nth-child(odd) {{
            background-color: #f9fafb;
        }}

        tbody tr:hover {{
            background-color: #f3f4f6;
        }}

        tbody td {{
            color: #374151;
        }}

        tbody td:first-child {{
            font-weight: 500;
            color: #1f2937;
        }}

        /* Footer Styles */
        footer {{
            text-align: center;
            margin-top: 3rem;
            padding-top: 2rem;
            border-top: 1px solid #e5e7eb;
            font-size: 0.875rem;
            color: #6b7280;
        }}

        /* Print Styles */
        @media print {{
            body {{
                background-color: white;
                padding: 0;
            }}

            .container {{
                box-shadow: none;
                padding: 0;
                max-width: 100%;
            }}

            header {{
                margin: 0 0 2rem 0;
            }}
        }}

        /* Responsive Styles */
        @media (max-width: 768px) {{
            body {{
                padding: 0.5rem;
            }}

            .container {{
                padding: 1rem;
                border-radius: 0.5rem;
            }}

            header {{
                padding: 1.5rem 1rem;
                margin: -1rem -1rem 1.5rem -1rem;
            }}

            header img {{
                width: 64px;
                height: 64px;
            }}

            header h1 {{
                font-size: 1.5rem;
            }}

            h2 {{
                font-size: 1.5rem;
                margin-top: 2rem;
            }}

            table {{
                font-size: 0.75rem;
            }}

            th, td {{
                padding: 0.5rem;
            }}

            thead th {{
                font-size: 0.625rem;
            }}
        }}

        @media (min-width: 769px) and (max-width: 1024px) {{
            header h1 {{
                font-size: 1.875rem;
            }}
        }}

        @media (min-width: 1025px) {{
            header img {{
                width: 100px;
                height: 100px;
            }}

            header h1 {{
                font-size: 2.25rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <img src="{logo_url}" alt="GPSA Logo" onerror="this.onerror=null; this.src='https://placehold.co/100x100/002366/FFFFFF?text=GPSA';">
            <h1>{meet_name}</h1>
        </header>

        <main>
            <h2>Team Scores</h2>
            <div class="table-wrapper narrow">
                <table>
                    <thead>
                        <tr>
                            <th>Team</th>
                            <th>Score</th>
                        </tr>
                    </thead>
                    <tbody>{scores_rows}</tbody>
                </table>
            </div>

            <h2>Event Winners</h2>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th class="center">Event</th>
                            <th>Description</th>
                            <th>Winner(s)</th>
                            <th class="center">Team</th>
                            <th class="center">Time</th>
                        </tr>
                    </thead>
                    <tbody>{winners_html}</tbody>
                </table>
            </div>
        </main>

        <footer>
            <p>Results generated on {generation_date} with the GPSA Bulk Meet Results Processor v1.0</p>
        </footer>
    </div>
</body>
</html>"""


class BulkProcessor:
    """Handles bulk processing of SDIF files."""

    def __init__(self, input_dir: Path, output_dir: Path):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.stats = {
            'processed': 0,
            'failed': 0,
            'zips_extracted': 0,
            'files_generated': 0
        }

    def process(self):
        """Process all SDIF and ZIP files in input directory."""
        logger.info(f"Starting bulk processing...")
        logger.info(f"Input directory: {self.input_dir}")
        logger.info(f"Output directory: {self.output_dir}")

        if not self.input_dir.exists():
            logger.error(f"Input directory does not exist: {self.input_dir}")
            return False

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Extract all zip files first
        self._extract_zip_files()

        # Process all .sd3 files
        sd3_files = list(self.input_dir.glob('*.sd3')) + list(self.input_dir.glob('*.SD3'))

        if not sd3_files:
            logger.warning("No .sd3 files found in input directory")
            return False

        logger.info(f"Found {len(sd3_files)} .sd3 file(s) to process")

        for sd3_file in sd3_files:
            self._process_sdif_file(sd3_file)

        # Print summary
        self._print_summary()
        return True

    def _extract_zip_files(self):
        """Extract all .zip files in input directory."""
        zip_files = list(self.input_dir.glob('*.zip')) + list(self.input_dir.glob('*.ZIP'))

        for zip_path in zip_files:
            try:
                logger.info(f"Extracting {zip_path.name}...")

                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # Extract only .sd3 files
                    sd3_members = [m for m in zip_ref.namelist()
                                   if m.lower().endswith('.sd3')]

                    if not sd3_members:
                        logger.warning(f"No .sd3 files found in {zip_path.name}")
                        continue

                    for member in sd3_members:
                        zip_ref.extract(member, self.input_dir)
                        logger.info(f"  Extracted: {member}")

                    self.stats['zips_extracted'] += 1

                # Delete zip file after successful extraction
                zip_path.unlink()
                logger.info(f"Deleted {zip_path.name}")

            except zipfile.BadZipFile:
                logger.error(f"Invalid zip file: {zip_path.name}")
            except Exception as e:
                logger.error(f"Error extracting {zip_path.name}: {str(e)}")

    def _process_sdif_file(self, sd3_path: Path):
        """Process a single SDIF file."""
        try:
            logger.info(f"Processing {sd3_path.name}...")

            # Read file content
            with open(sd3_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Parse SDIF data
            parser = SDIFParser()
            data = parser.parse(content)

            # Generate filename and output path
            filename, year = self._generate_filename(data)

            if not filename:
                logger.error(f"Could not generate filename for {sd3_path.name}")
                self.stats['failed'] += 1
                return

            # Determine output directory
            if year:
                output_path = self.output_dir / str(year)
                output_path.mkdir(parents=True, exist_ok=True)
            else:
                output_path = self.output_dir

            output_file = output_path / filename

            # Generate HTML
            html_content = HTMLGenerator.generate(data)

            # Write output file
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.info(f"  Generated: {output_file.relative_to(self.output_dir)}")

            self.stats['processed'] += 1
            self.stats['files_generated'] += 1

        except Exception as e:
            logger.error(f"Error processing {sd3_path.name}: {str(e)}", exc_info=True)
            self.stats['failed'] += 1

    def _generate_filename(self, data: Dict) -> Tuple[Optional[str], Optional[int]]:
        """Generate output filename from parsed data."""
        meet = data['meet']
        teams = data['teams']

        meet_date = meet.get('startDate', '')

        if not meet_date or len(meet_date) != 8:
            # Fallback to meet name
            meet_name = meet.get('name', 'swim_meet').replace(' ', '_')
            return f"{meet_name}_Results.html", None

        # Parse date MMDDYYYY -> YYYY-MM-DD
        year = meet_date[4:]
        month = meet_date[0:2]
        day = meet_date[2:4]
        formatted_date = f"{year}-{month}-{day}"

        team_list = list(teams.values())

        # For dual meets, use team codes
        if len(team_list) == 2:
            team1_code = team_list[0]['code']
            team2_code = team_list[1]['code']
            filename = f"{formatted_date}_{team1_code}_v_{team2_code}.html"
        else:
            # For multi-team meets, use meet name
            meet_name = meet.get('name', 'meet').replace(' ', '_')
            filename = f"{formatted_date}_{meet_name}.html"

        return filename, int(year)

    def _print_summary(self):
        """Print processing summary."""
        logger.info("=" * 60)
        logger.info("PROCESSING SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Zip files extracted: {self.stats['zips_extracted']}")
        logger.info(f"SDIF files processed: {self.stats['processed']}")
        logger.info(f"HTML files generated: {self.stats['files_generated']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='GPSA Bulk Meet Results Processor - Process SDIF files and generate HTML results',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process files in current directory
  %(prog)s -i ./input -o ./results

  # Process with repository structure
  %(prog)s -i ./meet_files -o ./results
        """
    )

    parser.add_argument(
        '-i', '--input',
        type=str,
        required=True,
        help='Input directory containing .sd3 and/or .zip files'
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        required=True,
        help='Output directory for generated HTML files (year subdirectories will be created automatically)'
    )

    args = parser.parse_args()

    # Convert to Path objects
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()

    # Create processor and run
    processor = BulkProcessor(input_dir, output_dir)
    success = processor.process()

    if success:
        logger.info("Processing completed successfully!")
        return 0
    else:
        logger.error("Processing failed or no files were processed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
