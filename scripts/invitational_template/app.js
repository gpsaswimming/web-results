// GPSA invitational results renderer.
// Data source: window.__MEET__ (inlined by build_invitational.mjs) or ../data/<slug>.json.
//
// Two shapes of meet run through here:
//   scored   (City Meet)      - results carry points; the page leads with the ribbon board.
//   unscored (Summer Splash)  - no points anywhere; the page keeps the medal count.
// Both branches are derived from the data, never from a config flag, so a new meet
// renders correctly without anyone remembering to set something.

// Two different depths, and the page must not blur them:
const MEDAL_DEPTH = 8;      // event ribbons - awarded to 8th in every event, individual and relay
const TEAM_MEDAL_DEPTH = 6; // team medals at City Meet - awarded to the top 6 teams overall

// Set per render, from the data.
let showCutCol = false;  // CM column only when standards were applied
let showPtsCol = false;  // points column only when the meet is scored
let relayRibbons = false; // relays medal only where relays actually score

// Needed by the deep-link handler, which outlives any single render.
let SWIMMERS = {};
let TEAM_NAMES = {};
let closeSheet = null; // set while a profile is open

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Only official ("ok") swims count - a DQ/scratch/DNF time doesn't stand, so it never
// shows a drop, counts as faster-than-seed, or gets highlighted.
const dropOf = (r) => (r.status === 'ok' && r.seed && r.final && r.final.s < r.seed.s ? r.seed.s - r.final.s : 0);
const addOf = (r) => (r.status === 'ok' && r.seed && r.final && r.final.s > r.seed.s ? r.final.s - r.seed.s : 0);
const fmtPts = (p) => (Number.isInteger(p) ? p : p.toFixed(1));
const ordinal = (n) => { const s = ['th', 'st', 'nd', 'rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
const shortName = (n) => n.replace(/^\d{4}\s+GPSA\s+/, '').replace(/\s+Invitational$/, '');

// Search matches on tokens, so "colton mueller" finds "Mueller, Colton A" even though
// the file stores names last-first.
const haystack = (name) => String(name || '').toLowerCase().replace(/[,]/g, ' ');

async function boot() {
  const app = document.getElementById('app');
  try {
    let data = window.__MEET__;
    if (!data) {
      const slug = new URLSearchParams(location.search).get('meet')
        || document.documentElement.dataset.defaultMeet;
      const res = await fetch(`../data/${slug}.json`);
      if (!res.ok) throw new Error(`data ${res.status}`);
      data = await res.json();
    }
    render(app, data);
  } catch (e) {
    app.innerHTML = `<p class="empty">Couldn't load these results. ${esc(e.message)}</p>`;
  }
}

function render(app, data) {
  // Events arrive in file order; render by event number (numeric prefix, then any
  // A/B/C… sub-group suffix) so the meet reads 1 → last regardless of source order.
  const evKey = (e) => { const m = /^(\d+)(.*)$/.exec(e.number); return m ? [+m[1], m[2]] : [1e9, e.number]; };
  data.events.sort((a, b) => { const x = evKey(a), y = evKey(b); return x[0] - y[0] || x[1].localeCompare(y[1]); });

  const teamName = Object.fromEntries(data.teams.map((t) => [t.code, t.name]));
  const allResults = data.events.flatMap((e) => e.results.map((r) => ({ ...r, ev: e })));

  // ---- derived stats -------------------------------------------------------
  const swimmers = new Set(allResults.filter((r) => r.sid).map((r) => r.sid));
  const drops = allResults.filter((r) => dropOf(r) > 0).length;
  const cuts = allResults.filter((r) => r.cut).length;
  const withSeed = allResults.filter((r) => r.seed && r.final).length;
  const teamsWithSwims = new Set(allResults.map((r) => r.team));

  const scored = allResults.some((r) => r.pts);
  showCutCol = !!data.meet.cutsLabel;
  showPtsCol = scored;
  // City Meet scores its four relays 18-14-12-10-8-6-4-2 and medals them like any
  // other event. Summer Splash relays place but score nothing - they're exhibition,
  // so they stay unmedalled.
  relayRibbons = allResults.some((r) => r.kind === 'relay' && r.pts);

  // ---- the ribbon board: points, and the ribbons that earned them ----------
  const agg = {};
  for (const r of allResults) {
    if (!r.pts || !r.place) continue;
    const a = (agg[r.team] ||= { pts: 0, byPlace: {}, count: {} });
    a.pts += r.pts;
    a.byPlace[r.place] = (a.byPlace[r.place] || 0) + r.pts;
    a.count[r.place] = (a.count[r.place] || 0) + 1;
  }
  const scorersOf = (code) => new Set(
    allResults.filter((r) => r.team === code && r.sid && r.pts).map((r) => r.sid)).size;
  const boardRows = Object.entries(agg)
    .map(([code, a]) => ({ code, ...a, scorers: scorersOf(code) }))
    .sort((x, y) => y.pts - x.pts || x.code.localeCompare(y.code));
  const maxPts = boardRows.length ? boardRows[0].pts : 0;

  // ---- medal tally (unscored meets; individual, places 1-3) ----------------
  const medals = {};
  for (const r of allResults) {
    if (r.kind === 'relay' || r.status !== 'ok' || !r.place || r.place > 3) continue;
    const m = (medals[r.team] ||= { g: 0, s: 0, b: 0 });
    if (r.place === 1) m.g++; else if (r.place === 2) m.s++; else m.b++;
  }
  const medalRows = Object.entries(medals)
    .map(([code, m]) => ({ code, ...m, tot: m.g + m.s + m.b }))
    .sort((a, b) => b.g - a.g || b.s - a.s || b.b - a.b || a.code.localeCompare(b.code));

  // ---- swimmer index (for the profile sheet) -------------------------------
  // The profile is the whole point of an unscored meet, so it has to be the swimmer's
  // whole meet. Relay legs carry a name and a team but no swimmer id, so they're
  // resolved back to the swimmer by name within their own team - unambiguous in every
  // published file. A swimmer who ONLY swam a relay has no id anywhere and so has no
  // profile; their name simply isn't a link.
  const bySwimmer = {};
  for (const r of allResults) {
    if (!r.sid) continue;
    (bySwimmer[r.sid] ||= { name: r.name, team: r.team, sid: r.sid, swims: [] }).swims.push(r);
  }
  const sidByName = {};
  for (const r of allResults) {
    if (!r.sid) continue;
    const k = `${r.team}|${r.name}`;
    sidByName[k] = sidByName[k] && sidByName[k] !== r.sid ? null : r.sid; // null = ambiguous
  }
  for (const r of allResults) {
    if (r.kind !== 'relay') continue;
    for (const leg of r.legs || []) {
      const sid = sidByName[`${r.team}|${leg}`];
      if (sid && bySwimmer[sid]) bySwimmer[sid].swims.push(r);
    }
  }
  const evOrder = new Map(data.events.map((e, i) => [e.number, i]));
  for (const s of Object.values(bySwimmer)) {
    s.swims.sort((a, b) => (evOrder.get(a.ev.number) ?? 0) - (evOrder.get(b.ev.number) ?? 0));
  }
  SWIMMERS = bySwimmer;
  TEAM_NAMES = teamName;

  const dateStr = new Date(data.meet.startDate + 'T00:00').toLocaleDateString('en-US',
    { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

  // Tab title, bookmarks and share cards all read this - "GPSA Invitational Results"
  // told nobody which meet they were looking at.
  document.title = `${data.meet.name} — Results`;
  const desc = document.querySelector('meta[name=description]');
  if (desc) {
    desc.content = scored && boardRows.length
      ? `${data.meet.name}: ${teamName[boardRows[0].code] || boardRows[0].code} wins with `
        + `${fmtPts(boardRows[0].pts)} points. Full results for ${swimmers.size} swimmers `
        + `across ${data.events.length} events.`
      : `${data.meet.name}: full results for ${swimmers.size} swimmers across ${data.events.length} events.`;
  }

  app.innerHTML = `
    <header class="hero"><div class="hero-in">
      <div class="eyebrow">${esc(data.meet.eyebrow || 'GPSA Invitational')}</div>
      <h1>${esc(data.meet.name)}</h1>
      <div class="date">${esc(dateStr)}</div>
      ${scored ? champBlock(boardRows, teamName, swimmers.size, data.events.length)
               : statTiles(swimmers.size, teamsWithSwims.size, data.events.length, drops, cuts, data.meet.cutsLabel)}
    </div></header>
    <div class="lane"></div>

    <div class="bar"><div class="bar-in">
      <div class="bar-title">${esc(shortName(data.meet.name))} <span>Results</span></div>
      <div class="ctrl"><input type="search" id="q" placeholder="Search a swimmer…" aria-label="Search swimmer"></div>
      <div class="ctrl"><select id="team" aria-label="Filter by team">
        <option value="">All teams</option>
        ${data.teams.filter((t) => teamsWithSwims.has(t.code))
          .sort((a, b) => a.name.localeCompare(b.name))
          .map((t) => `<option value="${esc(t.code)}">${esc(t.name)}</option>`).join('')}
      </select></div>
      <label class="toggle"><input type="checkbox" id="top8"> Top ${MEDAL_DEPTH} only</label>
    </div></div>

    <main>
      ${scored ? ribbonBoard(boardRows, teamName, maxPts) : medalPanel(medalRows, teamName, data.meet.showMedals)}

      <details class="panel"><summary>Jump to event</summary>
        <div class="panel-body"><div class="jump">
          ${data.events.map((e) => `<a href="#e${esc(e.number)}"><b>#${esc(e.number)}</b> ${esc(e.description)}</a>`).join('')}
        </div></div>
      </details>

      <p class="legend"><span><b>▼ faster than seed</b> (dropped time)</span>
        ${cuts ? `<span><span class="cut">CM</span> made a ${esc(data.meet.cutsLabel)}</span>` : ''}
        <span class="medal-key">${Array.from({ length: MEDAL_DEPTH }, (_, i) =>
          `<span class="chip p${i + 1}">${i + 1}</span>`).join('')} ribbons to ${ordinal(MEDAL_DEPTH)}</span>
        <span>Tap a name for every swim</span></p>

      <div id="events">
        ${data.events.map((e) => eventCard(e)).join('')}
      </div>
      <p class="empty hidden" id="none" role="status">No swims match your filters.</p>
    </main>
    <footer>${esc(data.meet.name)} · ${swimmers.size} swimmers · ${withSeed} swims with a seed time,
      ${drops} faster than seed · <a href="/invitationals/">All GPSA invitationals</a></footer>`;

  wire(app, { bySwimmer, teamName });

  // Arriving on a shared profile link opens it straight away.
  const linked = new URLSearchParams(location.search).get('swimmer');
  if (linked && bySwimmer[linked]) openSheet(bySwimmer[linked], teamName, false);
}

// Scored meets lead with the champion: the score, the margin, and how it was won.
function champBlock(rows, teamName, swimmerCount, eventCount) {
  if (!rows.length) return '';
  const w = rows[0];
  const margin = rows.length > 1 ? w.pts - rows[1].pts : 0;
  const firsts = w.count[1] || 0;
  const bits = [];
  if (margin > 0) bits.push(`<b>Wins by ${fmtPts(margin)}</b> over ${esc(teamName[rows[1].code] || rows[1].code)}`);
  if (firsts) bits.push(`<b>${firsts}</b> first place${firsts === 1 ? '' : 's'}`);
  bits.push(`<b>${w.scorers}</b> swimmer${w.scorers === 1 ? '' : 's'} scored`);
  return `<div class="champ">
    <div>
      <div class="champ-label">League champion</div>
      <h2 class="champ-name">${esc(teamName[w.code] || w.code)}</h2>
      <div class="champ-sub">${bits.join(' · ')}</div>
    </div>
    <div class="champ-pts"><div class="n num">${fmtPts(w.pts)}</div><div class="l">Points</div></div>
  </div>
  <p class="champ-sub" style="margin-top:.9rem">${swimmerCount} swimmers · ${rows.length} teams scoring · ${eventCount} events</p>`;
}

function statTiles(swimmers, teams, events, drops, cuts, cutsLabel) {
  return `<div class="stats">
    <div class="stat"><div class="n num">${swimmers}</div><div class="l">Swimmers</div></div>
    <div class="stat"><div class="n num">${teams}</div><div class="l">Teams</div></div>
    <div class="stat"><div class="n num">${events}</div><div class="l">Events</div></div>
    <div class="stat hl"><div class="n num">${drops}</div><div class="l">Faster than seed</div></div>
    ${cuts ? `<div class="stat gold"><div class="n num">${cuts}</div><div class="l">${esc(cutsLabel || 'Cuts')}</div></div>` : ''}
  </div>`;
}

// Bar length is the score. Bar composition is the ribbons that earned it - so a team
// that won a lot reads blue, and a team that scored on depth reads green and purple.
function ribbonBoard(rows, teamName, maxPts) {
  const key = Array.from({ length: MEDAL_DEPTH }, (_, i) =>
    `<span class="chip p${i + 1}" title="${ordinal(i + 1)} place">${i + 1}</span>`).join('');
  // The line after 6th is where the team medals stop - it is the difference between
  // a medal and nothing, and in 2026 it fell between 144 and 143 points.
  const cut = (i) => (i === TEAM_MEDAL_DEPTH && rows.length > TEAM_MEDAL_DEPTH
    ? `<div class="board-cut"><span>Team medals to ${ordinal(TEAM_MEDAL_DEPTH)}</span></div>` : '');
  return `<section class="board" aria-label="Team scores">
    <div class="board-key">
      <span>Ribbon by place</span><span class="key-scale">${key}</span>
      <span>Bar length = points scored</span>
    </div>
    ${rows.map((t, i) => cut(i) + boardRow(t, i, teamName, maxPts)).join('')}
  </section>`;
}

function boardRow(t, i, teamName, maxPts) {
  const places = Object.keys(t.byPlace).map(Number).sort((a, b) => a - b);
  const segs = places.map((p) =>
    `<span class="board-seg p${p}" style="flex:${t.byPlace[p]}"></span>`).join('');
  const facts = places.map((p) =>
    `<span class="fact"><span class="chip p${p}">${p}</span><b>${t.count[p]}</b> × ${ordinal(p)}
      = <b>${fmtPts(t.byPlace[p])}</b></span>`).join('');
  const spoken = places.map((p) => `${t.count[p]} ${ordinal(p)}`).join(', ');
  const medals = i < TEAM_MEDAL_DEPTH ? ' medals' : '';
  return `<details class="board-row${i === 0 ? ' first' : ''}${medals}" data-team="${esc(t.code)}">
    <summary aria-label="${esc(teamName[t.code] || t.code)}, ${ordinal(i + 1)}${medals ? ', team medal' : ''}, ${fmtPts(t.pts)} points: ${spoken}">
      <span class="board-rank num">${i + 1}</span>
      <span class="board-team">${esc(teamName[t.code] || t.code)}</span>
      <span class="board-bar-cell"><span class="board-bar" style="--w:${(t.pts / maxPts * 100).toFixed(1)}%">${segs}</span></span>
      <span class="board-pts num">${fmtPts(t.pts)}</span>
    </summary>
    <div class="board-detail">${facts}
      <span class="fact plain"><b>${t.scorers}</b> swimmers scored</span>
      <button type="button" class="fact plain only-team" data-team="${esc(t.code)}">Show only this team</button>
    </div>
  </details>`;
}

function medalPanel(rows, teamName, showMedals) {
  if (!showMedals || !rows.length) return '';
  return `<details class="panel" open><summary>Team medal count</summary>
    <div class="panel-body"><table class="medals"><thead><tr>
      <th></th><th>Team</th><th>1st</th><th>2nd</th><th>3rd</th><th>Total</th>
    </tr></thead><tbody>
      ${rows.map((m, i) => `<tr data-team="${esc(m.code)}" tabindex="0" role="button"
          aria-label="Show only ${esc(teamName[m.code] || m.code)}">
        <td class="rank num">${i + 1}</td>
        <td>${esc(teamName[m.code] || m.code)}</td>
        <td class="num">${m.g || ''}</td><td class="num">${m.s || ''}</td>
        <td class="num">${m.b || ''}</td><td class="num tot">${m.tot}</td>
      </tr>`).join('')}
    </tbody></table></div>
  </details>`;
}

function eventCard(e) {
  const rows = e.results.map((r) => (r.kind === 'relay' ? relayRow(r) : indivRow(r))).join('');
  return `<section class="event" id="e${esc(e.number)}" data-num="${esc(e.number)}">
    <div class="ev-head"><span class="ev-num">EVENT ${esc(e.number)}</span>
      <h2 class="ev-title">${esc(e.description)}</h2></div>
    <div class="tbl-wrap"><table class="res">
      <colgroup><col class="c-pl"><col class="c-name"><col class="c-team"><col class="c-seed"><col class="c-time"><col class="c-pm">${showPtsCol ? '<col class="c-pts">' : ''}${showCutCol ? '<col class="c-cm">' : ''}<col class="c-flex"></colgroup>
      <thead><tr>
      <th class="r">Pl</th><th>Swimmer</th><th>Team</th>
      <th class="r col-seed">Seed</th><th class="r">Time</th><th class="r">±</th>${showPtsCol ? '<th class="r">Pts</th>' : ''}${showCutCol ? '<th class="c">CM</th>' : ''}<td class="t-flex"></td>
    </tr></thead><tbody>${rows}</tbody></table></div>
  </section>`;
}

function indivRow(r) {
  const d = dropOf(r), a = addOf(r);
  let placeCell, timeCell, dropCell;
  if (r.status === 'ok') {
    const cls = r.place && r.place <= MEDAL_DEPTH ? ` p${r.place}` : '';
    placeCell = r.place ? `<span class="pl${cls}">${r.place}</span>` : '';
    timeCell = r.final ? `<span class="num">${esc(r.final.t)}</span>` : '';
    dropCell = d > 0 ? `<span class="drop num">▼ ${d.toFixed(2)}</span>`
      : a > 0 ? `<span class="addt num">▲ ${a.toFixed(2)}</span>` : '';
  } else {
    // DQ/scratch/DNF: the time doesn't stand, so no place, no time, no drop.
    placeCell = '';
    timeCell = '';
    dropCell = `<span class="badge ${r.dq ? 'dq' : 'sc'}">${r.dq ? 'DQ' : esc(r.status)}</span>`;
  }
  return `<tr data-name="${esc(haystack(r.name))}" data-team="${esc(r.team)}"
      data-place="${r.place || 99}" data-sid="${esc(r.sid)}">
    <td class="r t-pl">${placeCell}</td>
    <td class="name t-name"><button class="swm" data-sid="${esc(r.sid)}">${esc(r.name)}</button></td>
    <td class="t-team"><span class="team">${esc(r.team)}</span></td>
    <td class="r col-seed num t-seed">${r.seed ? esc(r.seed.t) : ''}</td>
    <td class="r t-time">${timeCell}</td>
    <td class="r t-pm">${dropCell}</td>
    ${showPtsCol ? `<td class="r t-end">${r.pts ? `<span class="pts num">${fmtPts(r.pts)}</span>` : ''}</td>` : ''}
    ${showCutCol ? `<td class="c t-end">${r.cut ? '<span class="cut">CM</span>' : ''}</td>` : ''}
    <td class="t-flex"></td>
  </tr>`;
}

// Relays: team + letter + leg names, no individual swimmer. Ribbon colors only where
// relays actually score (City Meet); elsewhere they're exhibition and stay plain.
function relayRow(r) {
  const ok = r.status === 'ok';
  const d = dropOf(r);
  const cls = relayRibbons && r.place && r.place <= MEDAL_DEPTH ? ` p${r.place}` : '';
  const placeCell = ok && r.place ? `<span class="pl${cls}">${r.place}</span>` : '';
  const timeCell = ok && r.final ? `<span class="num">${esc(r.final.t)}</span>` : '';
  const endCell = !ok ? `<span class="badge ${r.dq ? 'dq' : 'sc'}">${r.dq ? 'DQ' : esc(r.status)}</span>`
    : d > 0 ? `<span class="drop num">▼ ${d.toFixed(2)}</span>` : '';
  // Legs are stored "Last, First" - joining them with a comma reads as twice as many
  // people as actually swam, so they're separated with a middot.
  const legs = (r.legs || []);
  return `<tr data-name="${esc(haystack(legs.join(' ')))}" data-team="${esc(r.team)}"
      data-place="${r.place || 99}" data-sid="">
    <td class="r t-pl">${placeCell}</td>
    <td class="name t-name"><span class="relay-tag">'${esc(r.letter)}' relay</span><span class="legs">${legs.map(esc).join(' · ')}</span></td>
    <td class="t-team"><span class="team">${esc(r.team)}</span></td>
    <td class="r col-seed num t-seed">${r.seed ? esc(r.seed.t) : ''}</td>
    <td class="r t-time">${timeCell}</td>
    <td class="r t-pm">${endCell}</td>
    ${showPtsCol ? `<td class="r t-end">${r.pts ? `<span class="pts num">${fmtPts(r.pts)}</span>` : ''}</td>` : ''}
    ${showCutCol ? '<td class="c t-end"></td>' : ''}
    <td class="t-flex"></td>
  </tr>`;
}

function wire(app, { bySwimmer, teamName }) {
  const q = app.querySelector('#q');
  const team = app.querySelector('#team');
  const top8 = app.querySelector('#top8');
  const none = app.querySelector('#none');
  const events = [...app.querySelectorAll('.event')];

  // Anchor jumps must clear the sticky bar, which is three rows tall on a phone.
  const bar = app.querySelector('.bar');
  const setStick = () => document.documentElement.style.setProperty(
    '--stick', `${Math.round(bar.getBoundingClientRect().height) + 8}px`);
  setStick();
  addEventListener('resize', setStick);

  const apply = () => {
    const toks = q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const t = team.value;
    const only8 = top8.checked;
    let anyVisible = false;
    for (const ev of events) {
      let shown = 0;
      for (const tr of ev.querySelectorAll('tbody tr')) {
        const ok = toks.every((tok) => tr.dataset.name.includes(tok))
          && (!t || tr.dataset.team === t)
          && (!only8 || +tr.dataset.place <= MEDAL_DEPTH);
        tr.classList.toggle('hidden', !ok);
        if (ok) shown++;
      }
      ev.classList.toggle('hidden', shown === 0);
      if (shown) anyVisible = true;
    }
    none.classList.toggle('hidden', anyVisible);

    // The board is a ranking, so filtering never removes teams from it - a lone bar
    // has nothing to be long relative to, and a placing means nothing without the
    // teams either side of it. The selected team is highlighted in place instead.
    for (const row of app.querySelectorAll('.board-row')) {
      const picked = !!t && row.dataset.team === t;
      row.classList.toggle('focus', picked);
      if (picked) row.open = true;
    }
  };

  q.addEventListener('input', apply);
  team.addEventListener('change', apply);
  top8.addEventListener('change', apply);

  const filterTo = (code) => {
    team.value = code;
    apply();
    document.getElementById('events').scrollIntoView({ behavior: 'smooth' });
  };

  // medal row (unscored meets) → set team filter; reachable by keyboard
  app.querySelectorAll('.medals tbody tr').forEach((tr) => {
    tr.addEventListener('click', () => filterTo(tr.dataset.team));
    tr.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); filterTo(tr.dataset.team); }
    });
  });

  app.addEventListener('click', (e) => {
    const only = e.target.closest('.only-team');
    if (only) { filterTo(only.dataset.team); return; }
    const btn = e.target.closest('.swm');
    if (btn) openSheet(bySwimmer[btn.dataset.sid], teamName);
  });
}

// The URL carries the open profile, so a coach can send "here's your swimmer" and the
// back button closes the sheet instead of leaving the page.
function profileUrl(sid) {
  const u = new URL(location.href);
  if (sid) u.searchParams.set('swimmer', sid); else u.searchParams.delete('swimmer');
  return u.toString();
}

addEventListener('popstate', () => {
  const sid = new URLSearchParams(location.search).get('swimmer');
  if (sid && SWIMMERS[sid]) openSheet(SWIMMERS[sid], TEAM_NAMES, false);
  else if (closeSheet) closeSheet(false);
});

function openSheet(sw, teamName, push = true) {
  if (!sw) return;
  const modal = document.getElementById('modal');
  const opener = document.activeElement;
  if (push) history.pushState({ swimmer: sw.sid }, '', profileUrl(sw.sid));

  const rows = sw.swims.map((r) => {
    const relay = r.kind === 'relay';
    const d = dropOf(r);
    const ok = r.status === 'ok';
    const time = ok && r.final ? r.final.t : '—';
    // Built as a list and joined, so a swim with no place/cut/drop can't leave a
    // dangling separator behind it.
    const end = [];
    if (ok && r.place) end.push(ordinal(r.place));
    if (ok && r.pts) end.push(`<span class="pts num">${fmtPts(r.pts)} pts</span>`);
    if (ok && r.cut) end.push('<span class="cut">CM</span>');
    if (ok && d > 0) end.push(`<span class="drop num">▼ ${d.toFixed(2)}</span>`);
    if (!ok) end.push(`<span class="badge ${r.dq ? 'dq' : 'sc'}">${r.dq ? 'DQ' : esc(r.status)}</span>`);
    return `<div class="swim-row">
      <div class="ev">EV ${esc(r.ev.number)} · ${esc(r.ev.description)}${
        relay ? ` · <span class="relay-tag">'${esc(r.letter)}' relay</span>` : ''}</div>
      <div class="time num">${esc(time)}</div>
      <div class="seed num">${relay ? 'team time'
        : r.seed ? 'seed ' + esc(r.seed.t) : ''}</div>
      <div class="end">${end.join(' · ')}</div>
    </div>`;
  }).join('');

  const relays = sw.swims.filter((r) => r.kind === 'relay').length;
  const indiv = sw.swims.length - relays;
  const count = `${indiv} swim${indiv === 1 ? '' : 's'}`
    + (relays ? ` · ${relays} relay${relays === 1 ? '' : 's'}` : '');

  modal.innerHTML = `<div class="sheet">
    <div class="sheet-head">
      <div class="sheet-id"><h3 id="sheet-name">${esc(sw.name)}</h3>
        <div class="sub">${esc(teamName[sw.team] || sw.team)} · ${count}</div></div>
      <button class="sheet-link" type="button">Copy link</button>
      <button class="sheet-close" type="button" aria-label="Close">×</button>
    </div><div class="sheet-body">${rows}</div></div>`;
  modal.classList.add('open');

  const closeBtn = modal.querySelector('.sheet-close');
  const linkBtn = modal.querySelector('.sheet-link');
  closeBtn.focus();

  const close = (goBack = true) => {
    modal.classList.remove('open');
    modal.innerHTML = '';
    document.removeEventListener('keydown', onKey);
    closeSheet = null;
    if (goBack && new URLSearchParams(location.search).get('swimmer')) history.back();
    if (opener && opener.isConnected) opener.focus();
  };
  closeSheet = close;

  // Keep Tab inside the sheet while it's open.
  const onKey = (e) => {
    if (e.key === 'Escape') { close(); return; }
    if (e.key !== 'Tab') return;
    const f = [...modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
      .filter((el) => el.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  linkBtn.onclick = async () => {
    try {
      await navigator.clipboard.writeText(profileUrl(sw.sid));
      linkBtn.textContent = 'Link copied';
    } catch {
      linkBtn.textContent = 'Press Ctrl+C to copy';
    }
    setTimeout(() => { linkBtn.textContent = 'Copy link'; }, 2000);
  };
  closeBtn.onclick = () => close();
  modal.onclick = (e) => { if (e.target === modal) close(); };
  document.addEventListener('keydown', onKey);
}

boot();
