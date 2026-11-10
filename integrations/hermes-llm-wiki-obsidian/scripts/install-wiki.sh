#!/usr/bin/env bash
set -euo pipefail
NAMESPACE="${NAMESPACE:-ai}"
APP_LABEL="${APP_LABEL:-app=hermes}"
WIKI_PATH="${WIKI_PATH:-/opt/data/wiki}"
HERMES_HOME="${HERMES_HOME:-/opt/data}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for directory in "$WIKI_PATH" "$HERMES_HOME"; do
  [[ "$directory" == /* && "$directory" != / ]] || { echo "Runtime directories must be absolute non-root paths" >&2; exit 1; }
done
POD="$(kubectl -n "$NAMESPACE" get pod -l "$APP_LABEL" -o jsonpath='{.items[0].metadata.name}')"
[[ -n "$POD" ]] || { echo "No Hermes pod found" >&2; exit 1; }
copy_file() {
  local source="$1" destination="$2"
  kubectl -n "$NAMESPACE" exec "$POD" -- mkdir -p "$(dirname "$destination")"
  kubectl -n "$NAMESPACE" exec -i "$POD" -- tee "$destination" < "$source" > /dev/null
}
for skill in wiki-context wiki-ingest wiki-query; do
  copy_file "$SOURCE_DIR/skills/wiki/$skill/SKILL.md" "$HERMES_HOME/skills/wiki/$skill/SKILL.md"
done
for relative in SCHEMA.md index.md log.md _registry/active-context.yaml _registry/wiki-registry.yaml; do
  destination="$WIKI_PATH/$relative"
  kubectl -n "$NAMESPACE" exec "$POD" -- mkdir -p "$(dirname "$destination")"
  # noclobber creates new template files and leaves existing files untouched.
  # Positional args keep paths out of shell source.
  kubectl -n "$NAMESPACE" exec -i "$POD" -- sh -c \
    'if [ -e "$1" ]; then cat >/dev/null; else (set -C; cat >"$1"); fi' sh "$destination" \
    < "$SOURCE_DIR/templates/$(basename "$relative")"
done
echo "Wiki skills installed and missing templates initialized in $POD"
