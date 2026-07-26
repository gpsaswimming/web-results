// GPSA invitational results renderer.
// Data source: window.__MEET__ (inlined preview) or fetch ../data/<slug>.json.

const MEDAL_DEPTH = 8; // this league awards medals to 8th place
let showCutCol = true; // set per-render: the CM column only appears when the meet has cuts

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Only official ("ok") swims count — a DQ/scratch/DNF time doesn't stand, so it never
// shows a drop, counts as faster-than-seed, or gets highlighted.
const dropOf = (r) => (r.status === 'ok' && r.seed && r.final && r.final.s < r.seed.s ? r.seed.s - r.final.s : 0);
const addOf = (r) => (r.status === 'ok' && r.seed && r.final && r.final.s > r.seed.s ? r.final.s - r.seed.s : 0);
// boot() is invoked at the END of this file, after every const/helper is initialized —
// with inlined data render() runs synchronously, so nothing can be in its TDZ.

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
  showCutCol = !!data.meet.cutsLabel; // no CM column when standards weren't applied (e.g. City Meet)

  // ---- team scores (points carried in the file; e.g. City Meet 9-7-6-5-4…) -
  const scored = allResults.some((r) => r.pts);
  const teamPts = {};
  if (scored) for (const r of allResults) if (r.pts) teamPts[r.team] = (teamPts[r.team] || 0) + r.pts;
  const scoreRows = Object.entries(teamPts).map(([code, pts]) => ({ code, pts }))
    .sort((a, b) => b.pts - a.pts || a.code.localeCompare(b.code));
  const fmtPts = (p) => (Number.isInteger(p) ? p : p.toFixed(1));

  // ---- medal tally (individual, places 1-3) --------------------------------
  const medals = {};
  for (const r of allResults) {
    if (r.status !== 'ok' || !r.place || r.place > 3) continue;
    const m = (medals[r.team] ||= { g: 0, s: 0, b: 0 });
    if (r.place === 1) m.g++; else if (r.place === 2) m.s++; else m.b++;
  }
  const medalRows = Object.entries(medals)
    .map(([code, m]) => ({ code, ...m, tot: m.g + m.s + m.b }))
    .sort((a, b) => b.g - a.g || b.s - a.s || b.b - a.b || a.code.localeCompare(b.code));

  // ---- swimmer index (for the profile sheet) -------------------------------
  const bySwimmer = {};
  for (const r of allResults) {
    if (!r.sid) continue; // relay legs have no swimmer id — not in the per-swimmer index
    (bySwimmer[r.sid] ||= { name: r.name, team: r.team, swims: [] }).swims.push(r);
  }

  const dateStr = new Date(data.meet.startDate + 'T00:00').toLocaleDateString('en-US',
    { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

  const medalPanel = data.meet.showMedals ? `
      <details class="panel" open><summary>🏅 Team medal count</summary>
        <div class="panel-body"><table class="medals"><thead><tr>
          <th></th><th>Team</th><th>🥇</th><th>🥈</th><th>🥉</th><th>Total</th>
        </tr></thead><tbody>
          ${medalRows.map((m, i) => `<tr data-team="${esc(m.code)}">
            <td class="rank num">${i + 1}</td>
            <td>${esc(teamName[m.code] || m.code)}</td>
            <td class="num">${m.g || ''}</td><td class="num">${m.s || ''}</td>
            <td class="num">${m.b || ''}</td><td class="num tot">${m.tot}</td>
          </tr>`).join('')}
        </tbody></table></div>
      </details>` : '';

  // A scored meet (City Meet) leads with team points; otherwise fall back to the
  // opt-in medal count. Clicking a row filters the page to that team (wired via .medals).
  const scoresPanel = `
      <details class="panel" open><summary>🏆 Team scores</summary>
        <div class="panel-body"><table class="medals"><thead><tr>
          <th></th><th>Team</th><th>Points</th>
        </tr></thead><tbody>
          ${scoreRows.map((t, i) => `<tr data-team="${esc(t.code)}">
            <td class="rank num">${i + 1}</td>
            <td>${esc(teamName[t.code] || t.code)}</td>
            <td class="num tot">${fmtPts(t.pts)}</td>
          </tr>`).join('')}
        </tbody></table></div>
      </details>`;
  const teamPanel = scored ? scoresPanel : medalPanel;

  app.innerHTML = `
    <header class="hero"><div class="hero-in">
      <div class="eyebrow">${esc(data.meet.eyebrow || 'GPSA Invitational')}</div>
      <h1>${esc(data.meet.name)}</h1>
      <div class="date">${esc(dateStr)}</div>
      <div class="stats">
        <div class="stat"><div class="n num">${swimmers.size}</div><div class="l">Swimmers</div></div>
        <div class="stat"><div class="n num">${teamsWithSwims.size}</div><div class="l">Teams</div></div>
        <div class="stat"><div class="n num">${data.events.length}</div><div class="l">Events</div></div>
        <div class="stat hl"><div class="n num">${drops}</div><div class="l">Faster than seed</div></div>
        ${cuts ? `<div class="stat gold"><div class="n num">${cuts}</div><div class="l">City Meet cuts</div></div>` : ''}
      </div>
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
      <label class="toggle"><input type="checkbox" id="top8"> Top 8 only</label>
    </div></div>

    <main>
      ${teamPanel}

      <details class="panel"><summary>↳ Jump to event</summary>
        <div class="panel-body"><div class="jump">
          ${data.events.map((e) => `<a href="#e${esc(e.number)}"><b>#${esc(e.number)}</b> ${esc(shortEvent(e))}</a>`).join('')}
        </div></div>
      </details>

      <p class="legend"><span><b>▼ faster than seed</b> (dropped time)</span>
        ${cuts ? '<span><span class="cut">CM</span> made a City Meet qualifying time</span>' : ''}
        <span class="medal-key">${Array.from({ length: MEDAL_DEPTH }, (_, i) =>
          `<span class="pl p${i + 1}">${i + 1}</span>`).join('')} medals to 8th</span>
        <span>Tap a name for every swim</span></p>

      <div id="events">
        ${data.events.map((e) => eventCard(e)).join('')}
      </div>
      <p class="empty hidden" id="none">No swims match your filters.</p>
    </main>
    <footer>${esc(data.meet.name)} · ${withSeed} swims with a seed time, ${drops} faster than seed ·
      <a href="/invitationals/">All GPSA invitationals</a></footer>`;

  wire(app, { bySwimmer, teamName });
}

function eventCard(e) {
  const rows = e.results.map((r) => (r.kind === 'relay' ? relayRow(r) : indivRow(r))).join('');
  return `<section class="event" id="e${esc(e.number)}" data-num="${esc(e.number)}">
    <div class="ev-head"><span class="ev-num">EVENT ${esc(e.number)}</span>
      <span class="ev-title">${esc(e.description)}</span></div>
    <div class="tbl-wrap"><table class="res">
      <colgroup><col class="c-pl"><col class="c-name"><col class="c-team"><col class="c-seed"><col class="c-time"><col class="c-pm">${showCutCol ? '<col class="c-cm">' : ''}</colgroup>
      <thead><tr>
      <th class="r">Pl</th><th>Swimmer</th><th>Team</th>
      <th class="r col-seed">Seed</th><th class="r">Time</th><th class="r">±</th>${showCutCol ? '<th class="c">CM</th>' : ''}
    </tr></thead><tbody>${rows}</tbody></table></div>
  </section>`;
}

function indivRow(r) {
  const d = dropOf(r), a = addOf(r);
  let placeCell, timeCell, dropCell;
  if (r.status === 'ok') {
    // GPSA place-ribbon color for 1st-8th; 9+ get no award color.
    const cls = r.place && r.place <= MEDAL_DEPTH ? ` p${r.place}` : '';
    placeCell = r.place ? `<span class="pl${cls}">${r.place}</span>` : '';
    timeCell = r.final ? `<span class="num">${esc(r.final.t)}</span>` : '';
    dropCell = d > 0 ? `<span class="drop num">▼ ${d.toFixed(2)}</span>`
      : a > 0 ? `<span class="addt num">▲ ${a.toFixed(2)}</span>` : '';
  } else {
    // DQ/scratch/DNF: the time doesn't stand, so no place, no time, no drop — just the reason.
    placeCell = '';
    timeCell = '';
    dropCell = `<span class="badge ${r.dq ? 'dq' : 'sc'}">${r.dq ? 'DQ' : r.status}</span>`;
  }
  const cutCell = r.cut ? '<span class="cut">CM</span>' : '';
  return `<tr data-name="${esc(r.name.toLowerCase())}" data-team="${esc(r.team)}"
      data-place="${r.place || 99}" data-sid="${esc(r.sid)}">
    <td class="r">${placeCell}</td>
    <td class="name"><button class="swm" data-sid="${esc(r.sid)}">${esc(r.name)}</button></td>
    <td><span class="team">${esc(r.team)}</span></td>
    <td class="r col-seed num">${r.seed ? esc(r.seed.t) : ''}</td>
    <td class="r">${timeCell}</td>
    <td class="r">${dropCell}</td>
    ${showCutCol ? `<td class="c">${cutCell}</td>` : ''}
  </tr>`;
}

// Relays: team + letter + leg names, no individual swimmer, no medal color (no relay
// medals in this league), no City Meet cut.
function relayRow(r) {
  const ok = r.status === 'ok';
  const d = dropOf(r);
  const placeCell = ok && r.place ? `<span class="pl">${r.place}</span>` : '';
  const timeCell = ok && r.final ? `<span class="num">${esc(r.final.t)}</span>` : '';
  const endCell = !ok ? `<span class="badge ${r.dq ? 'dq' : 'sc'}">${r.dq ? 'DQ' : r.status}</span>`
    : d > 0 ? `<span class="drop num">▼ ${d.toFixed(2)}</span>` : '';
  const legNames = (r.legs || []).join(', ');
  return `<tr data-name="${esc(legNames.toLowerCase())}" data-team="${esc(r.team)}"
      data-place="${r.place || 99}" data-sid="">
    <td class="r">${placeCell}</td>
    <td class="name"><span class="relay-tag">'${esc(r.letter)}' relay</span> ${esc(legNames)}</td>
    <td><span class="team">${esc(r.team)}</span></td>
    <td class="r col-seed num">${r.seed ? esc(r.seed.t) : ''}</td>
    <td class="r">${timeCell}</td>
    <td class="r">${endCell}</td>
    ${showCutCol ? '<td class="c"></td>' : ''}
  </tr>`;
}

function wire(app, { bySwimmer, teamName }) {
  const q = app.querySelector('#q');
  const team = app.querySelector('#team');
  const top8 = app.querySelector('#top8');
  const none = app.querySelector('#none');
  const events = [...app.querySelectorAll('.event')];

  const apply = () => {
    const needle = q.value.trim().toLowerCase();
    const t = team.value;
    const only8 = top8.checked;
    let anyVisible = false;
    for (const ev of events) {
      let shown = 0;
      for (const tr of ev.querySelectorAll('tbody tr')) {
        const ok = (!needle || tr.dataset.name.includes(needle))
          && (!t || tr.dataset.team === t)
          && (!only8 || +tr.dataset.place <= 8);
        tr.classList.toggle('hidden', !ok);
        if (ok) shown++;
      }
      ev.classList.toggle('hidden', shown === 0);
      if (shown) anyVisible = true;
    }
    none.classList.toggle('hidden', anyVisible);
  };

  q.addEventListener('input', apply);
  team.addEventListener('change', apply);
  top8.addEventListener('change', apply);

  // medal row → set team filter
  app.querySelectorAll('.medals tbody tr').forEach((tr) => {
    tr.addEventListener('click', () => {
      team.value = tr.dataset.team; apply();
      document.getElementById('events').scrollIntoView({ behavior: 'smooth' });
    });
  });

  // swimmer name → profile sheet
  app.addEventListener('click', (e) => {
    const btn = e.target.closest('.swm');
    if (btn) openSheet(bySwimmer[btn.dataset.sid], teamName);
  });
}

function openSheet(sw, teamName) {
  if (!sw) return;
  const modal = document.getElementById('modal');
  const rows = sw.swims.map((r) => {
    const d = dropOf(r);
    const ok = r.status === 'ok';
    const time = ok && r.final ? r.final.t : '—';
    const tail = !ok ? `<span class="badge ${r.dq ? 'dq' : 'sc'}">${r.dq ? 'DQ' : r.status}</span>`
      : `${r.cut ? '<span class="cut">CM</span> ' : ''}${d > 0 ? `<span class="drop num">▼ ${d.toFixed(2)}</span>` : ''}`;
    const pl = ok && r.place ? `${ordinal(r.place)} · ` : '';
    return `<div class="swim-row">
      <div class="ev">EV ${esc(r.ev.number)} · ${esc(r.ev.description)}</div>
      <div class="time num">${esc(time)}</div>
      <div class="num" style="color:var(--muted)">${r.seed ? 'seed ' + esc(r.seed.t) : ''}</div>
      <div style="text-align:right">${pl}${tail}</div>
    </div>`;
  }).join('');
  modal.innerHTML = `<div class="sheet">
    <div class="sheet-head">
      <div><h3 id="sheet-name">${esc(sw.name)}</h3>
        <div class="sub">${esc(teamName[sw.team] || sw.team)} · ${sw.swims.length} swim${sw.swims.length === 1 ? '' : 's'}</div></div>
      <button class="sheet-close" aria-label="Close">×</button>
    </div><div class="sheet-body">${rows}</div></div>`;
  modal.classList.add('open');
  modal.querySelector('.sheet-close').focus();
  const close = () => modal.classList.remove('open');
  modal.querySelector('.sheet-close').onclick = close;
  modal.onclick = (e) => { if (e.target === modal) close(); };
  document.addEventListener('keydown', function esc2(e) {
    if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc2); }
  });
}

const shortName = (n) => n.replace(/^\d{4}\s+GPSA\s+/, '').replace(/\s+Invitational$/, '');
const shortEvent = (e) => `${e.gender === 'F' ? 'Girls' : e.gender === 'M' ? 'Boys' : ''} ${e.ageGroup} ${e.distance} ${e.stroke.slice(0, 4)}`.trim();
const ordinal = (n) => { const s = ['th', 'st', 'nd', 'rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };

boot();
