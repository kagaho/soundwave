const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function harness({ failure = false } = {}) {
  const calls = { exchanged: [], opened: [], chmod: [], written: [], closed: 0, logs: [] };
  let callback;
  let auth;
  const client = {
    generateAuthUrl(options) { auth = options; return 'https://accounts.example/authorize'; },
    async getToken(options) {
      calls.exchanged.push(options);
      if (failure) throw new Error('sensitive-provider-error');
      return { tokens: { refresh_token: 'fixture', access_token: 'fixture-access' } };
    },
  };
  const fakeFs = {
    constants: fs.constants,
    readFileSync() { return JSON.stringify({ installed: { client_id: 'fixture', client_secret: 'fixture' } }); },
    openSync(file, flags, mode) { calls.opened.push({ file, flags, mode }); return calls.opened.length; },
    fchmodSync(fd, mode) { calls.chmod.push({ fd, mode }); },
    ftruncateSync() {},
    writeFileSync(fd, data) { calls.written.push({ fd, data }); },
    closeSync() {},
  };
  const server = {
    listen(port, host, fn) { calls.listen = { port, host }; fn(); },
    close() { calls.closed++; },
    on() {},
  };
  const processMock = { umask(mask) { calls.umask = mask; }, exitCode: 0 };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'generate-tokens.js'), 'utf8'), {
    require(name) {
      if (name === 'googleapis') return { google: { auth: { OAuth2: function () { return client; } } } };
      if (name === 'node:http') return { createServer(fn) { callback = fn; return server; } };
      if (name === 'node:fs') return fakeFs;
      return require(name);
    },
    process: processMock,
    Buffer,
    URL,
    console: { log(message) { calls.logs.push(message); }, error(message) { calls.logs.push(message); } },
    setTimeout() { return { unref() {} }; },
    clearTimeout() {},
  });
  return {
    calls, auth, processMock,
    async request(query = {}, pathname = '/callback') {
      const response = { status: 200, setHeader() {}, writeHead(status) { this.status = status; return this; }, end(body) { this.body = body; return this; } };
      await callback({ method: 'GET', url: pathname+'?'+new URLSearchParams(query) }, response);
      return response;
    },
  };
}

test('listener is loopback-only; OAuth uses unpredictable state and S256 PKCE', () => {
  const h = harness();
  assert.equal(h.calls.listen.host, '127.0.0.1');
  assert.equal(h.calls.umask, 0o077);
  assert.equal(h.auth.code_challenge_method, 'S256');
  assert.equal(h.auth.state.length, 64);
  assert.notEqual(h.auth.state, harness().auth.state);
});

test('invalid state, wrong path and missing code cannot exchange or save tokens', async () => {
  const h = harness();
  assert.equal((await h.request({ code: 'fixture', state: 'invalid' })).status, 400);
  assert.equal((await h.request({ code: 'fixture', state: h.auth.state }, '/other')).status, 404);
  assert.equal((await h.request({ state: h.auth.state })).status, 400);
  assert.equal(h.calls.exchanged.length, 0);
  assert.equal(h.calls.opened.length, 0);
});

test('valid callback exchanges PKCE code and writes private files without following symlinks', async () => {
  const h = harness();
  const response = await h.request({ code: 'fixture-code', state: h.auth.state });
  assert.equal(response.status, 200);
  assert.equal(h.calls.exchanged[0].code, 'fixture-code');
  assert.ok(h.calls.exchanged[0].codeVerifier.length >= 43);
  assert.equal(h.calls.opened.length, 2);
  for (const file of h.calls.opened) {
    assert.equal(file.mode, 0o600);
    assert.ok(file.flags & fs.constants.O_NOFOLLOW);
  }
  assert.ok(h.calls.chmod.every(call => call.mode === 0o600));
  assert.equal(h.calls.closed, 1);
  assert.ok(!h.calls.logs.join(' ').includes('fixture-access'));
});

test('provider failure never logs the provider error or saves tokens', async () => {
  const h = harness({ failure: true });
  assert.equal((await h.request({ code: 'fixture', state: h.auth.state })).status, 500);
  assert.equal(h.calls.opened.length, 0);
  assert.equal(h.processMock.exitCode, 1);
  assert.ok(!h.calls.logs.join(' ').includes('sensitive-provider-error'));
});
