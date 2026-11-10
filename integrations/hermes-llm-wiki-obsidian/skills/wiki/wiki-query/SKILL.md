---
name: wiki-query
description: Query your Hermes LLM Wiki using the active context.
platforms: [linux, macos, windows]
---

# Wiki Query

Use this skill when the operator asks a question that should be answered from his Hermes LLM Wiki.

## Wiki Path

Use this wiki path:

```text
/opt/data/wiki
```

Important orientation files:

```text
/opt/data/wiki/SCHEMA.md
/opt/data/wiki/index.md
/opt/data/wiki/log.md
/opt/data/wiki/_registry/wiki-registry.yaml
/opt/data/wiki/_registry/active-context.yaml
```

## Required Orientation

Before answering:

1. Read `SCHEMA.md`.
2. Read `index.md`.
3. Read `_registry/active-context.yaml`.
4. If `include: []`, ask the operator to choose a domain using `/wiki-context`.
5. Use only the active domains plus `_shared`.
6. Read relevant compiled pages from:
   - `/opt/data/wiki/domains/<active-domain>/`
   - `/opt/data/wiki/_shared/`

## Rules

- Do not ingest raw files.
- Do not create or modify files unless the operator explicitly asks to save the answer.
- Prefer compiled pages over raw files.
- Only read raw files if the operator explicitly asks or no compiled page exists.
- Cite wiki pages using full vault-relative wikilinks.

Use citation format like:

```text
[[domains/product-manager-learning/book-summary.md]]
[[_shared/concepts/ai-driven-leadership-principles.md]]
```

## Common Commands

```text
/wiki-query what are the PM lessons from The AI-Driven Leader?
/wiki-query compare discovery and execution from the active PM learning notes
/wiki-query what does my example-project wiki say about PRD quality?
```

## Output Style

Answer directly.

At the end, include:

```text
Sources:
- [[path/to/page.md]]
```
