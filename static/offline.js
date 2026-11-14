/* Browser-only cache and mutation queue for synthetic demo data. */
(function (root) {
  'use strict';
  const PREFIX = 'astroguard-v3:';
  const QUEUE_KEY = PREFIX + 'sync-queue';
  const listeners = new Set();
  const storage = (() => {
    try { return root.localStorage; } catch (_) { return null; }
  })();
  function read(key, fallback = null) {
    if (!storage) return fallback;
    try { const value = storage.getItem(PREFIX + key); return value ? JSON.parse(value) : fallback; }
    catch (_) { return fallback; }
  }
  function write(key, value) {
    if (!storage) return false;
    try { storage.setItem(PREFIX + key, JSON.stringify(value)); return true; }
    catch (_) { return false; }
  }
  function queueItems() {
    if (!storage) return [];
    try { return JSON.parse(storage.getItem(QUEUE_KEY) || '[]'); }
    catch (_) { return []; }
  }
  function saveQueue(items) {
    if (!storage) return false;
    try { storage.setItem(QUEUE_KEY, JSON.stringify(items)); return true; }
    catch (_) { return false; }
  }
  function emit(status) { listeners.forEach(listener => listener(status)); }
  function makeId() {
    if (root.crypto?.randomUUID) return root.crypto.randomUUID();
    return 'offline-' + Date.now() + '-' + Math.random().toString(16).slice(2);
  }
  function enqueue(type, profileId, url, body) {
    const items = queueItems();
    const item = {id: body.client_id || makeId(), type, profileId, url, body,
                  queuedAt: new Date().toISOString(), attempts: 0};
    item.body.client_id = item.id;
    items.push(item); saveQueue(items);
    emit({online: false, pending: items.length});
    return item;
  }
  async function sync() {
    const items = queueItems();
    if (!items.length) { emit({online: root.navigator?.onLine !== false, pending: 0}); return {sent: 0, pending: 0}; }
    const remaining = []; let sent = 0;
    for (const item of items) {
      try {
        const response = await root.fetch(item.url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(item.body)});
        if (!response.ok) {
          if (response.status >= 400 && response.status < 500) continue;
          throw Error('Server returned ' + response.status);
        }
        sent += 1;
      } catch (_) {
        item.attempts += 1; remaining.push(item);
      }
    }
    saveQueue(remaining); emit({online: remaining.length === 0, pending: remaining.length});
    return {sent, pending: remaining.length};
  }
  async function sendOrQueue(type, profileId, url, body) {
    if (!body.client_id) body.client_id = makeId();
    try {
      const response = await root.fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      if (!response.ok) {
        let message = 'Server returned ' + response.status;
        try { message += ': ' + (await response.json()).error; } catch (_) {}
        const error = Error(message); error.permanent = response.status >= 400 && response.status < 500; throw error;
      }
      return {queuedOffline: false, data: await response.json()};
    } catch (error) {
      if (error.permanent) throw error;
      const item = enqueue(type, profileId, url, body);
      return {queuedOffline: true, item};
    }
  }
  const api = {
    read, write, enqueue, sync, sendOrQueue,
    pendingCount: () => queueItems().length,
    onStatus(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    cacheHealth(profileId, data) { write('health:' + profileId, data); },
    health(profileId) { return read('health:' + profileId); },
    cacheResource(name, profileId, data) { write(name + ':' + profileId, data); },
    resource(name, profileId) { return read(name + ':' + profileId); }
  };
  root.AstroOffline = api;
  root.addEventListener?.('online', () => sync());
  if (root.navigator?.serviceWorker) root.navigator.serviceWorker.register('/service-worker.js').catch(() => {});
})(typeof window !== 'undefined' ? window : globalThis);
