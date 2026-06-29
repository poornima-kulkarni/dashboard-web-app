/* ===================================================================
   Fulfilment Dashboard — frontend logic
   Fetches /api/filters once, then /api/dashboard on every filter
   change. Renders KPI hexagons, metric strip, charts and tables.
=================================================================== */

const COLORS = {
  teal900:'#0c3b41', teal700:'#0f5e63', teal500:'#159199', teal300:'#5fc6c8',
  blue600:'#2f6fb0', blue400:'#5b9bd5',
  green500:'#3fa66b', green300:'#7dd6a0',
  amber:'#e0a437', purple:'#6f7fd6', ink600:'#4d6066', border:'#e1e7e8'
};

const PALETTE = [COLORS.teal500, COLORS.blue400, COLORS.green500, COLORS.amber, COLORS.purple, COLORS.teal300];

let FILTER_DEFS = {};
let ACTIVE_FILTERS = {};   // key -> Set of selected values
let charts = {};           // chart-id -> Chart.js instance

const FILTER_LABELS = {
  demand_type:'demand_type', location:'location', sbu:'sbu',
  bu_head:'bu_head', account:'account', employment_type:'employment_type'
};

init();

async function init(){
  const res = await fetch('/api/filters');
  FILTER_DEFS = await res.json();
  Object.keys(FILTER_LABELS).forEach(k => ACTIVE_FILTERS[k] = new Set());
  renderFilterPanels();
  bindGlobalEvents();
  await refreshDashboard();
}

function renderFilterPanels(){
  Object.keys(FILTER_LABELS).forEach(key => {
    const container = document.getElementById('opt-' + key);
    if(!container) return;
    container.innerHTML = '';
    (FILTER_DEFS[key] || []).forEach(val => {
      const id = key + '-' + val.replace(/\s+/g,'_');
      const wrap = document.createElement('label');
      wrap.className = 'filter-opt';
      wrap.innerHTML = `<input type="checkbox" id="${id}" value="${val}"> <span>${val}</span>`;
      wrap.querySelector('input').addEventListener('change', (e) => {
        if(e.target.checked) ACTIVE_FILTERS[key].add(val);
        else ACTIVE_FILTERS[key].delete(val);
        wrap.classList.toggle('active', e.target.checked);
        refreshDashboard();
      });
      container.appendChild(wrap);
    });
  });
}

function bindGlobalEvents(){
  document.getElementById('clearFilters').addEventListener('click', () => {
    Object.keys(ACTIVE_FILTERS).forEach(k => ACTIVE_FILTERS[k].clear());
    document.querySelectorAll('.filter-opt input').forEach(cb => cb.checked = false);
    document.querySelectorAll('.filter-opt').forEach(l => l.classList.remove('active'));
    refreshDashboard();
  });

  const toggle = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');
  toggle.addEventListener('click', () => sidebar.classList.toggle('open'));
}

function buildQuery(){
  const params = new URLSearchParams();
  Object.entries(ACTIVE_FILTERS).forEach(([key, set]) => {
    set.forEach(v => params.append(key, v));
  });
  return params.toString();
}

async function refreshDashboard(){
  const qs = buildQuery();
  const res = await fetch('/api/dashboard' + (qs ? '?' + qs : ''));
  const data = await res.json();
  renderAll(data);
}

/* ===================== RENDER ORCHESTRATOR ===================== */

function renderAll(d){
  document.getElementById('refreshTime').textContent = 'Refreshed ' + d.last_refreshed;
  document.getElementById('updatedPill').textContent = 'Data updated ' + d.last_refreshed.split(' ')[0];
  document.getElementById('rowCountPill').textContent =
    `${d.row_counts.open_demands} demands · ${d.row_counts.hr_records} candidates`;

  renderHexStrip(d.kpis);
  renderMetricStrip(d.kpis);
  renderProjection(d.kpis);

  renderWeekOnWeek(d.week_on_week);
  renderTier(d.tier_view);
  renderClientInterview(d.client_interview);
  renderEmpType(d.employment_split);
  renderPracticeTable(d.practice_table);
  renderEmployerTable(d.employer_table);
  renderEmpSplitBars(d.employment_split);
  renderMarginRows(d.margin);
  renderMonthly(d.monthly_view);

  renderCandidateStatus(d.candidate_status);
  renderSourceMix(d.source_mix);
  renderExpBandTable(d.experience_band);
  renderCpcGrid(d.cpc_view);
  renderGauge(d.offer_acceptance);
}

/* ===================== HEX KPI STRIP ===================== */

function renderHexStrip(k){
  const items = [
    {v:k.onboarded, l:'Onboarded', c:'c1'},
    {v:k.avg_onboards_week, l:'Avg onboards / week', c:'c5'},
    {v:k.pipeline, l:'Offer Pipeline', c:'c2'},
    {v:k.avg_pipeline_week, l:'Avg pipeline / week', c:'c6'},
    {v:k.open_jobs, l:'Open Jobs', c:'c4'},
    {v:k.client_interview_pct + '%', l:'Demands w/ 3+ Client Rounds', c:'c3'},
  ];
  const strip = document.getElementById('hexStrip');
  strip.innerHTML = items.map(it => `
    <div class="hex ${it.c}">
      <div class="hex-value">${it.v}</div>
      <div class="hex-label">${it.l}</div>
    </div>`).join('');
}

function renderMetricStrip(k){
  const items = [
    {l:'Lead time to hire (days)', v:k.lead_time_to_hire},
    {l:'Mean time to hire (days)', v:k.mean_time_to_hire},
    {l:'Replacement %', v:k.replacement_pct + '%'},
    {l:'Offer to Joinee ratio', v:k.offer_to_joinee_ratio + '%'},
  ];
  document.getElementById('metricStrip').innerHTML = items.map(it => `
    <div class="metric-box">
      <span class="m-label">${it.l}</span>
      <span class="m-value">${it.v}</span>
    </div>`).join('');
}

function renderProjection(k){
  document.getElementById('projCurrent').textContent = k.projection_current;
  document.getElementById('projAvg').textContent = k.projection_avg;
  document.getElementById('projWeeksLeft').textContent = `(${k.weeks_left} weeks left)`;
}

/* ===================== CHART HELPERS ===================== */

function destroyChart(id){
  if(charts[id]){ charts[id].destroy(); delete charts[id]; }
}

function lineBarChart(id, labels, datasets){
  destroyChart(id);
  const ctx = document.getElementById(id).getContext('2d');
  charts[id] = new Chart(ctx, {
    type:'bar',
    data:{labels, datasets},
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:true, position:'top', labels:{boxWidth:10, font:{size:10}}}},
      scales:{
        x:{grid:{display:false}, ticks:{font:{size:9}}},
        y:{grid:{color:COLORS.border}, ticks:{font:{size:9}}}
      }
    }
  });
}

function donutChart(id, labels, counts, colors){
  destroyChart(id);
  const ctx = document.getElementById(id).getContext('2d');
  charts[id] = new Chart(ctx, {
    type:'doughnut',
    data:{labels, datasets:[{data:counts, backgroundColor:colors || PALETTE, borderWidth:2, borderColor:'#fff'}]},
    options:{
      responsive:true, maintainAspectRatio:false, cutout:'62%',
      plugins:{legend:{position:'bottom', labels:{boxWidth:9, font:{size:9}}}}
    }
  });
}

function simpleBar(id, labels, counts, color){
  destroyChart(id);
  const ctx = document.getElementById(id).getContext('2d');
  charts[id] = new Chart(ctx, {
    type:'bar',
    data:{labels, datasets:[{data:counts, backgroundColor:color || COLORS.teal500, borderRadius:5, maxBarThickness:40}]},
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{x:{grid:{display:false}, ticks:{font:{size:9}}}, y:{grid:{color:COLORS.border}, ticks:{font:{size:9}}}}
    }
  });
}

/* ===================== WIDGETS ===================== */

function renderWeekOnWeek(w){
  lineBarChart('chartWeekOnWeek', w.labels, [
    {label:'Onboards', data:w.onboards, backgroundColor:COLORS.green500, borderRadius:4},
    {label:'Pipeline', data:w.pipeline, backgroundColor:COLORS.blue400, borderRadius:4}
  ]);
}

function renderTier(t){
  simpleBar('chartTier', t.labels, t.counts, COLORS.blue400);
}

function renderClientInterview(c){
  simpleBar('chartClientInt', c.labels, c.counts, COLORS.teal500);
}

function renderEmpType(e){
  simpleBar('chartEmpType', e.labels, e.counts, COLORS.amber);
}

function renderPracticeTable(rows){
  renderDataTable('tablePractice', ['Practice','Count','%'], rows.map(r => [r.name, r.count, r.pct + '%']));
}

function renderEmployerTable(rows){
  renderDataTable('tableEmployer', ['Account','Count','%'], rows.slice(0,8).map(r => [r.name, r.count, r.pct + '%']));
}

function renderDataTable(id, headers, rows){
  const el = document.getElementById(id);
  el.innerHTML = `
    <thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(r => `<tr>${r.map((c,i)=>`<td class="${i>0?'num':''}">${c}</td>`).join('')}</tr>`).join('')}</tbody>`;
}

function renderEmpSplitBars(e){
  const el = document.getElementById('empSplitBars');
  const maxPct = Math.max(...e.pct, 1);
  el.innerHTML = e.labels.map((l,i) => `
    <div class="split-row">
      <span class="label">${l}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${(e.pct[i]/maxPct)*100}%"></div></div>
      <span class="pctval">${e.pct[i]}%</span>
    </div>`).join('');
}

function renderMarginRows(m){
  const el = document.getElementById('marginRows');
  el.innerHTML = m.labels.map((l,i) => `
    <div class="margin-row">
      <span class="mr-label">${l}</span>
      <span class="mr-value">${m.values[i]}%</span>
    </div>`).join('');
}

function renderMonthly(m){
  simpleBar('chartMonthly', m.labels, m.counts, COLORS.teal700 || COLORS.teal500);
}

function renderCandidateStatus(c){
  donutChart('chartCandidateStatus', c.labels, c.counts, [COLORS.green500, COLORS.blue400, '#d9534f']);
}

function renderSourceMix(s){
  donutChart('chartSourceMix', s.labels, s.counts);
}

function renderExpBandTable(rows){
  const el = document.getElementById('tableExpBand');
  el.innerHTML = rows.map(r => `<tr><td>${r.band}</td><td>${r.count}</td><td>${r.pct}%</td></tr>`).join('');
}

function renderCpcGrid(c){
  const el = document.getElementById('cpcGrid');
  el.innerHTML = `
    <div class="cpc-box">
      <div class="cpc-title">Permanent</div>
      <div class="cpc-row"><span>Offshore</span><b>₹${c.permanent.offshore}L</b></div>
      <div class="cpc-row"><span>Onsite</span><b>₹${c.permanent.onsite}L</b></div>
    </div>
    <div class="cpc-box">
      <div class="cpc-title">Contractor</div>
      <div class="cpc-row"><span>Offshore</span><b>₹${c.contractor.offshore}L</b></div>
      <div class="cpc-row"><span>Onsite</span><b>₹${c.contractor.onsite}L</b></div>
    </div>`;
}

function renderGauge(o){
  destroyChart('chartGauge');
  const ctx = document.getElementById('chartGauge').getContext('2d');
  charts['chartGauge'] = new Chart(ctx, {
    type:'doughnut',
    data:{
      datasets:[{
        data:[o.accepted_pct, 100 - o.accepted_pct],
        backgroundColor:[COLORS.green500, COLORS.border],
        borderWidth:0
      }]
    },
    options:{
      responsive:false,
      circumference:180, rotation:270, cutout:'70%',
      plugins:{legend:{display:false}, tooltip:{enabled:false}}
    }
  });
  document.getElementById('gaugeValue').textContent = o.accepted_pct + '%';
}
