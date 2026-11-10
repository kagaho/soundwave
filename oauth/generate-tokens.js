// Run from oauth/ after placing your ignored Google desktop credentials.json here.
const { google } = require('googleapis');
const http = require('node:http');
const fs = require('node:fs');
const crypto = require('node:crypto');

process.umask(0o077);
const creds = JSON.parse(fs.readFileSync('credentials.json', 'utf8'));
const config = creds.installed || creds.web;
if (!config || !config.client_id || !config.client_secret) {
  throw new Error('credentials.json must contain a Google desktop or web OAuth client');
}
const redirectUri = 'http://localhost:3456/callback';
const oauth2Client = new google.auth.OAuth2(config.client_id, config.client_secret, redirectUri);
const state = crypto.randomBytes(32).toString('hex');
const verifier = crypto.randomBytes(48).toString('base64url');
const authUrl = oauth2Client.generateAuthUrl({
  access_type: 'offline',
  scope: ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/calendar'],
  prompt: 'consent',
  state,
  code_challenge: crypto.createHash('sha256').update(verifier).digest('base64url'),
  code_challenge_method: 'S256',
});
let exchanging = false;

function sameState(value) {
  if (typeof value !== 'string') return false;
  const actual = Buffer.from(value);
  const expected = Buffer.from(state);
  return actual.length === expected.length && crypto.timingSafeEqual(actual, expected);
}

function saveToken(path, tokens) {
  // O_NOFOLLOW prevents accidentally writing through a preexisting symlink.
  const fd = fs.openSync(path, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_NOFOLLOW, 0o600);
  try {
    fs.fchmodSync(fd, 0o600);
    fs.ftruncateSync(fd, 0);
    fs.writeFileSync(fd, JSON.stringify(tokens, null, 2));
  } finally {
    fs.closeSync(fd);
  }
}

const server = http.createServer(async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  const callback = new URL(req.url, redirectUri);
  if (req.method !== 'GET' || callback.pathname !== '/callback') {
    res.writeHead(404).end('Not found');
    return;
  }
  if (!sameState(callback.searchParams.get('state'))) {
    res.writeHead(400).end('Invalid OAuth state. Restart authorization.');
    return;
  }
  if (callback.searchParams.has('error')) {
    res.writeHead(400).end('Authorization was declined. Restart authorization.');
    server.close();
    clearTimeout(timeout);
    return;
  }
  const code = callback.searchParams.get('code');
  if (!code || exchanging) {
    res.writeHead(400).end('Missing code or authorization already in progress.');
    return;
  }
  exchanging = true;
  try {
    const { tokens } = await oauth2Client.getToken({ code, codeVerifier: verifier, redirect_uri: redirectUri });
    if (!tokens.refresh_token) {
      throw new Error('No refresh token returned');
    }
    saveToken('gmail-token.json', tokens);
    saveToken('calendar-token.json', tokens);
    console.log('OAuth token files saved with mode 0600. Keep them outside Git.');
    res.end('Success. Token files saved locally. You can close this tab.');
  } catch {
    // Provider errors may contain credentials or the authorization code.
    console.error('OAuth exchange or token save failed. Restart authorization.');
    process.exitCode = 1;
    res.writeHead(500).end('Authorization failed. See the local console.');
  } finally {
    clearTimeout(timeout);
    server.close();
  }
});

const timeout = setTimeout(() => {
  console.error('Authorization timed out. Restart this helper.');
  process.exitCode = 1;
  server.close();
}, 5 * 60 * 1000);
timeout.unref();
server.on('error', () => {
  clearTimeout(timeout);
  console.error('Could not start the loopback callback listener.');
  process.exitCode = 1;
});
server.listen(3456, '127.0.0.1', () => {
  console.log('Open this URL in your browser:\n' + authUrl);
  console.log('Waiting for http://localhost:3456/callback (five minute timeout)');
});
