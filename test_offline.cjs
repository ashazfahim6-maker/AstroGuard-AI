const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup(fetchImpl) {
  const values = new Map();
  const localStorage = {getItem: key => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key)};
  const events = {};
  const context = vm.createContext({localStorage, navigator: {onLine: true}, fetch: fetchImpl,
    addEventListener: (name, callback) => {events[name] = callback;}, crypto: {randomUUID: () => 'fixed-id'},
    Date, Math, JSON, Error, console});
  vm.runInContext(fs.readFileSync('static/offline.js', 'utf8'), context);
  return {api: context.AstroOffline, values, events, context};
}

test('health snapshots and resources persist in browser storage', () => {
  const {api} = setup(async () => ({ok: true, json: async () => ({})}));
  api.cacheHealth('crew-01', {status: 'demo'}); api.cacheResource('timeline', 'crew-01', {events: [1]});
  assert.equal(api.health('crew-01').status, 'demo'); assert.deepEqual(api.resource('timeline', 'crew-01').events, [1]);
});

test('failed mutation queues once and synchronizes after reconnection', async () => {
  let online = false; const calls = [];
  const {api} = setup(async (url, options) => {
    calls.push({url, options}); if (!online) throw Error('offline');
    return {ok: true, json: async () => ({saved: true})};
  });
  const result = await api.sendOrQueue('assessment', 'crew-01', '/api/assessments?profile=crew-01', {fatigue: 2});
  assert.equal(result.queuedOffline, true); assert.equal(api.pendingCount(), 1);
  online = true; const synced = await api.sync();
  assert.equal(synced.sent, 1); assert.equal(synced.pending, 0); assert.equal(api.pendingCount(), 0);
  assert.equal(JSON.parse(calls.at(-1).options.body).client_id, 'fixed-id');
});

test('client validation errors are not stored for retry', async () => {
  const {api} = setup(async () => ({ok: false, status: 400, json: async () => ({error: 'Invalid fatigue'})}));
  await assert.rejects(api.sendOrQueue('assessment', 'crew-01', '/api/assessments', {}), /Invalid fatigue/);
  assert.equal(api.pendingCount(), 0);
});
