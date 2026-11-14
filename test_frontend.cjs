const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor() {
    this.children = []; this.style = {}; this.dataset = {}; this.attrs = {}; this.events = {};
    this.value = ''; this.hidden = false; this.disabled = false;
    this.classList = {toggle() {}};
  }
  append(...items) { this.children.push(...items); }
  replaceChildren() { this.children = []; }
  setAttribute(k, v) { this.attrs[k] = v; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(k, v) { this.events[k] = v; }
  createTHead() { const e = new Element(); this.append(e); return e; }
  createTBody() { return this.createTHead(); }
  insertRow() { return this.createTHead(); }
  insertCell() { return this.createTHead(); }
  closest() { return new Element(); }
  reportValidity() { return true; }
}
const keys = ['heart_rate', 'spo2', 'temperature', 'sleep_hours'];
function fixture(profileId = 'crew-01') {
  const latest = {step: 48, recorded_at: '2026-11-04T12:00:00+00:00', heart_rate: 75, spo2: 98, temperature: 36.7, sleep_hours: 7};
  return {latest, history: Array.from({length: 48}, (_, i) => ({...latest, step: i + 1})),
    alerts: [], anomalies: [], status: 'WITHIN DEMO RANGES', scenario: 'normal', updated_at: latest.recorded_at,
    profile: {id: profileId, callsign: 'ORION', name: 'Crew Member 01', role: 'Commander'}, mission: 'DEMO-01', astronaut: 'Crew Member 01',
    baseline: Object.fromEntries(keys.map((key, i) => [key, {value: [72, 97, 36.7, 7.2][i], tolerance: [15, 3, 0.6, 1.5][i]}])),
    decision_support: {review_flag: false, observations: ['No experimental flags.', 'No self-assessment available.']},
    insights: keys.map((key, i) => ({metric: key, label: key, unit: ['BPM','%','°C','hours'][i], direction: 'stable', deviation: 0, explanation: 'Experimental stable demo trend.'}))};
}
function setup() {
  const names = ['hr','spo2','temp','sleep','status','updated','alertCount','alerts','connection','trend','details','requestError','refresh','viewTitle','profileSelect','pause','reportCsv','reportJson','profilePanel','profileDescription','crewIdentity','scenarioLabel','baselineForm','baselineFeedback','saveBaseline','resetBaseline','assessmentPanel','timelinePanel','communicationPanel','insightsPanel','demoPanel','insightList','assessmentHistory','timelineList','communicationList','assessmentDate','assessmentForm','fatigue','stress','sleepQuality','recentActivity','assessmentNotes','assessmentFeedback','communicationForm','communicationSubject','communicationDelay','communicationFeedback','refreshTimeline','syncNow','syncBadge','demoStart','demoReview','demoAssessment','demoReport','demoSync','demoStatus', ...keys.flatMap(key => [`baseline-${key}`, `${key}-value`, `${key}-tolerance`])];
  const ids = Object.fromEntries(names.map(id => [id, new Element()])); ids.profileSelect.value = 'crew-01';
  const nav = ['overview','vitals','analytics','profiles','assessment','timeline','communications','insights','demo'].map(view => {const e = new Element(); e.dataset.view = view; return e;});
  const buttons = ['normal','elevated','low_oxygen'].map(scenario => {const e = new Element(); e.dataset.scenario = scenario; return e;});
  const inputs = keys.flatMap(key => [ids[key + '-value'], ids[key + '-tolerance']]);
  const calls = [], timers = [];
  const data = fixture();
  const doc = {hidden: false, body: {dataset: {}}, getElementById: id => ids[id], createElement: () => new Element(), createElementNS: () => new Element(),
    querySelectorAll: s => s === '[data-view]' ? nav : s === '[data-scenario]' ? buttons : s === '#baselineForm input' ? inputs : s.includes('symptom') ? [] : [...buttons, ids.refresh, ids.profileSelect, ids.saveBaseline, ids.resetBaseline]};
  const offline = {cacheHealth() {}, cacheResource() {}, resource() {return null;}, health() {return null;}, pendingCount() {return 0;}, onStatus() {}, sync: async () => ({sent: 0, pending: 0}), sendOrQueue: async () => ({queuedOffline: false, data: {}})};
  const context = vm.createContext({document: doc, AstroOffline: offline, fetch: async (...args) => {calls.push(args); return {ok: true, json: async () => structuredClone(data)};}, AbortSignal, setInterval: (callback, ms) => timers.push({callback, ms})});
  vm.runInContext(fs.readFileSync('static/app.js', 'utf8'), context);
  return {ids, nav, buttons, data, calls, context, timers, doc, offline};
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('initial load, offline charts, navigation and scenario POST', async () => {
  const s = setup(); await settle(); assert.equal(s.ids.hr.textContent, '75'); assert.equal(s.ids.trend.children.length, 2);
  s.nav[1].events.click(); assert.equal(s.ids.details.hidden, false); assert.equal(s.ids.trend.children.length, 4);
  assert.equal(s.ids.details.children[1].children[1].children.length, 48);
  s.nav[2].events.click(); assert.equal(s.ids.details.children[1].children[1].children.length, 4);
  s.nav[3].events.click(); assert.equal(s.ids.profilePanel.hidden, false); assert.equal(s.ids.details.hidden, true);
  s.nav[0].events.click(); assert.equal(s.ids.profilePanel.hidden, true);
  s.buttons[1].events.click(); await settle(); assert.equal(s.calls.at(-1)[0], '/api/scenario/elevated?profile=crew-01'); assert.equal(s.calls.at(-1)[1].method, 'POST'); assert.equal(s.buttons[1].disabled, false);
});
test('connection failure retains data and refresh recovers', async () => {
  const s = setup(); await settle(); const good = s.context.fetch;
  s.context.fetch = async () => {throw Error('offline');};
  await s.ids.refresh.events.click(); assert.equal(s.ids.hr.textContent, '75'); assert.equal(s.ids.requestError.hidden, false);
  assert.match(s.ids.requestError.textContent, /last received/); assert.equal(s.ids.refresh.disabled, false);
  s.context.fetch = good; await s.ids.refresh.events.click(); assert.equal(s.ids.requestError.hidden, true); assert.match(s.ids.connection.textContent, /ACTIVE/);
});
test('initial failure and server error are actionable', async () => {
  const s = setup(); await settle(); vm.runInContext('currentData=undefined', s.context);
  s.context.fetch = async () => ({ok: false, status: 500}); await s.ids.refresh.events.click();
  assert.equal(s.ids.status.textContent, 'TELEMETRY UNAVAILABLE'); assert.match(s.ids.requestError.textContent, /500/);
});
test('5-second simulation timer pauses and skips hidden tabs', async () => {
  const s = setup(); await settle(); assert.equal(s.timers[0].ms, 5000);
  s.timers[0].callback(); await settle(); assert.equal(s.calls.at(-1)[0], '/api/simulation/tick?profile=crew-01');
  const count = s.calls.length; s.ids.pause.events.click(); s.timers[0].callback(); await settle(); assert.equal(s.calls.length, count);
  assert.match(s.ids.connection.textContent, /PAUSED/);
  s.ids.pause.events.click(); s.doc.hidden = true; s.timers[0].callback(); await settle(); assert.equal(s.calls.length, count);
  s.doc.hidden = false; s.timers[0].callback(); await settle(); assert.equal(s.calls.length, count + 1);
});
test('profile changes update report links; failed switch reverts selector', async () => {
  const s = setup(); await settle(); s.data.profile.id = 'crew-02'; s.ids.profileSelect.value = 'crew-02';
  await s.ids.profileSelect.events.change(); assert.equal(s.calls.at(-1)[0], '/api/health?profile=crew-02');
  assert.match(s.ids.reportCsv.href, /profile=crew-02&format=csv/); assert.match(s.ids.reportJson.href, /profile=crew-02&format=json/);
  s.context.fetch = async () => {throw Error('offline');}; s.ids.profileSelect.value = 'crew-03';
  await s.ids.profileSelect.events.change(); assert.equal(s.ids.profileSelect.value, 'crew-02');
  assert.match(s.ids.reportCsv.href, /crew-02/);
});
test('unsaved baseline survives polling, saves via PUT and can be discarded', async () => {
  const s = setup(); await settle(); s.ids['heart_rate-value'].value = '81'; s.ids.baselineForm.events.input();
  s.timers[0].callback(); await settle(); assert.equal(s.ids['heart_rate-value'].value, '81');
  s.data.baseline.heart_rate.value = 81;
  await s.ids.baselineForm.events.submit({preventDefault() {}});
  assert.equal(s.calls.at(-1)[0], '/api/profiles/crew-01/baseline'); assert.equal(s.calls.at(-1)[1].method, 'PUT');
  assert.equal(JSON.parse(s.calls.at(-1)[1].body).heart_rate.value, 81); assert.match(s.ids.baselineFeedback.textContent, /saved/);
  s.ids['heart_rate-value'].value = '85'; s.ids.baselineForm.events.input(); s.ids.resetBaseline.events.click();
  assert.equal(s.ids['heart_rate-value'].value, 81);
});
test('failed baseline save preserves edits and shows validation message', async () => {
  const s = setup(); await settle(); s.ids['heart_rate-value'].value = '81'; s.ids.baselineForm.events.input();
  s.context.fetch = async () => ({ok: false, status: 400, json: async () => ({error: 'Invalid tolerance'})});
  await s.ids.baselineForm.events.submit({preventDefault() {}});
  assert.equal(s.ids['heart_rate-value'].value, '81'); assert.match(s.ids.requestError.textContent, /Invalid tolerance/);
  assert.match(s.ids.requestError.textContent, /not saved/); assert.equal(s.ids.saveBaseline.disabled, false);
});
test('experimental explanations rendered safely as text', async () => {
  const s = setup(); await settle();
  s.data.anomalies = [{label: 'Heart rate', value: 125, unit: 'BPM', recorded_at: '2026-11-04T12:00:00+00:00', rules: ['personal_baseline'], explanation: '<script>example</script>'}];
  s.data.status = 'REVIEW';
  await s.ids.refresh.events.click(); assert.equal(s.ids.alertCount.textContent, '1 flag');
  assert.equal(s.ids.alerts.children[0].children[1].textContent, '<script>example</script>');
  assert.match(s.ids.alerts.children[0].children[0].textContent, /BPM · .+/);
  assert.match(s.ids.status.textContent, /EXPERIMENTAL REVIEW/);
});
test('overlapping timer requests are suppressed', async () => {
  const s = setup(); await settle(); let release;
  s.context.fetch = () => new Promise(resolve => {release = resolve;});
  s.timers[0].callback(); s.timers[0].callback(); assert.equal(s.ids.refresh.disabled, true);
  release({ok: true, json: async () => s.data}); await settle(); assert.equal(s.ids.refresh.disabled, false);
});
test('Phase 3 views render assessments, timeline and communication records', async () => {
  const s = setup(); await settle();
  s.context.fetch = async url => {
    if (url.startsWith('/api/assessments')) return {ok: true, json: async () => ({assessments: [{assessment_date: '2026-11-04', fatigue: 2, stress: 3, sleep_quality: 4, symptoms: ['Headache']} ]})};
    if (url.startsWith('/api/timeline')) return {ok: true, json: async () => ({events: [{type: 'self_assessment', title: 'Daily check-in', summary: 'Fatigue 2/5', recorded_at: s.data.updated_at}]})};
    return {ok: true, json: async () => ({reports: [{subject: 'Daily report', report_kind: 'health_snapshot', delay_seconds: 30, status: 'queued', created_at: s.data.updated_at, delivered_at: null}]})};
  };
  await s.nav[4].events.click(); assert.equal(s.ids.assessmentPanel.hidden, false); assert.equal(s.ids.assessmentHistory.children.length, 1);
  await s.nav[5].events.click(); assert.equal(s.ids.timelinePanel.hidden, false); assert.equal(s.ids.timelineList.children.length, 1);
  await s.nav[6].events.click(); assert.equal(s.ids.communicationPanel.hidden, false); assert.equal(s.ids.communicationList.children.length, 1);
  await s.nav[7].events.click(); assert.equal(s.ids.insightsPanel.hidden, false); assert.equal(s.ids.insightList.children.length, 5);
  await s.nav[8].events.click(); assert.equal(s.ids.demoPanel.hidden, false);
});
test('Phase 3 mutations use the offline synchronization adapter', async () => {
  const s = setup(); await settle(); const sent = [];
  s.offline.sendOrQueue = async (...args) => { sent.push(args); return {queuedOffline: true}; };
  s.ids.assessmentDate.value = '2026-11-04'; s.ids.fatigue.value = '2'; s.ids.stress.value = '3'; s.ids.sleepQuality.value = '4'; s.ids.recentActivity.value = 'Exercise'; s.ids.assessmentNotes.value = 'Synthetic';
  await s.ids.assessmentForm.events.submit({preventDefault() {}});
  assert.equal(sent[0][0], 'assessment'); assert.equal(sent[0][3].fatigue, 2); assert.equal(sent[0][3].recent_activity, 'Exercise'); assert.match(s.ids.assessmentFeedback.textContent, /waiting to synchronize/);
  s.ids.communicationSubject.value = 'Health report'; s.ids.communicationDelay.value = '30';
  await s.ids.communicationForm.events.submit({preventDefault() {}});
  assert.equal(sent[1][0], 'communication'); assert.equal(sent[1][3].delay_seconds, 30); assert.match(s.ids.communicationFeedback.textContent, /sync queue/);
});
