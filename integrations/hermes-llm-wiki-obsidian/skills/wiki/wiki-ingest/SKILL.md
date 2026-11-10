---
name: wiki-ingest
description: Ingest raw material into your Hermes LLM Wiki and create compiled Markdown pages.
platforms: [linux, macos, windows]
---

# Wiki Ingest

Use this skill when the operator wants to ingest a source into the Hermes LLM Wiki.

## Wiki Path

Use this wiki path:

```text
/opt/data/wiki
```

Important files:

```text
/opt/data/wiki/SCHEMA.md
/opt/data/wiki/index.md
/opt/data/wiki/log.md
/opt/data/wiki/_registry/wiki-registry.yaml
/opt/data/wiki/_registry/active-context.yaml
```

## Required Orientation

Before ingestion:

1. Read `SCHEMA.md`.
2. Read `index.md`.
3. Read `log.md`.
4. Read `_registry/wiki-registry.yaml`.
5. Read `_registry/active-context.yaml`.
6. If `include: []`, stop and ask the operator to select a domain with `/wiki-context`.
7. Confirm the source path is under `/opt/data/wiki/raw/`.
8. Prefer Markdown or text extractions as input.
9. Do not ingest EPUB, PDF, DOCX, PNG, SVG, or Excalidraw directly unless the operator explicitly asks.

## Source Format Policy

Preferred input:

```text
raw/<project>/markdown/<file>.md
raw/<project>/markdown/<file>.txt
```

Original files stay immutable under:

```text
raw/<project>/ebooks/
raw/<project>/pdfs/
raw/<project>/docx/
raw/<project>/images/
raw/<project>/excalidraw/
raw/<project>/svg/
```

## Ingestion Rules

- Create compiled pages only under active domains:
  - `domains/<active-domain>/`
- Use `_shared/` only for reusable cross-domain concepts.
- Check existing pages before creating new ones.
- Use only tags listed in `SCHEMA.md`.
- If a new tag is needed, ask the operator before adding it, unless the operator explicitly requested auto-tag updates.
- Update `index.md`.
- Append to `log.md`.
- Limit to 5 high-value compiled pages by default unless the operator asks for deep ingestion.
- Do not create dozens of pages from one source unless explicitly requested.

## Common Commands

```text
/wiki-ingest raw/product-manager-learning/markdown/the-ai-driven-leader.md
/wiki-ingest raw/product-manager-learning/markdown/book.md limit 5 pages
/wiki-ingest raw/example-project/markdown/example-prd.md create PRD summary and requirement pages
```

## Output Style

After ingestion, report:

```text
Ingested:
- raw/path/file.md

Created:
- domains/domain/page.md

Updated:
- index.md
- log.md
```
