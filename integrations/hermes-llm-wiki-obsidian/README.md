# Hermes LLM Wiki + Obsidian

A Markdown knowledge workflow combining Hermes skills, an Obsidian vault, domain selection, source ingestion, and compiled answers. This integration was imported from `hermes-llm-wiki-obsidian` for Soundwave `2.1.0`; its original license is retained in [LICENSE](LICENSE).

## Contents

- `skills/wiki/` — `/wiki-context`, `/wiki-ingest`, and `/wiki-query` skill instructions.
- `templates/` — schema, navigation, log, and registry examples. These are starting templates, not personal knowledge.
- `scripts/install-wiki.sh` — stream skills to a running Hermes pod without preserving the local UID.
- `scripts/reset-wiki-context.sh` — reset only the active selection using the supplied neutral template.
- `scripts/epub-to-md.py` — standard-library EPUB text extraction in spine order; it is a lightweight text converter, not a full HTML/Markdown renderer.
- [GUIDE.md](GUIDE.md) — longer historical walkthrough and examples. Prefer the commands below for the integrated layout.

## Prerequisites

Deploy and configure [Hermes](../../hermes/README.md) first. You need `kubectl` access to its namespace, a writable Hermes home owned by UID/GID `10000`, and a separately managed vault. Install and configure Obsidian separately; the repository does not include an Obsidian application or vault data.

Set `WIKI_PATH` and `OBSIDIAN_VAULT_PATH` to the same persistent directory in the deployment. The reference value is `/opt/data/wiki`.

## Install

From this directory:

```bash
bash scripts/install-wiki.sh
```

The installer sends the three skills to `/opt/data/skills/wiki` and copies the initial schema/index/log/registry templates only when those files do not exist. It leaves existing vault data intact. It uses `kubectl exec -i` and `tee` so the pod user creates the files; it does not use `kubectl cp`. Review templates before installation. Reopen the Hermes session if needed for skill discovery.

Namespace and paths are configurable:

```bash
NAMESPACE=ai WIKI_PATH=/opt/data/wiki HERMES_HOME=/opt/data bash scripts/install-wiki.sh
```

Use `/wiki-context` to select domains before ingestion or queries. To reset that selection, intentionally replacing only `_registry/active-context.yaml`:

```bash
bash scripts/reset-wiki-context.sh
```

## Convert a local source

```bash
python3 scripts/epub-to-md.py /path/to/your-book.epub /path/to/your-vault/raw/your-book.md
```

Only ingest sources you are entitled to use. Keep original books, internal documents, compiled private notes, active runtime context, and `.obsidian/` settings outside Git. Do not overwrite an existing raw source when choosing the converter output path. The converter does not extract archive paths into the filesystem, but it loads source text into memory, so use trusted reasonably sized EPUBs.
