/* Local-only synthetic monitoring; no medical inference or external assets. */
let currentData;
let busy = false;
let view = 'overview';
let paused = false;
const offline = globalThis.AstroOffline || null;
const drafts = new Map();
const metrics = [
  ['heart_rate', 'Heart rate', 'BPM', '#67e8d3'],
  ['spo2', 'Oxygen saturation', '%', '#afa5ff'],
  ['temperature', 'Body temperature', '°C', '#ffbf8b'],
  ['sleep_hours', 'Sleep duration', 'hours', '#80b6ff']
];
const el = id => document.getElementById(id);
const svgNS = 'http://www.w3.org/2000/svg';
const numeric = value => Number(value).toFixed(1).replace(/\.0$/, '');
const signed = value => (value > 0 ? '+' : '') + numeric(value);
function svgNode(tag, attributes, text) {
  const node = document.createElementNS(svgNS, tag);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
  if (text !== undefined) node.textContent = text;
  return node;
}
function sampleTime(value) {
  return value ? new Date(value).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'}) : '—';
}
function chart(data) {
  el('trend').replaceChildren();
  (view === 'vitals' ? metrics : metrics.slice(0, 2)).forEach(([key, label, unit, color]) => {
    const values = data.history.map(row => row[key]);
    const baseline = data.baseline[key].value;
    const padding = key === 'temperature' ? 0.2 : key === 'sleep_hours' ? 0.4 : 2;
    const min = Math.min(...values, baseline) - padding;
    const max = Math.max(...values, baseline) + padding;
    const y = value => 88 - (value - min) * 64 / (max - min);
    const section = document.createElement('div');
    const caption = document.createElement('p');
    const name = document.createElement('span');
    name.textContent = `${label} (${unit})`;
    name.style.color = color;
    const latest = document.createElement('strong');
    latest.textContent = numeric(values.at(-1));
    caption.append(name, latest);
    const svg = svgNode('svg', {viewBox: '0 0 680 120', role: 'img',
      'aria-label': `${label}: samples ${data.history[0].step} to ${data.history.at(-1).step}; latest ${values.at(-1)} ${unit}; personal baseline ${baseline} ${unit}`});
    [min, (min + max) / 2, max].forEach(value => {
      svg.append(svgNode('line', {x1: 44, x2: 650, y1: y(value), y2: y(value), stroke: '#23384b', 'stroke-width': 0.7}));
      svg.append(svgNode('text', {x: 0, y: y(value) + 4, fill: '#9aacc0', 'font-size': 10}, numeric(value)));
    });
    svg.append(svgNode('line', {x1: 44, x2: 650, y1: y(baseline), y2: y(baseline), stroke: '#9caebe', 'stroke-dasharray': '5 5', 'stroke-width': 1}));
    svg.append(svgNode('polyline', {points: values.map((v, i) => `${44 + i * 606 / Math.max(1, values.length - 1)},${y(v)}`).join(' '), fill: 'none', stroke: color, 'stroke-width': 2}));
    svg.append(svgNode('circle', {cx: 650, cy: y(values.at(-1)), r: 3, fill: color}));
    [[44, data.history[0]], [540, data.history.at(-1)]].forEach(([x, row]) => {
      svg.append(svgNode('text', {x, y: 112, fill: '#9aacc0', 'font-size': 10}, sampleTime(row.recorded_at)));
    });
    section.append(caption, svg);
    el('trend').append(section);
  });
}
function details(data) {
  const section = el('details');
  section.hidden = !['vitals', 'analytics'].includes(view);
  el('profilePanel').hidden = view !== 'profiles';
  ['assessmentPanel', 'timelinePanel', 'communicationPanel', 'insightsPanel', 'demoPanel'].forEach(id => {
    el(id).hidden = view !== {assessmentPanel: 'assessment', timelinePanel: 'timeline', communicationPanel: 'communications', insightsPanel: 'insights', demoPanel: 'demo'}[id];
  });
  section.replaceChildren();
  if (section.hidden) return;
  const heading = document.createElement('h3');
  heading.textContent = view === 'analytics' ? 'Crew Analytics · Last 48 simulated samples' : 'Vital Signs · Simulated sample history';
  const table = document.createElement('table');
  const head = table.createTHead().insertRow();
  const labels = view === 'analytics' ? ['Measurement', 'Minimum', 'Average', 'Maximum', 'Personal baseline'] : ['Sample', 'Recorded (local)', ...metrics.map(m => `${m[1]} (${m[2]})`)];
  labels.forEach(label => {
    const th = document.createElement('th');
    th.scope = 'col'; th.textContent = label; head.append(th);
  });
  const rows = view === 'analytics' ? metrics.map(([key, label, unit]) => {
    const values = data.history.map(row => row[key]);
    return [`${label} (${unit})`, numeric(Math.min(...values)), numeric(values.reduce((a, b) => a + b, 0) / values.length), numeric(Math.max(...values)), `${numeric(data.baseline[key].value)} ± ${numeric(data.baseline[key].tolerance)}`];
  }) : [...data.history].reverse().map(row => [row.step, sampleTime(row.recorded_at), ...metrics.map(([key]) => numeric(row[key]))]);
  const body = table.createTBody();
  rows.forEach(values => {
    const row = body.insertRow();
    values.forEach(value => { row.insertCell().textContent = value; });
  });
  section.append(heading, table);
}
function renderInsights(data) {
  const list = el('insightList');
  list.replaceChildren();
  if (data.decision_support) {
    const summary = document.createElement('article'); summary.className = 'insight-card decision-support';
    const heading = document.createElement('h4');
    heading.textContent = data.decision_support.review_flag ? 'Combined evidence · REVIEW SUGGESTED' : 'Combined evidence · NO REVIEW FLAG';
    const observations = document.createElement('p'); observations.textContent = data.decision_support.observations.join(' ');
    const method = document.createElement('span'); method.className = 'tag'; method.textContent = 'EXPERIMENTAL / SELF-REPORT + SYNTHETIC SIGNALS';
    summary.append(heading, observations, method); list.append(summary);
  }
  data.insights.forEach(insight => {
    const card = document.createElement('article'); card.className = 'insight-card';
    const heading = document.createElement('h4'); heading.textContent = `${insight.label} · ${insight.direction.toUpperCase()}`;
    const explanation = document.createElement('p'); explanation.textContent = insight.explanation;
    const tag = document.createElement('span'); tag.className = 'tag'; tag.textContent = `Δ baseline ${signed(insight.deviation)} ${insight.unit}`;
    card.append(heading, explanation, tag); list.append(card);
  });
}
function renderAlerts(data) {
  const alerts = el('alerts');
  alerts.replaceChildren();
  el('alertCount').textContent = `${data.anomalies.length} ${data.anomalies.length === 1 ? 'flag' : 'flags'}`;
  if (!data.anomalies.length) {
    const clear = document.createElement('div'); clear.className = 'clear-state';
    const title = document.createElement('strong'); title.textContent = '✓ No experimental flags';
    const description = document.createElement('span'); description.textContent = 'Current synthetic values are within the configured demo limits and personal deviations. This is not a medical assessment.';
    clear.append(title, description); alerts.append(clear); return;
  }
  data.anomalies.forEach(anomaly => {
    const card = document.createElement('article'); card.className = 'anomaly';
    const title = document.createElement('h4');
    title.textContent = `${anomaly.label} · ${numeric(anomaly.value)} ${anomaly.unit}${anomaly.recorded_at ? ' · ' + sampleTime(anomaly.recorded_at) : ''}`;
    const explanation = document.createElement('p'); explanation.textContent = anomaly.explanation;
    const rule = document.createElement('div'); rule.className = 'rule-tags';
    rule.textContent = 'EXPERIMENTAL / ' + anomaly.rules.map(r => r === 'personal_baseline' ? 'PERSONAL DEVIATION' : 'DEMO LIMIT').join(' + ');
    card.append(title, explanation, rule); alerts.append(card);
  });
}
function fillBaseline() {
  if (!currentData) return;
  const source = drafts.get(currentData.profile.id) || currentData.baseline;
  metrics.forEach(([key]) => ['value', 'tolerance'].forEach(field => { el(`${key}-${field}`).value = source[key][field]; }));
  el('baselineFeedback').textContent = drafts.has(currentData.profile.id) ? 'Unsaved edits for this crew member.' : '';
}
function connectionLabel() {
  el('connection').textContent = paused ? 'Ⅱ SIMULATION PAUSED' : '● SIMULATION ACTIVE';
}
function render(data) {
  const profileChanged = currentData?.profile.id !== data.profile.id;
  currentData = data;
  offline?.cacheHealth(data.profile.id, data);
  ['hr', 'spo2', 'temp', 'sleep'].forEach((id, i) => { el(id).textContent = numeric(data.latest[metrics[i][0]]); });
  metrics.forEach(([key]) => {
    const baseline = data.baseline[key];
    const reference = el('baseline-' + key);
    reference.textContent = `Baseline ${numeric(baseline.value)} ± ${numeric(baseline.tolerance)} · Δ ${signed(data.latest[key] - baseline.value)}`;
    reference.closest('.metric').classList.toggle('flagged', data.anomalies.some(a => a.metric === key));
  });
  el('profileSelect').value = data.profile.id;
  el('crewIdentity').textContent = `Mission ${data.mission} · ${data.astronaut} · ${data.profile.role} · Fictional crew`;
  el('profileDescription').textContent = `${data.profile.callsign} / ${data.astronaut} / ${data.profile.role} / ${data.mission}. Separate synthetic history and personal reference values.`;
  el('status').textContent = data.status === 'REVIEW' ? 'EXPERIMENTAL REVIEW FLAG' : 'WITHIN DEMO RANGES';
  el('status').style.color = data.anomalies.length ? '#ffbf8b' : '#67e8d3';
  el('updated').textContent = `Sample ${data.latest.step} recorded ${sampleTime(data.latest.recorded_at)} · Last checked ${sampleTime(data.updated_at)}`;
  el('scenarioLabel').textContent = `Active: ${{normal: 'Normal', elevated: 'Elevated HR', low_oxygen: 'Low oxygen'}[data.scenario]}. This scenario stays active until changed.`;
  document.querySelectorAll('[data-scenario]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.scenario === data.scenario)));
  el('reportCsv').href = `/api/report?profile=${encodeURIComponent(data.profile.id)}&format=csv`;
  el('reportJson').href = `/api/report?profile=${encodeURIComponent(data.profile.id)}&format=json`;
  connectionLabel(); renderAlerts(data); chart(data); details(data); renderInsights(data);
  if (profileChanged || !drafts.has(data.profile.id)) fillBaseline();
}
async function refresh(scenario, action = 'health', payload, profileId = currentData?.profile.id || el('profileSelect').value || 'crew-01') {
  if (busy) return false;
  busy = true;
  const buttons = document.querySelectorAll('[data-scenario], #refresh, #profileSelect, #saveBaseline, #resetBaseline');
  buttons.forEach(button => { button.disabled = true; });
  const inputs = document.querySelectorAll('#baselineForm input');
  if (action === 'baseline') inputs.forEach(input => { input.disabled = true; });
  el('requestError').hidden = true;
  const query = '?profile=' + encodeURIComponent(profileId);
  let url = '/api/health' + query;
  const options = {method: 'GET', cache: 'no-store', signal: AbortSignal.timeout(10000)};
  if (scenario) { url = '/api/scenario/' + scenario + query; options.method = 'POST'; }
  else if (action === 'tick') { url = '/api/simulation/tick' + query; options.method = 'POST'; }
  else if (action === 'baseline') {
    url = `/api/profiles/${encodeURIComponent(profileId)}/baseline`;
    options.method = 'PUT'; options.headers = {'Content-Type': 'application/json'}; options.body = JSON.stringify(payload);
  }
  try {
    const response = await fetch(url, options);
    if (!response.ok) {
      let message = 'Server returned ' + response.status;
      try { message += ': ' + (await response.json()).error; } catch (_) { /* Retain HTTP status when no JSON is available. */ }
      throw Error(message);
    }
    const data = await response.json();
    if (action === 'baseline') drafts.delete(profileId);
    render(data);
    if (action === 'baseline') el('baselineFeedback').textContent = 'Baseline saved. Experimental flags recalculated.';
    return true;
  } catch (error) {
    const cached = !currentData ? offline?.health(profileId) : null;
    if (cached) {
      render(cached);
      el('connection').textContent = '● OFFLINE SNAPSHOT';
    } else el('connection').textContent = '● CONNECTION ERROR';
    if (!currentData) el('status').textContent = 'TELEMETRY UNAVAILABLE';
    else el('profileSelect').value = currentData.profile.id;
    el('requestError').textContent = `${action === 'baseline' ? 'Baseline was not saved.' : scenario ? 'Scenario could not be confirmed.' : 'Telemetry could not be refreshed.'} ${currentData ? 'Showing last received data. ' : ''}Use Refresh to retry. (${error.message})`;
    el('requestError').hidden = false;
    return false;
  } finally {
    busy = false;
    buttons.forEach(button => { button.disabled = false; });
    if (action === 'baseline') inputs.forEach(input => { input.disabled = false; });
  }
}
function recordCard(titleText, summaryText, metaText, className = '') {
  const card = document.createElement('article'); card.className = 'record-card ' + className;
  const title = document.createElement('h4'); title.textContent = titleText;
  const summary = document.createElement('p'); summary.textContent = summaryText;
  const meta = document.createElement('span'); meta.textContent = metaText;
  card.append(title, summary, meta); return card;
}
async function resource(endpoint, cacheName) {
  const profileId = currentData?.profile.id || el('profileSelect').value;
  try {
    const response = await fetch(endpoint + '?profile=' + encodeURIComponent(profileId), {cache: 'no-store'});
    if (!response.ok) throw Error('Server returned ' + response.status);
    const data = await response.json(); offline?.cacheResource(cacheName, profileId, data); return {data, cached: false};
  } catch (error) {
    const cached = offline?.resource(cacheName, profileId);
    if (cached) return {data: cached, cached: true};
    throw error;
  }
}
async function loadAssessments() {
  const list = el('assessmentHistory'); list.textContent = 'Loading assessment history…';
  try {
    const {data, cached} = await resource('/api/assessments', 'assessments'); list.replaceChildren();
    if (!data.assessments.length) list.textContent = 'No daily self-assessments saved for this fictional astronaut.';
    data.assessments.forEach(item => list.append(recordCard(
      `Daily check-in · ${item.assessment_date}`,
      `Fatigue ${item.fatigue}/5 · Stress ${item.stress}/5 · Sleep quality ${item.sleep_quality}/5`,
      `${item.symptoms.length ? item.symptoms.join(', ') : 'No symptoms reported'}${item.recent_activity ? ' · Activity: ' + item.recent_activity : ''}${cached ? ' · cached offline' : ''}`
    )));
  } catch (error) { list.textContent = 'Assessment history requires the local Flask server or a previous cached response.'; }
}
async function loadTimeline() {
  const list = el('timelineList'); list.textContent = 'Loading mission timeline…';
  try {
    const {data, cached} = await resource('/api/timeline', 'timeline'); list.replaceChildren();
    if (!data.events.length) list.textContent = 'No self-assessments or current-window telemetry flags.';
    data.events.forEach(item => list.append(recordCard(item.title, item.summary,
      `${sampleTime(item.recorded_at)}${cached ? ' · cached offline' : ''}`, item.type)));
  } catch (error) { list.textContent = 'Timeline requires the local Flask server or a previous cached response.'; }
}
async function loadCommunications() {
  const list = el('communicationList'); list.textContent = 'Loading outgoing reports…';
  try {
    const {data, cached} = await resource('/api/communications', 'communications'); list.replaceChildren();
    if (!data.reports.length) list.textContent = 'No outgoing reports for this fictional astronaut.';
    data.reports.forEach(item => list.append(recordCard(item.subject,
      `${item.report_kind.replaceAll('_', ' ')} · ${item.delay_seconds}s simulated delay`,
      `${item.status.toUpperCase()} · queued ${sampleTime(item.created_at)}${item.delivered_at ? ' · delivered ' + sampleTime(item.delivered_at) : ''}${cached ? ' · cached offline' : ''}`,
      item.status)));
  } catch (error) { list.textContent = 'Communication status requires the local Flask server or a previous cached response.'; }
}
async function loadPhaseData(targetView = view) {
  if (targetView === 'assessment') await loadAssessments();
  if (targetView === 'timeline') await loadTimeline();
  if (targetView === 'communications') await loadCommunications();
}
document.querySelectorAll('[data-scenario]').forEach(button => button.addEventListener('click', () => refresh(button.dataset.scenario)));
async function activateView(button) {
  view = button.dataset.view;
  document.body.dataset.view = view;
  document.querySelectorAll('[data-view]').forEach(nav => {
    nav.classList.toggle('active', nav === button);
    if (nav === button) nav.setAttribute('aria-current', 'page'); else nav.removeAttribute('aria-current');
  });
  el('viewTitle').textContent = {overview: 'Astronaut Health Overview', vitals: 'Vital Signs', analytics: 'Crew Analytics', profiles: 'Crew & Personal Baselines', assessment: 'Daily Self-Assessment', timeline: 'Mission Health Timeline', communications: 'Earth Communication Queue', insights: 'Explainable Health Insights', demo: 'Guided Decision-Support Demo'}[view];
  if (currentData) { chart(currentData); details(currentData); }
  await loadPhaseData(view);
}
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => activateView(button)));
function openView(name) {
  const button = [...document.querySelectorAll('[data-view]')].find(item => item.dataset.view === name);
  if (button) return activateView(button);
}
el('profileSelect').addEventListener('change', async () => {
  const changed = await refresh(null, 'health', null, el('profileSelect').value);
  if (changed) await loadPhaseData(view);
});
el('refresh').addEventListener('click', () => refresh());
el('pause').addEventListener('click', () => {
  paused = !paused;
  el('pause').textContent = paused ? 'Resume simulation' : 'Pause simulation';
  el('pause').setAttribute('aria-pressed', String(paused));
  if (el('requestError').hidden) connectionLabel();
});
el('baselineForm').addEventListener('input', () => {
  if (!currentData) return;
  const draft = Object.fromEntries(metrics.map(([key]) => [key, {value: el(key + '-value').value, tolerance: el(key + '-tolerance').value}]));
  drafts.set(currentData.profile.id, draft);
  el('baselineFeedback').textContent = 'Unsaved edits for this crew member.';
});
el('baselineForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (!currentData || !el('baselineForm').reportValidity() || busy) return;
  const payload = Object.fromEntries(metrics.map(([key]) => [key, {value: Number(el(key + '-value').value), tolerance: Number(el(key + '-tolerance').value)}]));
  await refresh(null, 'baseline', payload);
});
el('resetBaseline').addEventListener('click', () => { if (currentData) { drafts.delete(currentData.profile.id); fillBaseline(); } });
el('assessmentDate').value = new Date().toISOString().slice(0, 10);
el('assessmentForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (!currentData || !el('assessmentForm').reportValidity()) return;
  const symptoms = [...document.querySelectorAll('input[name="symptom"]:checked')].map(input => input.value);
  const payload = {assessment_date: el('assessmentDate').value, fatigue: Number(el('fatigue').value),
    stress: Number(el('stress').value), sleep_quality: Number(el('sleepQuality').value),
    symptoms, recent_activity: el('recentActivity').value, notes: el('assessmentNotes').value};
  try {
    const result = await offline.sendOrQueue('assessment', currentData.profile.id,
      '/api/assessments?profile=' + encodeURIComponent(currentData.profile.id), payload);
    el('assessmentFeedback').textContent = result.queuedOffline ? 'Saved in this browser; waiting to synchronize.' : 'Daily assessment saved to SQLite.';
    if (!result.queuedOffline) { await loadAssessments(); await refresh(); }
  } catch (error) { el('assessmentFeedback').textContent = error.message; }
});
el('communicationForm').addEventListener('submit', async event => {
  event.preventDefault(); if (!currentData || !el('communicationForm').reportValidity()) return;
  const payload = {subject: el('communicationSubject').value, report_kind: 'health_snapshot',
    delay_seconds: Number(el('communicationDelay').value)};
  try {
    const result = await offline.sendOrQueue('communication', currentData.profile.id,
      '/api/communications?profile=' + encodeURIComponent(currentData.profile.id), payload);
    el('communicationFeedback').textContent = result.queuedOffline ? 'Stored in browser sync queue. Delivery delay starts after Flask receives it.' : 'Report accepted into the simulated Earth queue.';
    if (!result.queuedOffline) await loadCommunications();
  } catch (error) { el('communicationFeedback').textContent = error.message; }
});
el('refreshTimeline').addEventListener('click', loadTimeline);
async function synchronizeCommunication() {
  const result = await offline.sync();
  if (result.pending) {
    el('communicationFeedback').textContent = `Browser sync sent ${result.sent}; ${result.pending} still pending.`;
    return {delivered_count: 0, pending: result.pending};
  }
  const profileId = currentData?.profile.id || el('profileSelect').value;
  try {
    const response = await fetch('/api/communications/sync?profile=' + encodeURIComponent(profileId), {method: 'POST'});
    if (!response.ok) throw Error('Server returned ' + response.status);
    const data = await response.json();
    offline?.cacheResource('communications', profileId, {profile_id: profileId, reports: data.reports, delivery_requires_sync: true});
    el('communicationFeedback').textContent = `Browser sync sent ${result.sent}. Earth-link sync delivered ${data.delivered_count} eligible report(s).`;
    await loadPhaseData(view);
    return {...data, pending: 0};
  } catch (error) {
    el('communicationFeedback').textContent = `Earth-link synchronization failed safely; reports remain queued. (${error.message})`;
    return {delivered_count: 0, pending: 0, error};
  }
}
el('syncNow').addEventListener('click', synchronizeCommunication);
el('demoStart').addEventListener('click', async () => {
  const completed = await refresh('elevated');
  el('demoStatus').textContent = completed ? 'Step 1 complete: synthetic elevated heart rate injected. Continue to review the experimental flag.' : 'Step 1 could not be completed; check the local server connection.';
});
el('demoReview').addEventListener('click', () => openView('overview'));
el('demoAssessment').addEventListener('click', () => openView('assessment'));
el('demoReport').addEventListener('click', () => {
  el('communicationSubject').value = 'Guided demo elevated-HR review';
  el('communicationDelay').value = '5';
  openView('communications');
});
el('demoSync').addEventListener('click', async () => {
  const result = await synchronizeCommunication();
  el('demoStatus').textContent = result.error ? 'Synchronization failed safely; queued reports were retained.' :
    result.delivered_count ? `Demo complete: ${result.delivered_count} eligible report(s) delivered during simulated synchronization.` :
    'Synchronization completed. No report was eligible yet; wait for its simulated delay and synchronize again.';
});
offline?.onStatus(status => {
  el('syncBadge').textContent = status.pending ? `${status.pending} OFFLINE PENDING` : status.online ? 'SYNC READY' : 'OFFLINE';
});
el('syncBadge').textContent = offline?.pendingCount() ? `${offline.pendingCount()} OFFLINE PENDING` : 'SYNC READY';
refresh();
setInterval(() => { if (!document.hidden && !paused) refresh(null, 'tick'); }, 5000);
setInterval(() => { if (view === 'communications') loadCommunications(); }, 5000);
