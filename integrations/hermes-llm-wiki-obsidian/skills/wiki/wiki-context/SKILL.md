---
name: wiki-context
description: Select, reset, and inspect the active Hermes LLM Wiki context.
platforms: [linux, macos, windows]
---

# Wiki Context

Use this skill when the operator wants to select which wiki domains are active for the current task, query, project, or ingestion workflow.

## Wiki Path

Use this wiki path:

```text
/opt/data/wiki
```

Important files:

```text
/opt/data/wiki/_registry/wiki-registry.yaml
/opt/data/wiki/_registry/active-context.yaml
/opt/data/wiki/SCHEMA.md
/opt/data/wiki/index.md
/opt/data/wiki/log.md
```

## Behavior

When this skill is used:

1. Read `/opt/data/wiki/_registry/wiki-registry.yaml`.
2. Read `/opt/data/wiki/_registry/active-context.yaml`.
3. If the operator asks to list domains, show all domains from `wiki-registry.yaml` with short descriptions.
4. If the operator asks to activate domains, update only `include:` in `active-context.yaml`.
5. If the operator asks to reset context, set:

```yaml
task: unset
mode: user-selected
include: []
exclude: []
```

6. Do not ingest documents.
7. Do not create compiled wiki pages.
8. Do not modify `SCHEMA.md`, `index.md`, or `log.md` unless the operator explicitly asks.

## Common Commands

```text
/wiki-context list domains
/wiki-context activate product-manager-learning
/wiki-context activate example-project, product-manager-learning
/wiki-context reset
/wiki-context show active
```

## Output Style

Keep the answer short.

When listing domains, use:

```text
Available domains:
- domain-name — description
```

When activating context, confirm:

```text
Active context updated:
- domain-a
- domain-b
```

When reset, confirm:

```text
Active context reset. No domains are currently selected.
```
