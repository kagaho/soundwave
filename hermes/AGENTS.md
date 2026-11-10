# Soundwave Hermes Infrastructure Repo

This repo contains the Kubernetes manifests, configuration, and skills
that deploy and configure the Hermes Agent on the Soundwave cluster.

Hermes runs on the `thundercracker` node in the `ai` namespace, backed
by a host-local PVC mounted at `/opt/data` (HERMES_HOME).

## Layout

- `hermes-deploy.yaml`          — Deployment manifest (idle mode)
- `hermes-pvc.yaml`             — PVC for /opt/data
- `hermes-secrets.yaml.example` — template; the real file is .gitignored
- `hermes-config/`              — SOUL.md and optional memory examples
- `skills/`                     — Versioned SKILL.md files
- `scripts/sync-to-pod.sh`      — Push repo contents to Hermes workspace
- Upstream Hermes source is maintained separately and is not vendored.

## Conventions

- All workloads live in namespace `ai`.
- Hermes Deployment pins to `nodeSelector: {kubernetes.io/hostname: thundercracker}`
  because the PVC `hermes-data` is host-local to that node.
- PVC access mode is RWO. Any Deployment touching this PVC must use
  `strategy: Recreate`.
- All Hermes-related containers run as `runAsUser: 10000`, `runAsGroup: 10000`,
  `fsGroup: 10000`. Do not run as root.
- File edits inside the PVC must use `cat … | kubectl exec -i $POD -- tee`,
  not `kubectl cp`. `kubectl cp` preserves the host UID (1000) which does
  not match the container UID (10000) and breaks ownership.
- Secrets are NEVER committed in cleartext. Real values live in:
  - The local `hermes-secrets.yaml` (gitignored)
  - The cluster Secret `ai/hermes-secrets`
  - A separate password manager (out of band)
  Use `hermes-secrets.yaml.example` as the template.

## Common commands

    # Active hermes pod
    POD=$(kubectl -n ai get pod -l app=hermes -o jsonpath='{.items[0].metadata.name}')

    # Push the repo to the pod's workspace
    ./scripts/sync-to-pod.sh

    # Open an interactive Hermes session inside the workspace
    # (Hermes reads AGENTS.md from CWD; no --working-dir flag exists)
    kubectl -n ai exec -it deploy/hermes -- sh -c \
      'cd /opt/data/workspace/soundwave-hermes && hermes'

    # Variant: isolated git worktree for parallel sessions (--worktree / -w)
    kubectl -n ai exec -it deploy/hermes -- sh -c \
      'cd /opt/data/workspace/soundwave-hermes && hermes -w'

    # Sync a single skill (without full repo sync)
    cat skills/<category>/<name>/SKILL.md | \
      kubectl -n ai exec -i $POD -- tee /opt/data/skills/<category>/<name>/SKILL.md > /dev/null

    # Apply / restart
    kubectl -n ai apply -f hermes-deploy.yaml
    kubectl -n ai rollout restart deploy/hermes

    # Tail logs
    kubectl -n ai logs deploy/hermes -f

## Cluster context

- `thundercracker` (x86_64, no GPU) — Hermes, MCP servers, Jellyfin, general workloads
- `megatron` (DGX Spark GB10, SM12x) — OpenWebUI, Ollama (Qwen3-30B :31434), HAProxy gateway
- `shockwave` (Jetson AGX Thor, SM90) — vLLM-served LLMs (gpt-oss-120b)
- `soundwave` (RTX 4090, control-plane) — k8s control plane, Riva TTS, Nemotron ASR

LLM endpoint Hermes is configured against:
`http://gpt-oss-120b.ai.svc.cluster.local:8000/v1`

MCP services available in-cluster:
- Gmail at `gmail-mcp.ai.svc.cluster.local:8100` (read/send)
- GCal at `gcal-mcp.ai.svc.cluster.local:8200`  (read/create)
- Web search providers are optional; provision keys out of band.

## Skills versioned in this repo

See `skills/`. Each lives under `skills/<category>/<name>/SKILL.md`.
After editing, run `./scripts/sync-to-pod.sh` (or single-skill `tee`
command above) and test inside Hermes with `/<skill-name> <prompt>`.

Current:
- `mlops/vllm-jetson-deploy` — Deploy vLLM on Jetson AGX Thor (shockwave),
  including the standalone device-plugin workaround and per-model
  tool-call parser flags.

## What NOT to do

- Don't `kubectl cp` into the PVC (UID mismatch — see Conventions).
- Don't commit `hermes-secrets.yaml` with real values. The .gitignore
  blocks it; if it ever shows in `git status`, stop and check.
- Don't apply manifests touching the Hermes PVC without
  `nodeSelector: thundercracker` and `strategy: Recreate`.
- Don't run Hermes as root or with capabilities. The Deployment is
  configured with `runAsNonRoot: true` for a reason.
- Upstream Hermes implementation changes belong upstream; no source mirror is included.
