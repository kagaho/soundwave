# Hermes LLM Wiki + Obsidian Guide

A practical guide for your Hermes-powered LLM Wiki running inside Kubernetes and using Obsidian as the Markdown vault.

---

## 1. What this project is

This setup combines:

- **Hermes Agent** — the AI agent running in Kubernetes.
- **LLM Wiki** — the structured knowledge architecture inspired by Andrej Karpathy's LLM Wiki idea.
- **Obsidian** — the Markdown vault and visual note interface.
- **Kubernetes** — the runtime where Hermes runs as a pod.
- **Raw source preservation** — original files are kept untouched under `raw/`.

The main wiki path is:

```text
/opt/data/wiki
```

This path is both:

```text
Obsidian vault
+
LLM Wiki storage
```

---

## 2. Mental model

```text
Hermes = the agent
Obsidian = the Markdown vault / note UI
LLM Wiki = the knowledge structure and workflow
```

They are related, but not the same thing.

### Obsidian

Obsidian is the place where Markdown notes live. It gives you:

- folders
- Markdown files
- wikilinks
- graph view
- tags
- manual browsing
- manual editing

### LLM Wiki

LLM Wiki is the structured process Hermes follows:

```text
raw/        = original source files and extracted Markdown
domains/    = Hermes-created compiled knowledge pages
_shared/    = reusable concepts shared across domains
SCHEMA.md   = wiki rules
index.md    = navigation/catalog
log.md      = audit trail
_registry/  = domain registry and active context
```

### Hermes

Hermes is the maintainer. It reads sources, creates compiled pages, updates the index, and keeps the log.

---

## 3. `/obsidian` vs `/wiki-*`

### `/obsidian`

`/obsidian` is the Hermes skill for direct Obsidian vault work.

It can:

```text
read notes
search notes
create notes
edit notes
append content
add wikilinks
```

It is the lower-level file/note tool.

Example:

```text
/obsidian read this note /opt/data/wiki/_shared/concepts/ai-driven-leadership-principles.md and tell me how many chapters are there
```

Then you can continue:

```text
can you explain to me the first chapter?
chapter 2 now
chapter 3 now
```

This is useful for reading and brainstorming around one specific note.

### `/wiki-context`

Used to select which wiki domains are active.

Examples:

```text
/wiki-context list domains
/wiki-context show active
/wiki-context activate product-manager-learning
/wiki-context activate product-manager-learning, example-project
/wiki-context reset
```

### `/wiki-ingest`

Used to ingest raw Markdown/text sources into the compiled LLM Wiki.

Example:

```text
/wiki-ingest raw/product-manager-learning/markdown/the-ai-driven-leader.md
```

### `/wiki-query`

Used to ask questions from the compiled wiki knowledge.

Example:

```text
/wiki-query what are the PM lessons from The AI-Driven Leader?
```

### Simple rule

```text
/obsidian    = direct note reading/editing
/wiki-query  = ask questions from compiled knowledge
/wiki-ingest = create compiled knowledge from raw sources
/wiki-context = select active domains/projects
```

---

## 4. Kubernetes / Hermes environment

Hermes runs in namespace:

```text
ai
```

Get the Hermes pod:

```bash
POD=$(kubectl -n ai get pod -l app=hermes -o jsonpath='{.items[0].metadata.name}')
echo "$POD"
```

Hermes command:

```bash
kubectl -n ai exec -it deploy/hermes -- /opt/hermes/.venv/bin/hermes
```

The important environment variables are:

```text
WIKI_PATH=/opt/data/wiki
OBSIDIAN_VAULT_PATH=/opt/data/wiki
```

Patch them into the deployment:

```bash
kubectl -n ai set env deployment/hermes \
  WIKI_PATH=/opt/data/wiki \
  OBSIDIAN_VAULT_PATH=/opt/data/wiki
```

Restart:

```bash
kubectl -n ai rollout restart deployment/hermes
kubectl -n ai rollout status deployment/hermes
```

Verify:

```bash
POD=$(kubectl -n ai get pod -l app=hermes -o jsonpath='{.items[0].metadata.name}')

kubectl -n ai exec -it "$POD" -- bash -lc '
echo "WIKI_PATH=$WIKI_PATH"
echo "OBSIDIAN_VAULT_PATH=$OBSIDIAN_VAULT_PATH"
ls -la "$WIKI_PATH"
'
```

---

## 5. Wiki folder layout

Recommended structure:

```text
/opt/data/wiki/
├── SCHEMA.md
├── index.md
├── log.md
├── _registry/
│   ├── active-context.yaml
│   └── wiki-registry.yaml
├── _shared/
├── raw/
│   ├── product-manager-learning/
│   │   ├── ebooks/
│   │   ├── pdfs/
│   │   ├── docx/
│   │   ├── images/
│   │   ├── excalidraw/
│   │   ├── svg/
│   │   └── markdown/
│   └── example-project/
│       ├── prds/
│       ├── docx/
│       ├── pdfs/
│       ├── images/
│       ├── excalidraw/
│       ├── svg/
│       └── markdown/
└── domains/
    ├── product-manager-learning/
    └── example-project/
```

---

## 6. Raw vs domains

### `raw/`

This is where original files go.

Examples:

```text
raw/product-manager-learning/ebooks/The AI-Driven Leader.epub
raw/product-manager-learning/pdfs/some-book.pdf
raw/example-project/docx/example-prd.docx
raw/example-project/images/product-diagram.png
```

Rule:

```text
Do not edit raw files.
```

### `domains/`

This is where Hermes creates compiled Markdown pages.

Examples:

```text
domains/product-manager-learning/book-summary.md
domains/product-manager-learning/key-product-management-concepts.md
domains/product-manager-learning/multi-agent-systems-summary.md
domains/product-manager-learning/ai-driven-leadership-vs-multi-agent-systems-for-product-managers.md
```

### `_shared/`

This is where reusable cross-domain concepts go.

Example:

```text
_shared/concepts/ai-driven-leadership-principles.md
```

---

## 7. Domain registry

The domain registry is permanent:

```text
/opt/data/wiki/_registry/wiki-registry.yaml
```

Example domains:

```yaml
domains:
  product-manager-learning:
    path: domains/product-manager-learning
    description: Product management learning materials, books, ebooks, frameworks, notes, diagrams, and study material.
    tags: [product-management, pm-learning, books, frameworks, strategy, discovery, execution]

  example-project:
    path: domains/example-project
    description: Product management work related to PANW, including PRDs, product docs, diagrams, planning material, and internal product thinking.
    tags: [product-management, example-team, prd, product-strategy, roadmap, execution, requirements]
```

The active context is temporary:

```text
/opt/data/wiki/_registry/active-context.yaml
```

Neutral/default state:

```yaml
task: unset

mode: user-selected

include: []

exclude: []

agent_stack:
  primary: hermes
  future:
    - openhands
```

When the active context is empty, Hermes should list domains and ask which one to activate.

Example active state:

```yaml
include:
  - product-manager-learning
```

---

## 8. Reset active context

Create a script called:

```text
scripts/reset-wiki-context.sh
```

Content:

```bash
#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-ai}"
APP_LABEL="${APP_LABEL:-app=hermes}"
ACTIVE_CONTEXT_PATH="${ACTIVE_CONTEXT_PATH:-/opt/data/wiki/_registry/active-context.yaml}"

POD=$(kubectl -n "$NAMESPACE" get pod -l "$APP_LABEL" -o jsonpath='{.items[0].metadata.name}')

if [[ -z "$POD" ]]; then
  echo "No Hermes pod found with label: $APP_LABEL"
  exit 1
fi

echo "Using pod: $POD"
echo "Resetting: $ACTIVE_CONTEXT_PATH"

kubectl -n "$NAMESPACE" exec "$POD" -- bash -lc "cat > '$ACTIVE_CONTEXT_PATH' <<'EOF'
# Hermes Active Wiki Context
# This file is temporary and should be updated per task/query/project.

task: unset

mode: user-selected

include: []

exclude: []

agent_stack:
  primary: hermes
  future:
    - openhands

selection_policy:
  - Before wiki work, read _registry/wiki-registry.yaml.
  - Present the available domains to the operator when no active context is selected.
  - Ask the operator which domains should be included for the current task.
  - Update this file with the selected domains.
  - Use only included domains unless the operator explicitly expands scope.
  - If include is empty, do not assume a domain automatically.

instructions:
  - Read this file before wiki work.
  - If include is empty, list available domains from wiki-registry.yaml and ask the operator to choose.
  - Prefer _shared for concepts used by more than one selected domain.
  - Do not create duplicate entity or concept pages across domains without checking _shared first.
EOF"

echo
echo "Current active context:"
kubectl -n "$NAMESPACE" exec "$POD" -- cat "$ACTIVE_CONTEXT_PATH"
```

Make executable:

```bash
chmod +x scripts/reset-wiki-context.sh
```

Run:

```bash
scripts/reset-wiki-context.sh
```

---

## 9. Custom Hermes wiki skills

The custom skills live under:

```text
/opt/data/skills/wiki/
```

Expected structure:

```text
/opt/data/skills/wiki/
├── wiki-context/
│   └── SKILL.md
├── wiki-ingest/
│   └── SKILL.md
└── wiki-query/
    └── SKILL.md
```

Install:

```bash
POD=$(kubectl -n ai get pod -l app=hermes -o jsonpath='{.items[0].metadata.name}')

bash scripts/install-wiki.sh

kubectl -n ai rollout restart deployment/hermes
kubectl -n ai rollout status deployment/hermes
```

Open Hermes:

```bash
kubectl -n ai exec -it deploy/hermes -- /opt/hermes/.venv/bin/hermes
```

Test:

```text
/wiki
```

Expected:

```text
/wiki-context
/wiki-ingest
/wiki-query
```

---

## 10. Ebook ingestion flow

### Step 1: put EPUB in raw folder

Example:

```text
/opt/data/wiki/raw/product-manager-learning/ebooks/The AI-Driven Leader.epub
/opt/data/wiki/raw/product-manager-learning/ebooks/multi-agent-systems.epub
```

### Step 2: convert EPUB to Markdown

Hermes pod currently has Python:

```bash
kubectl -n ai exec -it "$POD" -- bash -lc 'which python3'
```

Create this converter:

```text
/opt/data/bin/epub-to-md.py
```

Then run:

```bash
kubectl -n ai exec -it "$POD" -- bash -lc '
mkdir -p /opt/data/wiki/raw/product-manager-learning/markdown

/opt/data/bin/epub-to-md.py \
  "/opt/data/wiki/raw/product-manager-learning/ebooks/The AI-Driven Leader.epub" \
  "/opt/data/wiki/raw/product-manager-learning/markdown/the-ai-driven-leader.md"

ls -lh /opt/data/wiki/raw/product-manager-learning/markdown/the-ai-driven-leader.md
'
```

Preview:

```bash
kubectl -n ai exec -it "$POD" -- bash -lc '
sed -n "1,120p" /opt/data/wiki/raw/product-manager-learning/markdown/the-ai-driven-leader.md"
'
```

Check headings:

```bash
kubectl -n ai exec -it "$POD" -- bash -lc '
grep -n "^#" /opt/data/wiki/raw/product-manager-learning/markdown/the-ai-driven-leader.md | head -80
'
```

### Step 3: activate domain

Inside Hermes:

```text
/wiki-context activate product-manager-learning
```

### Step 4: ingest Markdown

Inside Hermes:

```text
/wiki-ingest raw/product-manager-learning/markdown/the-ai-driven-leader.md
```

Controlled ingestion:

```text
/wiki-ingest raw/product-manager-learning/markdown/designing-multi-agent-systems.md limit 5 pages. Focus on product-management lessons, multi-agent system design principles, coordination patterns, evaluation, and implications for PMs.
```

---

## 11. Tested ingestion results

### The AI-Driven Leader

Raw source:

```text
raw/product-manager-learning/markdown/the-ai-driven-leader.md
```

Created:

```text
domains/product-manager-learning/book-summary.md
domains/product-manager-learning/key-product-management-concepts.md
_shared/concepts/ai-driven-leadership-principles.md
```

### Designing Multi-Agent Systems

Raw source:

```text
raw/product-manager-learning/markdown/designing-multi-agent-systems.md
```

Created:

```text
domains/product-manager-learning/multi-agent-systems-summary.md
```

Then a comparison query was saved as:

```text
domains/product-manager-learning/ai-driven-leadership-vs-multi-agent-systems-for-product-managers.md
```

---

## 12. Query examples

Ask from compiled wiki pages:

```text
/wiki-query what are the most useful lessons from The AI-Driven Leader for someone moving into product management?
```

Compare two books:

```text
/wiki-query compare the lessons from The AI-Driven Leader and Designing Multi-Agent Systems for a product manager building AI products
```

Save a useful answer:

```text
Save this answer as a comparison page under domains/product-manager-learning. Name it ai-driven-leadership-vs-multi-agent-systems-for-product-managers.md. Add proper frontmatter, use tags from SCHEMA.md, update index.md and log.md.
```

---

## 13. Obsidian example

This is the direct `/obsidian` flow.

Command:

```text
/obsidian read this note /opt/data/wiki/_shared/concepts/ai-driven-leadership-principles.md and tell me how many chapters are there
```

Hermes answered that the note contained five numbered principles.

Then follow-up questions:

```text
can you explain to me the first chapter?
chapter 2 now
chapter 3 now
chapter 4 now
chapter 5
```

Hermes explained each principle:

1. Treat AI as a Thought Partner
2. Data-to-Decision Speed
3. Bias Mitigation
4. Strategic Alignment
5. Iterative Learning

Then save the session:

```text
/title obsidian brainstorm on the 5 principles of AI Driven Leadership - ai-driven-leadership-principles.md
/save
```

Saved session path example:

```text
/opt/data/sessions/saved/hermes_conversation_20260528_090032.json
```

---

## 14. Recommended daily workflow

### For PM learning books

```text
/wiki-context activate product-manager-learning
/wiki-ingest raw/product-manager-learning/markdown/<book>.md
/wiki-query what are the most useful lessons from this book for product management?
```

Then save valuable synthesis:

```text
Save this answer as a compiled page under domains/product-manager-learning. Update index.md and log.md.
```

### For PM/PANW PRDs

```text
/wiki-context activate example-project
/wiki-ingest raw/example-project/markdown/<prd>.md
/wiki-query summarize the customer problem, goals, non-goals, risks, dependencies, and open questions from this PRD
```

### For reading one note interactively

```text
/obsidian read this note /opt/data/wiki/path/to/note.md
```

---

## 15. Troubleshooting

### `kubectl cp deploy/hermes` fails

Use the actual pod name:

```bash
POD=$(kubectl -n ai get pod -l app=hermes -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai cp local-file "$POD":/remote/path
```

### `/wiki-*` commands do not appear

Restart Hermes:

```bash
kubectl -n ai rollout restart deployment/hermes
kubectl -n ai rollout status deployment/hermes
```

Then open Hermes and type:

```text
/wiki
```

### Active context is stale

Reset:

```bash
scripts/reset-wiki-context.sh
```

Or inside Hermes:

```text
/wiki-context reset
```

### EPUB extraction has noisy headings

Check:

```bash
grep -n "^#" /opt/data/wiki/raw/product-manager-learning/markdown/<book>.md | head -80
```

Some noisy quote-only headings are acceptable if the main structure is readable.

### Hermes `/new` behaves oddly

Exit and restart Hermes instead:

```text
/exit
```

Then:

```bash
kubectl -n ai exec -it deploy/hermes -- /opt/hermes/.venv/bin/hermes
```

---

## 16. Practical summary

Use this mental model:

```text
raw/      = originals and extracted source text
domains/  = compiled wiki knowledge
_shared/  = reusable cross-domain concepts
/obsidian = direct note/file interaction
/wiki-*   = structured LLM Wiki workflow
```

Best loop:

```text
copy source → convert to Markdown → /wiki-context activate domain → /wiki-ingest → /wiki-query → save valuable synthesis
```
