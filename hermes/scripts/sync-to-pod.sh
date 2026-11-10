#!/usr/bin/env bash
# Copy only reviewed, tracked reference files; no private runtime configuration.
set -euo pipefail
NS="${NS:-ai}"
LABEL="${LABEL:-app=hermes}"
WORKSPACE="${WORKSPACE:-/opt/data/workspace/soundwave-hermes}"
HERMES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POD="$(kubectl -n "$NS" get pod -l "$LABEL" -o jsonpath='{.items[0].metadata.name}')"
[[ -n "$POD" ]] || { echo "No Hermes pod found" >&2; exit 1; }
[[ "$WORKSPACE" == /* && "$WORKSPACE" != / ]] || { echo "WORKSPACE must be an absolute non-root directory" >&2; exit 1; }
kubectl -n "$NS" exec "$POD" -- mkdir -p "$WORKSPACE"
git -C "$HERMES_DIR" ls-files -z -- . ':!:src/**' ':!:scripts/**' ':!:hermes-secrets.yaml' ':!:hermes-config/memories/USER.md' ':!:hermes-config/memories/MEMORY.md' |
  tar --null --verbatim-files-from --no-recursion -C "$HERMES_DIR" -T - -cf - |
  kubectl -n "$NS" exec -i "$POD" -- tar -xf - -C "$WORKSPACE" --no-same-owner
echo "Tracked reference files synced to $POD:$WORKSPACE"
