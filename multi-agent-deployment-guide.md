# Soundwave Multi-Agent Deployment Guide

## Architecture Summary

| Component | Node | Port | Purpose |
|-----------|------|------|---------|
| Qwen3-8B Agent | soundwave (RTX 4090) | :8000 | Tool-calling agent brain |
| Gmail MCP | thundercracker (no GPU) | :8100 | Gmail API via MCP/MCPO |
| Calendar MCP | thundercracker (no GPU) | :8200 | Google Calendar via MCP/MCPO |

All components deploy into namespace `ai`.

---

## Step 1 — Google Cloud OAuth Setup

Both MCP servers need Google OAuth2 credentials.

```bash
# 1. Go to https://console.cloud.google.com/apis/credentials
# 2. Create OAuth 2.0 Client ID (type: Desktop App)
# 3. Enable these APIs in your GCP project:
#    - Gmail API
#    - Google Calendar API
# 4. Download the credentials.json file

# 5. Generate initial token.json by running locally first:
npx -y @gongrzhe/server-gmail-autoauth-mcp
# This opens a browser for OAuth consent. After auth, token.json is created.

# Repeat for Calendar if using separate credentials:
npx -y @gongrzhe/server-google-calendar-mcp
```

---

## Step 2 — Create Kubernetes Secrets

```bash
# Gmail OAuth secret
kubectl -n ai create secret generic google-oauth-gmail \
  --from-file=credentials.json=./credentials.json \
  --from-file=token.json=./gmail-token.json

# Calendar OAuth secret
# (use same credentials.json if same GCP project, different token.json)
kubectl -n ai create secret generic google-oauth-calendar \
  --from-file=credentials.json=./credentials.json \
  --from-file=token.json=./calendar-token.json
```

---

## Step 3 — Deploy Storage (soundwave HF cache)

```bash
kubectl apply -f volumes/pv-hf-cache-soundwave.yaml

# Verify
kubectl get pv pv-hf-cache-soundwave
kubectl get pvc -n ai hf-cache-soundwave
```

---

## Step 4 — Deploy Qwen3-8B Agent on soundwave

```bash
kubectl apply -f deployments/qwen3-8b-agent-deployment.yaml

# Watch the pod come up (model download takes a few minutes first time)
kubectl -n ai get pods -l app=qwen3-8b-agent -w

# Check logs for successful model load
kubectl -n ai logs -f deployment/qwen3-8b-agent

# Wait for "Uvicorn running on http://0.0.0.0:8000"
```

### Verify Tool Calling

```bash
# Test from within the cluster
kubectl -n ai run curl-test --rm -it --image=curlimages/curl -- \
  curl -s http://qwen3-8b-agent.ai.svc.cluster.local:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-8b-agent",
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "calculator",
        "description": "Perform arithmetic",
        "parameters": {
          "type": "object",
          "properties": {"expression": {"type": "string"}},
          "required": ["expression"]
        }
      }
    }],
    "max_tokens": 512
  }'
```

---

## Step 5 — Deploy MCP Servers on thundercracker

```bash
# Gmail MCP
kubectl apply -f deployments/gmail-mcp-deployment.yaml

# Calendar MCP
kubectl apply -f deployments/gcal-mcp-deployment.yaml

# Watch pods
kubectl -n ai get pods -l role=mcp-server -w
```

### Verify MCP Servers

```bash
# Gmail — check MCPO docs endpoint
kubectl -n ai run curl-test --rm -it --image=curlimages/curl -- \
  curl -s http://gmail-mcp.ai.svc.cluster.local:8100/docs

# Calendar — check MCPO docs endpoint
kubectl -n ai run curl-test --rm -it --image=curlimages/curl -- \
  curl -s http://gcal-mcp.ai.svc.cluster.local:8200/docs
```

---

## Step 6 — Configure OpenWebUI

### 6.1 Add Qwen3-8B as a Model Backend

Navigate to **Admin Panel > Settings > Connections**.

Add a new OpenAI API connection:
- **URL**: `http://qwen3-8b-agent.ai.svc.cluster.local:8000/v1`
- **API Key**: `EMPTY`
- **Model Filter**: `qwen3-8b-agent`

### 6.2 Add MCP Tool Servers

Navigate to **Admin Panel > Settings > External Tools**.

**Add Gmail MCP:**
- Click **+** to add new tool connection
- **Type**: OpenAPI (MCPO exposes OpenAPI, not raw MCP)
- **URL**: `http://gmail-mcp.ai.svc.cluster.local:8100`
- **Auth**: None (internal cluster traffic)

**Add Calendar MCP:**
- Click **+** to add new tool connection
- **Type**: OpenAPI
- **URL**: `http://gcal-mcp.ai.svc.cluster.local:8200`
- **Auth**: None

### 6.3 Configure Native Tool Calling

For the Qwen3-8B Agent model in OpenWebUI:

1. Go to **Workspace > Models** > edit `qwen3-8b-agent`
2. Under **Advanced Parameters**:
   - Set **Function Calling** to **Native**
3. Under **Tools**, check both:
   - Gmail MCP
   - Calendar MCP
4. **Save & Update**

### 6.4 Create a Dedicated Agent (Recommended)

Go to **Workspace > Models > New Model**:
- **Name**: `Soundwave Agent`
- **Base Model**: `qwen3-8b-agent`
- **System Prompt**:
```
You are Soundwave, a helpful AI assistant with access to Gmail and Google Calendar.
When the user asks you to send emails, read inbox, create events, or check schedules,
use the available tools. Always confirm actions before executing them.
Be concise and action-oriented. Confirm completions with a brief summary.
```
- **Tools**: Enable Gmail MCP, Calendar MCP
- **Capabilities**: Enable Status Updates only
- **Function Calling**: Native

---

## Step 7 — Verification Checklist

```bash
# All pods running
kubectl -n ai get pods -o wide

# Expected output (new pods):
# qwen3-8b-agent-xxxxx    1/1  Running  soundwave
# gmail-mcp-xxxxx         1/1  Running  thundercracker
# gcal-mcp-xxxxx          1/1  Running  thundercracker

# All services reachable
kubectl -n ai get svc

# Expected new services:
# qwen3-8b-agent  ClusterIP  x.x.x.x  8000/TCP
# gmail-mcp        ClusterIP  x.x.x.x  8100/TCP
# gcal-mcp         ClusterIP  x.x.x.x  8200/TCP
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Qwen3-8B OOM on soundwave | Lower `--gpu-memory-utilization` to 0.75 or reduce `--max-model-len` to 16384 |
| Tool calls return empty JSON | Check vLLM logs for parser errors; try `--tool-call-parser qwen3_xml` instead of `hermes` |
| Gmail MCP auth expired | Re-run local auth flow, update token.json in secret, restart pod |
| MCPO 502/connection refused | Check `kubectl -n ai logs` on the mcpo pod; npm package may need network access for first install |
| OpenWebUI can't reach MCP | Verify service DNS: `kubectl -n ai run test --rm -it --image=busybox -- nslookup gmail-mcp.ai.svc.cluster.local` |
| Model not appearing in OpenWebUI | Check Connections page — verify URL ends with `/v1` |

---

## Network Policy (Optional Hardening)

If you want to restrict MCP server access to only OpenWebUI and the agent:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mcp-server-access
  namespace: ai
spec:
  podSelector:
    matchLabels:
      role: mcp-server
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: open-webui
    - podSelector:
        matchLabels:
          role: agent-brain
```

---

## Future: Phase 2 — LangGraph Orchestration

When ready to add multi-agent routing, deploy a LangGraph service that:
1. Connects to both MCP servers via `MultiServerMCPClient`
2. Uses Qwen3-8B as the reasoning LLM
3. Exposes an OpenAI-compatible API for OpenWebUI to consume

A skeleton deployment for this will be provided in the next iteration.
