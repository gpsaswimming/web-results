#!/usr/bin/env node
// Build an invitational results page from a meet file.
//
//   node build_invitational.mjs <meetFile> <slug> [outDir]
//
// Parses the .sd3/.hy3 with swimparse under the GPSA league profile (which strips
// birthdates at the parse boundary — the output is DOB-free and safe to publish),
// slims it to what the renderer needs, and writes into <outDir> (default: invitationals/):
//   <slug>.html   results page (renderer + data inlined; styles from the shared CDN)
//   <slug>.json   the NormalizedMeet data feed (reusable; index tool ignores it)
//
// Pass an existing <slug>.json as <meetFile> to re-render a published meet against the
// current template without needing the original .sd3 — the JSON is the renderer contract.
//
// The renderer source (shell.html, app.js) lives in scripts/invitational_template/; styles
// come from the shared CDN (web-css/gpsa-results.css).

import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse, GPSA } from '../../app-tools/swimparse/src/index.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Flags: --exclude 53,54 drops those event numbers (numeric prefix, so 54B/54C go too);
// --standards <csv> overrides the auto-resolved City Meet cuts file; --no-standards skips
// cut matching. Everything else is positional: <meetFile> <slug> [outDir].
const argv = process.argv.slice(2);
const takeFlag = (name) => {
  const i = argv.indexOf(name);
  if (i === -1) return undefined;
  const v = argv[i + 1] ?? '';
  argv.splice(i, 2);
  return v;
};
const noStandards = argv.includes('--no-standards');
if (noStandards) argv.splice(argv.indexOf('--no-standards'), 1);
const showMedals = argv.includes('--medals'); // team medal count is opt-in (team-scored meets)
if (showMedals) argv.splice(argv.indexOf('--medals'), 1);
const excludeArg = takeFlag('--exclude') ?? '';
const standardsArg = takeFlag('--standards');
const titleArg = takeFlag('--title'); // override the meet name (SDIF truncates it, e.g. "…Invita")
const eyebrowArg = takeFlag('--eyebrow'); // hero eyebrow label (default "GPSA Invitational")
const [meetFile, slug, outDirArg] = argv;
const excluded = new Set(excludeArg.split(',').map((s) => s.trim()).filter(Boolean));
const eventNum = (n) => (/^(\d+)/.exec(n) || [])[1];

if (!meetFile || !slug) {
  console.error('usage: node build_invitational.mjs <meetFile> <slug> [outDir] '
    + '[--exclude 53,54] [--standards cuts.csv | --no-standards] [--medals] [--title "…"] [--eyebrow "…"]');
  process.exit(1);
}

// City Meet qualifying cuts: season-scoped CSVs live in app-census/data/standards/
// named <startYear>-<endYear>.csv. Resolve the one covering the meet year, build a
// lookup keyed by gender|distance|stroke|ageGroup → qualifying seconds.
function loadCuts(meetYear) {
  let csvPath = standardsArg;
  if (!csvPath && !noStandards) {
    const dir = join(__dirname, '..', '..', 'app-census', 'data', 'standards');
    if (existsSync(dir)) {
      for (const f of readdirSync(dir)) {
        const m = /^(\d{4})-(\d{4})\.csv$/.exec(f);
        if (m && meetYear >= +m[1] && meetYear <= +m[2]) { csvPath = join(dir, f); break; }
      }
    }
  }
  if (!csvPath || !existsSync(csvPath)) return { map: null, path: null };
  const rows = readFileSync(csvPath, 'utf8').trim().split(/\r?\n/);
  const head = rows[0].split(',');
  const col = (k) => head.indexOf(k);
  const map = new Map();
  for (const line of rows.slice(1)) {
    const c = line.split(',');
    const key = `${c[col('gender')]}|${+c[col('distance')]}|${c[col('stroke')]}|${c[col('age_group')]}`;
    map.set(key, +c[col('standard_seconds')]);
  }
  return { map, path: csvPath };
}

const outDir = resolve(outDirArg ?? join(__dirname, '..', 'invitationals'));
const tplDir = join(__dirname, 'invitational_template');

// Re-render path: a .json input is already the renderer contract, so skip parsing.
const fromJson = /\.json$/i.test(meetFile);
const text = readFileSync(resolve(meetFile), 'utf8');
const meet = fromJson ? null : parse(text, { filename: meetFile, league: GPSA });

// --- City Meet cuts ---------------------------------------------------------
const cuts = fromJson ? { map: null, path: null } : loadCuts(+meet.meet.startDate.slice(0, 4));

// --- slim to the renderer contract -----------------------------------------
const num = (t) => (t && t.seconds > 0 ? { t: t.text, s: t.seconds } : null);
const data = fromJson ? JSON.parse(text) : {
  meet: {
    name: titleArg || meet.meet.name,
    startDate: meet.meet.startDate,
    ...(eyebrowArg ? { eyebrow: eyebrowArg } : {}),
    ...(cuts.map ? { cutsLabel: 'City Meet cut' } : {}),
    ...(showMedals ? { showMedals: true } : {}),
  },
  teams: meet.teams.map((t) => ({ code: t.code, name: t.name })),
  events: meet.events
    .filter((e) => e.results && e.results.length && !excluded.has(eventNum(e.number)))
    .map((e) => {
      const cutSec = cuts.map ? cuts.map.get(`${e.gender}|${e.distance}|${e.stroke}|${e.ageGroup ? e.ageGroup.label : ''}`) : undefined;
      return {
        number: e.number,
        description: e.description,
        gender: e.gender,
        distance: e.distance,
        stroke: e.stroke,
        ageGroup: e.ageGroup ? e.ageGroup.label : '',
        results: e.results.map((r) => {
          const final = num(r.finalTime);
          const place = r.status === 'ok' ? r.place : null;
          if (r.kind === 'relay') {
            // Relays: team + letter + leg names, no individual swimmer / seed / cut.
            return {
              kind: 'relay',
              team: r.teamCode,
              letter: r.relayLetter || '',
              legs: (r.legs || []).map((l) => l.name),
              seed: num(r.seedTime),
              final,
              place,
              status: r.status,
              dq: !!r.disqualified,
              ...(r.points ? { pts: r.points } : {}),
            };
          }
          const rec = {
            name: r.swimmerName,
            team: r.teamCode,
            sid: r.swimmerId,
            seed: num(r.seedTime),
            final,
            place,
            status: r.status,
            dq: !!r.disqualified,
          };
          if (cutSec != null && r.status === 'ok' && final && final.s <= cutSec) rec.cut = true;
          if (r.points) rec.pts = r.points;
          return rec;
        }),
      };
    }),
};

// --- write outputs into <outDir> --------------------------------------------
mkdirSync(outDir, { recursive: true });
// On a re-render the data feed is the input — leave it untouched.
if (!fromJson) writeFileSync(join(outDir, `${slug}.json`), JSON.stringify(data));

// Inline the renderer + data. Styles are NOT inlined: the page links
// css.gpsaswimming.org/gpsa-results.css, the same shared CDN every other GPSA
// property uses, so a styling fix ships once instead of rebuilding every meet page.
const js = readFileSync(join(tplDir, 'app.js'), 'utf8');
const shell = readFileSync(join(tplDir, 'shell.html'), 'utf8');

const page = shell.replace(
  '<script type="module" src="app.js"></script>',
  `<script>window.__MEET__ = ${JSON.stringify(data)};</script>\n<script type="module">\n${js}\n</script>`,
);

writeFileSync(join(outDir, `${slug}.html`), page);

const flat = data.events.flatMap((e) => e.results);
const drops = flat.filter((r) => r.status === 'ok' && r.seed && r.final && r.final.s < r.seed.s).length;
const cutCount = flat.filter((r) => r.cut).length;
console.log(`✓ ${slug}: ${data.teams.length} teams, ${data.events.length} events, ` +
  `${flat.length} swims, ${drops} time drops`);
console.log(`  cuts:    ${fromJson ? `${cutCount} carried in the data feed`
  : cuts.path ? `${cutCount} City Meet cuts (${cuts.path})` : 'none (no standards)'}`);
console.log(`  scored:  ${flat.some((r) => r.pts) ? 'yes — ribbon board'
  : 'no — medal count'}${flat.some((r) => r.kind === 'relay' && r.pts) ? ', relays medal' : ''}`);
console.log(`  page:    ${join(outDir, `${slug}.html`)}`);
if (!fromJson) console.log(`  data:    ${join(outDir, `${slug}.json`)}`);
