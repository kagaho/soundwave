#!/usr/bin/env bash
# Intentionally replaces only the current active selection with the neutral template.
set -euo pipefail
NAMESPACE="${NAMESPACE:-ai}"
APP_LABEL="${APP_LABEL:-app=hermes}"
WIKI_PATH="${WIKI_PATH:-/opt/data/wiki}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ "$WIKI_PATH" == /* && "$WIKI_PATH" != / ]] || { echo "WIKI_PATH must be an absolute non-root path" >&2; exit 1; }
POD="$(kubectl -n "$NAMESPACE" get pod -l "$APP_LABEL" -o jsonpath='{.items[0].metadata.name}')"
[[ -n "$POD" ]] || { echo "No Hermes pod found" >&2; exit 1; }
kubectl -n "$NAMESPACE" exec "$POD" -- mkdir -p "$WIKI_PATH/_registry"
kubectl -n "$NAMESPACE" exec -i "$POD" -- tee "$WIKI_PATH/_registry/active-context.yaml" \
  < "$SCRIPT_DIR/../templates/active-context.yaml" > /dev/null
echo "Active wiki selection reset in $POD"
