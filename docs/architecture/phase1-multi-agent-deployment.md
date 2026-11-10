# Soundwave Phase 1 — Multi-Agent Deployment Guide

## Overview

This document describes the complete Phase 1 deployment of the Soundwave Multi-Agent AI Framework. The system provides a self-hosted AI assistant with **native tool-calling** capabilities, connecting to Gmail and Google Calendar through MCP (Model Context Protocol) servers, orchestrated across a heterogeneous 4-node Kubernetes cluster.

**Date:** 2026-03-08  
**Author:** the operator Teixeira  
**Status:** Phase 1 Complete — Gmail + Calendar operational

---

## Architecture

```
Client (Browser)
    │ HTTPS :31443
    ▼
HAProxy GW (megatron) ─── TLS termination, path routing
    │
    ▼
OpenWebUI (megatron) ─── Native Function Calling mode
    │
    │  OpenAI-compat API :8000
    ▼
Qwen3-8B Agent Brain (soundwave) ─── Tool-call router
    │
    ├── MCP tools/call ──▶ Gmail MCP (thundercracker :8100/gmail)
    │                           │
    │                           └──▶ Google Gmail API (OAuth 2.0)
    │
    ├── MCP tools/call ──▶ Calendar MCP (thundercracker :8200/google-calendar)
    │                           │
    │                           └──▶ Google Calendar API (OAuth 2.0)
    │
    ├── Code tasks ──▶ Qwen3-Coder-AWQ (megatron :8000)
    │
    └── General chat ──▶ MiniMax M2.5 (shockwave :8001)
```

---

## Cluster Topology

| Node | Role | OS | Arch | GPU | IP |
|------|------|----|------|-----|----|
| `soundwave` | Control Plane + Agent | Fedora 43 | x86_64 | RTX 4090 (24GB) | 192.168.15.2 |
| `megatron` | Worker (Frontend + Code) | Ubuntu 24.04 | ARM64 | DGX Spark (Blackwell) | 192.168.16.8 |
| `shockwave` | Worker (Chat) | Ubuntu 24.04 L4T | ARM64 | Jetson Thor | 192.168.16.7 |
| `thundercracker` | Worker (MCP Tools) | Fedora 43 | x86_64 | None | 192.168.16.2 |

---

## Pod Inventory (namespace: ai)

| Pod | Node | Image | Port | Service Type | Purpose |
|-----|------|-------|------|-------------|---------|
| haproxy-gw | megatron | haproxy:3.0 | 31443/31200 | NodePort | API Gateway + TLS |
| open-webui | megatron | open-webui:ollama | 8080 | ClusterIP | Web UI |
| qwen3-coder-awq | megatron | vllm:cu130-aarch64 | 8000 | ClusterIP | Code generation |
| qwen3-8b-agent | soundwave | vllm:latest | 8000 | ClusterIP | Tool-calling agent |
| gmail-mcp | thundercracker | mcpo:main | 8100 | ClusterIP | Gmail MCP bridge |
| gcal-mcp | thundercracker | mcpo:main | 8200 | ClusterIP | Calendar MCP bridge |
| minimax-m2-5 | shockwave | minimax-llama:latest | 8001 | ClusterIP | General chat |

---

## Prerequisites

Before starting, ensure the base Kubernetes cluster is operational with all 4 nodes in `Ready` state. Refer to `kubernetes-multiarch-install-guide-flannel.md` for the base cluster setup.

Required:
- Kubernetes v1.32 with Flannel CNI
- NVIDIA GPU Operator deployed
- `hf-token` secret in namespace `ai` (HuggingFace access token)
- HAProxy Ingress with TLS (see `final-fixed.md`)
- OpenWebUI deployed and accessible
- Node.js v18+ on soundwave (for OAuth token generation)
- Google Cloud Platform account

---

## Deployment Procedure

### Step 1 — Firewall Configuration (Fedora Nodes)

Flannel requires the `cni0` and `flannel.1` interfaces to be in the `trusted` firewall zone. Without this, cross-node pod traffic is silently dropped.

**On soundwave:**

```bash
sudo firewall-cmd --permanent --zone=trusted --add-interface=cni0
sudo firewall-cmd --permanent --zone=trusted --add-interface=flannel.1
sudo firewall-cmd --reload
```

**On thundercracker:**

```bash
sudo firewall-cmd --permanent --zone=trusted --add-interface=cni0
sudo firewall-cmd --permanent --zone=trusted --add-interface=flannel.1
sudo firewall-cmd --reload
```

**Verification:**

```bash
sudo firewall-cmd --get-active-zones
# cni0 and flannel.1 should appear under 'trusted'
```

> **Note:** Ubuntu nodes (megatron, shockwave) don't need this — ufw is inactive and iptables is managed by Flannel/kube-proxy directly.

---

### Step 2 — Deploy Qwen3-8B Agent on soundwave

#### 2.1 — Create Persistent Volume for HuggingFace Cache

```bash
kubectl apply -f volumes/pv-hf-cache-soundwave.yaml
```

**File: `volumes/pv-hf-cache-soundwave.yaml`**

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-hf-cache-soundwave
spec:
  capacity:
    storage: 30Gi
  accessModes:
  - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: local-hostpath
  hostPath:
    path: /var/lib/vllm/hf-cache
    type: DirectoryOrCreate
  nodeAffinity:
    required:
      nodeSelectorTerms:
      - matchExpressions:
        - key: kubernetes.io/hostname
          operator: In
          values:
          - soundwave
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: hf-cache-soundwave
  namespace: ai
spec:
  accessModes:
  - ReadWriteOnce
  storageClassName: local-hostpath
  resources:
    requests:
      storage: 30Gi
```

Verify:

```bash
kubectl get pv pv-hf-cache-soundwave
kubectl get pvc -n ai hf-cache-soundwave
```

#### 2.2 — Deploy Qwen3-8B Agent

```bash
kubectl apply -f deployments/qwen3-8b-agent-deployment.yaml
```

**Key configuration notes:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `--dtype` | float16 | Full precision for reliable tool-call JSON |
| `--max-model-len` | 16384 | 32k causes OOM — model uses 15.27 GiB, leaving only 3.48 GiB for KV cache at 0.85 utilization. 16k fits comfortably (~2.25 GiB) |
| `--gpu-memory-utilization` | 0.85 | Leaves headroom on the 24GB RTX 4090 |
| `--enable-auto-tool-choice` | — | Enables native OpenAI function-calling API |
| `--tool-call-parser` | hermes | Parses Hermes-style tool calls from Qwen3 |

> **Note:** `--chat-template-kwargs` is NOT a valid CLI argument in vLLM v0.17.x. To disable thinking mode, pass `"chat_template_kwargs": {"enable_thinking": false}` per-request in the API call body or configure it in OpenWebUI's system prompt.

Wait for the model to download and load:

```bash
kubectl -n ai logs -f deployment/qwen3-8b-agent
# Wait for: "Uvicorn running on http://0.0.0.0:8000"
```

#### 2.3 — Verify Agent Deployment

```bash
# Check pod status
kubectl -n ai get pods -l app=qwen3-8b-agent

# Test from within the cluster
kubectl -n ai exec -it deployment/open-webui -- \
  curl -s http://qwen3-8b-agent:8000/v1/models

# Test tool calling directly
kubectl -n ai exec -it deployment/qwen3-8b-agent -- \
  curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-8b-agent",
    "messages": [{"role": "user", "content": "Check my emails"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "search_emails",
        "description": "Search Gmail",
        "parameters": {
          "type": "object",
          "properties": {"query": {"type": "string"}},
          "required": ["query"]
        }
      }
    }],
    "max_tokens": 512
  }'
```

The response should contain `"finish_reason": "tool_calls"` with a populated `tool_calls` array.

---

### Step 3 — Google Cloud OAuth Setup

#### 3.1 — Create GCP Project

1. Go to https://console.cloud.google.com
2. Create a new project named `soundwave-mcp` (or use an existing one)

#### 3.2 — Enable APIs

Enable both APIs in your project:

- **Gmail API**: https://console.cloud.google.com/apis/library/gmail.googleapis.com
- **Google Calendar API**: https://console.cloud.google.com/apis/library/calendar-json.googleapis.com

#### 3.3 — Configure OAuth Consent Screen

Navigate to **Google Auth Platform** (or **APIs & Services > OAuth consent screen**):

1. Click **Get started** (or **Configure Consent Screen**)
2. **App name**: `Soundwave MCP`
3. **User support email**: your email
4. **Audience**: External
5. Click through to complete initial setup

**Add scopes** (via **Data access** in the sidebar):

- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/calendar`
- `https://www.googleapis.com/auth/calendar.events`

**Add test users** (via **Audience** in the sidebar):

- Add your Gmail address as a test user

> **Important:** In "External/Testing" mode, only listed test users can authenticate. The OAuth consent flow will fail for unlisted users.

#### 3.4 — Create OAuth Client Credentials

Navigate to **Clients** in the sidebar:

1. Click **+ Create Client**
2. **Application type**: Desktop app
3. **Name**: `soundwave-mcp-desktop`
4. Click **Create**
5. Click **Download JSON** — save as `credentials.json`

#### 3.5 — Generate OAuth Tokens

The MCP servers need refresh tokens to access Google APIs. Desktop app clients automatically allow `http://localhost` redirects.

**On soundwave** (requires browser and Node.js):

```bash
# Create working directory
mkdir -p ~/Documents/Soundwave/oauth
cd ~/Documents/Soundwave/oauth

# Copy your downloaded credentials.json here
cp ~/Downloads/client_secret_*.json ./credentials.json

# Install dependencies
npm init -y
npm install googleapis
```

Create the token generation script:

```bash
cat > generate-tokens.js << 'EOF'
const { google } = require('googleapis');
const http = require('http');
const fs = require('fs');
const url = require('url');

const creds = JSON.parse(fs.readFileSync('credentials.json'));
const { client_id, client_secret } = creds.installed || creds.web;
const redirect_uri = 'http://localhost:3456/callback';

const oauth2Client = new google.auth.OAuth2(client_id, client_secret, redirect_uri);

const SCOPES = [
  'https://www.googleapis.com/auth/gmail.modify',
  'https://www.googleapis.com/auth/calendar',
  'https://www.googleapis.com/auth/calendar.events',
];

const authUrl = oauth2Client.generateAuthUrl({
  access_type: 'offline',
  scope: SCOPES,
  prompt: 'consent',
});

console.log('\n🔗 Open this URL in your browser:\n');
console.log(authUrl);
console.log('\nWaiting for callback...\n');

const server = http.createServer(async (req, res) => {
  const query = url.parse(req.url, true).query;
  if (query.code) {
    const { tokens } = await oauth2Client.getToken(query.code);
    
    fs.writeFileSync('gmail-token.json', JSON.stringify(tokens, null, 2));
    console.log('✅ gmail-token.json saved');
    
    fs.writeFileSync('calendar-token.json', JSON.stringify(tokens, null, 2));
    console.log('✅ calendar-token.json saved');
    
    res.end('Success! Tokens saved. You can close this tab.');
    server.close();
    process.exit(0);
  }
});

server.listen(3456, () => {
  console.log('Listening on http://localhost:3456/callback');
});
EOF
```

Run the script:

```bash
node generate-tokens.js
```

This will:
1. Print an authorization URL
2. Open it in your browser
3. Google will ask you to sign in and authorize
4. After consent, it redirects to localhost and saves both token files

> **Warning:** If you see "Google hasn't verified this app", click **Continue** (this is expected for test-mode apps).

Verify you have all three files:

```bash
ls -la credentials.json gmail-token.json calendar-token.json
```

> **Security:** Add `oauth/` to your `.gitignore` — these files must never be committed to version control.

#### 3.6 — Create Kubernetes Secrets

```bash
cd ~/Documents/Soundwave/oauth

# Gmail secret (note: key file must be named gcp-oauth.keys.json)
kubectl -n ai create secret generic google-oauth-gmail \
  --from-file=gcp-oauth.keys.json=./credentials.json \
  --from-file=token.json=./gmail-token.json

# Calendar secret
kubectl -n ai create secret generic google-oauth-calendar \
  --from-file=gcp-oauth.keys.json=./credentials.json \
  --from-file=token.json=./calendar-token.json

# Verify
kubectl -n ai get secrets | grep google
```

**Expected output:**

```
google-oauth-calendar   Opaque   2      Xs
google-oauth-gmail      Opaque   2      Xs
```

> **Note on filenames:** The Gmail MCP package (`@gongrzhe/server-gmail-autoauth-mcp`) hardcodes looking for `gcp-oauth.keys.json` in `/root/.gmail-mcp/`. The Calendar MCP package (`@gongrzhe/server-calendar-autoauth-mcp`) looks in `/root/.calendar-mcp/`. The init containers in the deployments handle copying files to these locations.

#### 3.7 — Token Refresh

Access tokens expire after 1 hour. The MCP servers automatically refresh them using the refresh token stored in the secret. However, if the GCP app is in **testing mode**, refresh tokens expire after **7 days**. When this happens:

1. Re-run `node generate-tokens.js` on soundwave
2. Update the secrets:

```bash
cd ~/Documents/Soundwave/oauth

kubectl -n ai delete secret google-oauth-gmail google-oauth-calendar

kubectl -n ai create secret generic google-oauth-gmail \
  --from-file=gcp-oauth.keys.json=./credentials.json \
  --from-file=token.json=./gmail-token.json

kubectl -n ai create secret generic google-oauth-calendar \
  --from-file=gcp-oauth.keys.json=./credentials.json \
  --from-file=token.json=./calendar-token.json
```

3. Restart the MCP pods:

```bash
kubectl -n ai rollout restart deployment gmail-mcp gcal-mcp
```

To avoid the 7-day expiry, publish the GCP app to **production** in the OAuth consent screen settings.

---

### Step 4 — Deploy MCP Servers on thundercracker

#### 4.1 — Deploy Gmail MCP

```bash
kubectl apply -f deployments/gmail-mcp-deployment.yaml
```

**Key design decisions:**

- Uses `ghcr.io/open-webui/mcpo:main` as the MCP-to-OpenAPI proxy
- MCPO launches `@gongrzhe/server-gmail-autoauth-mcp` via npx as a stdio subprocess
- Init container copies OAuth credentials from K8s secret to `/root/.gmail-mcp/` (the hardcoded path the npm package expects)
- Token is copied as `credentials.json` (the filename the package uses for saved tokens)
- No environment variables — the Gmail MCP package ignores them and reads directly from the filesystem

Wait for startup (npm download takes ~60 seconds on first boot):

```bash
kubectl -n ai logs -f deployment/gmail-mcp
# Wait for: "Successfully connected to 'gmail'"
```

#### 4.2 — Deploy Calendar MCP

```bash
kubectl apply -f deployments/gcal-mcp-deployment.yaml
```

Same pattern as Gmail. The Calendar MCP package is `@gongrzhe/server-calendar-autoauth-mcp` and expects credentials in `/root/.calendar-mcp/`.

> **Note:** The package name is `server-calendar-autoauth-mcp` (NOT `server-google-calendar-mcp` — that package does not exist on npm).

```bash
kubectl -n ai logs -f deployment/gcal-mcp
# Wait for: "Successfully connected to 'google-calendar'"
```

#### 4.3 — Verify MCP Servers

```bash
# Check both pods are running
kubectl -n ai get pods -l role=mcp-server

# Verify Gmail tools are exposed (should show paths, not empty)
kubectl -n ai exec -it deployment/qwen3-8b-agent -- \
  curl -s http://gmail-mcp:8100/gmail/openapi.json | python3 -m json.tool | head -40

# Verify Calendar tools
kubectl -n ai exec -it deployment/qwen3-8b-agent -- \
  curl -s http://gcal-mcp:8200/google-calendar/openapi.json | python3 -m json.tool | head -40
```

> **Important:** Tools are exposed under sub-paths `/gmail/` and `/google-calendar/`, not at the root. The root `/openapi.json` shows `"paths": {}` but provides a link to the sub-path where actual tools live.

---

### Step 5 — Update HAProxy Configuration

Apply the updated HAProxy configmap with routes for the new services:

```bash
kubectl apply -f configmap/02-haproxy-config-updated.yaml
kubectl -n ai rollout restart deployment haproxy-gw
```

**New routes (optional, for debugging):**

| Path | Backend |
|------|---------|
| `/` | OpenWebUI (default) |
| `/v1/` | Qwen3-8B Agent API |
| `/gmail/` | Gmail MCP MCPO |
| `/calendar/` | Calendar MCP MCPO |

Verify:

```bash
curl -sk https://192.168.16.8:31443 | head -5          # OpenWebUI
curl -sk https://192.168.16.8:31443/v1/models           # Agent API
```

---

### Step 6 — Configure OpenWebUI

#### 6.1 — Add Qwen3-8B as a Model Connection

1. Go to **Admin Panel** → **Settings** → **Connections**
2. Under **OpenAI API**, click **+**
3. **URL**: `http://qwen3-8b-agent.ai.svc.cluster.local:8000/v1`
4. **API Key**: `EMPTY`
5. Click verify — should show `qwen3-8b-agent`
6. **Save**

#### 6.2 — Add MCP Tool Servers

1. Go to **Admin Panel** → **Settings** → **Integrations**
2. Under **Manage Tool Servers**, click **+**
3. Add Gmail MCP:
   - **Type**: OpenAPI
   - **URL**: `http://gmail-mcp.ai.svc.cluster.local:8100/gmail`
4. Add Calendar MCP:
   - **Type**: OpenAPI
   - **URL**: `http://gcal-mcp.ai.svc.cluster.local:8200/google-calendar`
5. **Save**

> **Critical:** The URLs must include the sub-path (`/gmail` and `/google-calendar`). Without the sub-path, OpenWebUI discovers zero tools.

#### 6.3 — Create the Soundwave Agent Model

1. Go to **Workspace** → **Models** → **+ New Model**
2. **Model Name**: `Soundwave Agent`
3. **Base Model**: `qwen3-8b-agent`
4. **System Prompt**:

```
You are Soundwave, a helpful AI assistant with access to Gmail and Google Calendar.
When the user asks you to send emails, read inbox, create events, or check schedules,
use the available tools. Always confirm actions before executing them.
Be concise and action-oriented.
```

5. Under **Tools**, check both **Gmail-Mcp** and **Gcal-Mcp**
6. Under **Capabilities**, uncheck everything except **Status Updates** (reduces noise for smaller models)
7. Click **Advanced Params** → **Show** → set **Function Calling** to **Native**
8. Click **Save & Update**

---

### Step 7 — Verification

#### Full cluster status:

```bash
kubectl -n ai get pods -o wide
kubectl -n ai get svc
```

**Expected: 7 pods, all 1/1 Running across 4 nodes.**

#### End-to-end test:

1. Open `https://192.168.16.8:31443`
2. Start a **New Chat**
3. Select **Soundwave Agent** as the model
4. Test Gmail: `Show me my latest emails`
5. Test Calendar: `List my calendar events from 2026-03-09 to 2026-03-15`

> **Calendar tip:** Qwen3-8B sometimes generates malformed JSON for complex Calendar tool calls (e.g., `get_current_timestamp`). Providing explicit dates in the prompt avoids this issue. Phase 2 (LangGraph orchestration) will address this with more robust tool-call handling.

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| vLLM crashes with `unrecognized arguments: --chat-template-kwargs` | Not a CLI arg in vLLM v0.17.x | Remove the arg; use per-request API parameter instead |
| vLLM OOM: "4.5 GiB KV cache needed, only 3.48 GiB available" | `--max-model-len` too high for available VRAM | Reduce to 16384 (or lower `--gpu-memory-utilization`) |
| Cross-node curl returns exit code 7 (connection refused) | Fedora firewalld blocking Flannel interfaces | Add `cni0` and `flannel.1` to trusted zone |
| MCPO shows `"paths": {}` (no tools) | MCP server failed to initialize | Check MCPO logs for auth errors |
| Gmail MCP: `OAuth keys file not found` | Package expects `gcp-oauth.keys.json` in `/root/.gmail-mcp/` | Fix init container to copy with correct filename to correct path |
| Calendar MCP: `npm 404 Not Found` | Wrong package name | Use `@gongrzhe/server-calendar-autoauth-mcp` (not `server-google-calendar-mcp`) |
| OpenWebUI: model doesn't use tools | Tools not enabled or Function Calling not set to Native | Check model config: tools checked, Advanced Params → Function Calling → Native |
| OpenWebUI: tools listed but model ignores them | OpenWebUI URL missing sub-path | Use `/gmail` and `/google-calendar` sub-paths in tool server URLs |
| Calendar: malformed JSON error | Qwen3-8B struggles with complex tool schemas | Provide explicit dates in prompt; Phase 2 will add retry logic |
| Token 401 Unauthorized | Access token expired (1-hour lifespan) | Normal — refresh tokens handle this automatically |
| Refresh token expired | GCP app in testing mode (7-day limit) | Re-run `generate-tokens.js` and update K8s secrets |

---

## File Structure

```
Soundwave/
├── configmap/
│   └── 02-haproxy-config-updated.yaml     # HAProxy with new routes
├── deployments/
│   ├── 01-open-webui.yaml                  # OpenWebUI (existing)
│   ├── 03-haproxy-gw.yaml                  # HAProxy gateway (existing)
│   ├── minimax-m2.5-deploy.yaml            # MiniMax on shockwave (existing)
│   ├── qwen3-coder-awq-deployment.yaml     # Qwen3-Coder on megatron (existing)
│   ├── qwen3-coder-awq-service.yaml        # Qwen3-Coder service (existing)
│   ├── qwen3-8b-agent-deployment.yaml      # ★ Qwen3-8B agent on soundwave
│   ├── gmail-mcp-deployment.yaml           # ★ Gmail MCP on thundercracker
│   └── gcal-mcp-deployment.yaml            # ★ Calendar MCP on thundercracker
├── volumes/
│   ├── pv-openwebui.yaml                   # OpenWebUI storage (existing)
│   ├── pv-hf-cache-vllm-megatron.yaml      # HF cache megatron (existing)
│   └── pv-hf-cache-soundwave.yaml          # ★ HF cache soundwave
├── oauth/                                   # ★ OAuth credentials (gitignored)
│   ├── credentials.json                    # GCP OAuth client credentials
│   ├── gmail-token.json                    # Gmail refresh token
│   ├── calendar-token.json                 # Calendar refresh token
│   └── generate-tokens.js                  # Token generation script
├── .gitignore                              # Must include: oauth/
├── README.md
├── kubernetes-multiarch-install-guide-flannel.md
├── final-fixed.md
├── HA-Proxy.md
├── open_webui.md
└── phase1-multi-agent-deployment.md        # ★ This document
```

---

## Security Considerations

- OAuth credentials are stored as K8s Opaque secrets — not in Git
- The `oauth/` directory is in `.gitignore`
- MCP servers run on thundercracker (no GPU, no sensitive workloads)
- TLS termination happens at HAProxy — internal cluster traffic is unencrypted over Flannel VXLAN
- Google API access is scoped to `gmail.modify` and `calendar.events` — no admin scopes
- Consider deploying a NetworkPolicy to restrict MCP server access (see `multi-agent-deployment-guide.md`)

---

## Phase 2 Roadmap

- LangGraph multi-agent orchestration layer (new K8s deployment)
- Multi-agent routing: planner → Gmail agent, Calendar agent, Code agent
- Parallel tool calls across MCP servers
- Retry logic for malformed tool-call JSON
- Memory persistence across conversations
- Additional MCP servers (Slack, Drive, etc.)
