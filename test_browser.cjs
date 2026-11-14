/* Optional real-browser smoke test. Requires Node 22+, Python/Flask and Edge or Chrome. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const net = require('node:net');
const {spawn} = require('node:child_process');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function freePort() {
  const server = net.createServer(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port; await new Promise(resolve => server.close(resolve)); return port;
}
async function until(check, timeout = 10000) {
  const start = Date.now();
  while (Date.now() - start < timeout) { const value = await check(); if (value) return value; await sleep(100); }
  throw Error('Timed out waiting for browser condition');
}
async function main() {
  const executable = process.env.ASTROGUARD_BROWSER || [
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Google/Chrome/Application/chrome.exe'
  ].find(p => fs.existsSync(p));
  if (!executable) throw Error('Set ASTROGUARD_BROWSER to an Edge/Chrome executable.');
  const port = await freePort();
  const origin = 'http://127.0.0.1:' + port;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'astroguard-browser-'));
  const serverEnvironment = {...process.env, ASTROGUARD_DATABASE: path.join(profile, 'browser-test.db')};
  const server = spawn(process.env.ASTROGUARD_PYTHON || 'python', ['-c', `from app import app; app.run(host='127.0.0.1',port=${port})`], {cwd: __dirname, env: serverEnvironment, windowsHide: true, stdio: 'ignore'});
  let browser, socket;
  try {
    await until(async () => { try { return (await fetch(origin + '/api/health')).ok; } catch { return false; } });
    let debuggerUrl;
    browser = spawn(executable, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'], {windowsHide: true, stdio: ['ignore', 'ignore', 'pipe']});
    browser.stderr.on('data', chunk => { const match = chunk.toString().match(/DevTools listening on (ws:\/\/[^\s]+)/); if (match) debuggerUrl = match[1]; });
    await until(() => debuggerUrl);
    const debugOrigin = 'http://127.0.0.1:' + new URL(debuggerUrl).port;
    const page = await until(async () => (await (await fetch(debugOrigin + '/json/list')).json()).find(p => p.type === 'page'));
    socket = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
    let nextId = 0; const pending = new Map(); const browserErrors = [];
    socket.onmessage = event => {
      const message = JSON.parse(event.data);
      if (message.method === 'Runtime.exceptionThrown') browserErrors.push(message.params.exceptionDetails.text + ' ' + (message.params.exceptionDetails.exception?.description || ''));
      if (!message.id) return;
      const callbacks = pending.get(message.id); pending.delete(message.id);
      if (message.error) callbacks.reject(Error(message.error.message)); else callbacks.resolve(message.result);
    };
    const command = (method, params = {}) => new Promise((resolve, reject) => {
      const id = ++nextId; pending.set(id, {resolve, reject}); socket.send(JSON.stringify({id, method, params}));
    });
    const evaluate = async expression => {
      const result = await command('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
      if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
      return result.result.value;
    };
    await command('Runtime.enable'); await command('Page.enable');
    await command('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false});
    await command('Page.navigate', {url: origin});
    await until(() => evaluate("document.getElementById('hr')?.textContent !== '--' && typeof currentData !== 'undefined'"));
    assert.equal(await evaluate('currentData.simulated'), true);
    assert.equal(await evaluate("document.querySelectorAll('#trend svg').length"), 2);
    const initialStep = await evaluate('currentData.latest.step');
    await until(async () => await evaluate('currentData.latest.step') > initialStep, 8000);
    await evaluate("document.getElementById('pause').click()");
    const pausedStep = await evaluate('currentData.latest.step');
    await sleep(5500); assert.equal(await evaluate('currentData.latest.step'), pausedStep);
    console.log('PASS real-time sample generation and pause');
    await evaluate("document.querySelector('[data-scenario=elevated]').click()");
    await until(() => evaluate("!busy && currentData.latest.heart_rate === 125"));
    assert.match(await evaluate("document.getElementById('alerts').textContent"), /personal baseline/);
    await evaluate("document.querySelector('[data-scenario=normal]').click()");
    await until(() => evaluate("!busy && currentData.scenario === 'normal'"));
    assert.equal(await evaluate('currentData.anomalies.length'), 0);
    console.log('PASS scenarios, experimental explanations and recovery');
    await evaluate("document.getElementById('profileSelect').value='crew-02';document.getElementById('profileSelect').dispatchEvent(new Event('change'))");
    await until(() => evaluate("!busy && currentData.profile.id === 'crew-02'"));
    assert.match(await evaluate("document.getElementById('reportCsv').href"), /profile=crew-02/);
    await evaluate("document.querySelector('[data-view=profiles]').click();document.getElementById('heart_rate-value').value='90';document.getElementById('heart_rate-value').dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('baselineForm').requestSubmit()");
    await until(() => evaluate("!busy && currentData.baseline.heart_rate.value === 90"));
    assert.equal(await evaluate("document.getElementById('profilePanel').hidden"), false);
    const report = await evaluate("fetch(document.getElementById('reportJson').href).then(r=>r.json())");
    assert.equal(report.profile.id, 'crew-02'); assert.equal(report.baseline.heart_rate.value, 90); assert.equal(report.history.length, 48);
    const csv = await evaluate("fetch(document.getElementById('reportCsv').href).then(async r=>({body:await r.text(),disposition:r.headers.get('Content-Disposition')}))");
    assert.match(csv.disposition, /attachment/); assert.match(csv.body, /SIMULATED DATA/);
    const downloadPath = path.join(__dirname, 'artifacts', 'downloads');
    fs.mkdirSync(downloadPath, {recursive: true});
    const downloaded = path.join(downloadPath, 'astroguard-crew-02.csv');
    // Avoid mistaking a previous run's report for a completed download.
    if (fs.existsSync(downloaded)) fs.unlinkSync(downloaded);
    await command('Browser.setDownloadBehavior', {behavior: 'allow', downloadPath});
    await evaluate("document.getElementById('reportCsv').click()");
    await until(() => fs.existsSync(downloaded));
    assert.match(fs.readFileSync(downloaded, 'utf8'), /crew-02/);
    console.log('PASS profile isolation, baseline form and downloadable reports');
    await evaluate("document.querySelector('[data-view=assessment]').click();document.getElementById('fatigue').value='2';document.getElementById('stress').value='3';document.getElementById('sleepQuality').value='4';document.getElementById('assessmentNotes').value='Browser smoke test';document.getElementById('assessmentForm').requestSubmit()");
    await until(() => evaluate("document.getElementById('assessmentFeedback').textContent.includes('SQLite')"));
    const assessments = await evaluate("fetch('/api/assessments?profile=crew-02').then(r=>r.json())");
    assert.equal(assessments.assessments.length, 1); assert.equal(assessments.assessments[0].fatigue, 2);
    await evaluate("document.querySelector('[data-view=timeline]').click()");
    await until(() => evaluate("document.querySelectorAll('#timelineList .record-card').length > 0"));
    await evaluate("document.querySelector('[data-view=communications]').click();document.getElementById('communicationDelay').value='5';document.getElementById('communicationForm').requestSubmit()");
    await until(() => evaluate("document.getElementById('communicationFeedback').textContent.includes('accepted')"));
    const communications = await evaluate("fetch('/api/communications?profile=crew-02').then(r=>r.json())");
    assert.equal(communications.reports.length, 1); assert.equal(communications.reports[0].status, 'queued');
    await evaluate("document.querySelector('[data-view=insights]').click()");
    assert.equal(await evaluate("document.querySelectorAll('#insightList .insight-card').length"), 4);
    assert.match(await evaluate("fetch('/research').then(r=>r.text())"), /not clinically validated/);
    console.log('PASS assessment persistence, timeline, Earth queue, insights and research page');
    await evaluate("document.querySelector('[data-view=vitals]').click()");
    assert.equal(await evaluate("document.querySelectorAll('#trend svg').length"), 4);
    assert.equal(await evaluate("document.querySelectorAll('#details tbody tr').length"), 48);
    await evaluate("document.querySelector('[data-view=analytics]').click()");
    assert.equal(await evaluate("document.querySelectorAll('#details tbody tr').length"), 4);
    // Restore the default crew view for review screenshots.
    await evaluate("document.getElementById('profileSelect').value='crew-01';document.getElementById('profileSelect').dispatchEvent(new Event('change'))");
    await until(() => evaluate("!busy && currentData.profile.id === 'crew-01'"));
    await evaluate("document.querySelector('[data-view=overview]').click()");
    fs.mkdirSync(path.join(__dirname, 'artifacts'), {recursive: true});
    const screenshot = async filename => {
      const shot = await command('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true});
      fs.writeFileSync(path.join(__dirname, 'artifacts', filename), Buffer.from(shot.data, 'base64'));
    };
    await screenshot('dashboard-desktop.png');
    assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false);
    await command('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
    await sleep(200);
    assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false);
    assert.equal(await evaluate("getComputedStyle(document.querySelector('nav')).display"), 'flex');
    await screenshot('dashboard-mobile.png');
    await evaluate("document.querySelector('[data-view=profiles]').click()");
    assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false);
    assert.equal(await evaluate("document.getElementById('profilePanel').hidden"), false);
    await screenshot('baselines-mobile.png');
    await evaluate("document.querySelector('[data-view=overview]').click()");
    console.log('PASS desktop and mobile layouts, all navigation views');
    await command('Network.enable');
    await command('Network.emulateNetworkConditions', {offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0});
    await evaluate("document.getElementById('refresh').click()");
    await until(() => evaluate("!document.getElementById('requestError').hidden && !busy"));
    assert.equal(await evaluate("document.getElementById('hr').textContent"), '75');
    await command('Network.emulateNetworkConditions', {offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1});
    await evaluate("document.getElementById('refresh').click()");
    await until(() => evaluate("document.getElementById('requestError').hidden && !busy"));
    await evaluate("navigator.serviceWorker.ready.then(()=>true)");
    await command('Network.emulateNetworkConditions', {offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0});
    await command('Page.navigate', {url: origin + '/research'});
    await until(() => evaluate("document.body?.textContent.includes('Research demonstration only')"));
    await command('Network.emulateNetworkConditions', {offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1});
    assert.deepEqual(browserErrors, []);
    console.log('PASS offline failure, cached research shell, retry, no JavaScript exceptions');
    await command('Browser.close').catch(() => {});
  } finally {
    socket?.close(); browser?.kill(); server.kill();
    await sleep(500);
    // Delete only the exact temporary profile this test created under the OS temp directory.
    if (path.dirname(path.resolve(profile)) === path.resolve(os.tmpdir()) && path.basename(profile).startsWith('astroguard-browser-')) {
      try { fs.rmSync(profile, {recursive: true, force: true, maxRetries: 3, retryDelay: 200}); } catch { /* Browser may still be releasing its temporary profile. */ }
    }
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
