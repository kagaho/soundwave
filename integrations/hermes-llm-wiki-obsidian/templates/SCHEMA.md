# Wiki Schema

## Domain

This is your federated Hermes LLM Wiki and Obsidian vault.

It is organized as one Obsidian vault with multiple domain wikis selected through `_registry/active-context.yaml`.

Primary domains:

- AI infrastructure
- Elita / Perceptor / Energon
- OpenStack / Kubernetes / GPU infrastructure
- Palo Alto Networks documentation and command knowledge
- Terraform / Ansible labs
- Personal learning

## Operating Model

This wiki uses a federated single-vault model.

The root-level folders hold shared wiki infrastructure:

- `_registry/` stores domain registry and active context selection.
- `_shared/` stores cross-domain concepts, entities, glossary pages, and reusable notes.
- `raw/` stores immutable source material.
- `entities/`, `concepts/`, `comparisons/`, and `queries/` store global compiled pages.
- `domains/` stores domain-specific compiled knowledge.

Before any wiki work, Hermes must read:

1. `SCHEMA.md`
2. `index.md`
3. `log.md`
4. `_registry/wiki-registry.yaml`
5. `_registry/active-context.yaml`

Hermes should only use the domains listed under `include:` in `_registry/active-context.yaml`, unless the operator explicitly asks to expand scope.

## Folder Rules

Domain-specific pages go under:

- `domains/ai-infrastructure/`
- `domains/elita-perceptor-energon/`
- `domains/openstack-kubernetes-gpu/`
- `domains/palo-alto-docs/`
- `domains/terraform-ansible-labs/`
- `domains/personal-learning/`

Cross-domain reusable pages go under:

- `_shared/`

Raw source material goes under:

- `raw/articles/`
- `raw/papers/`
- `raw/transcripts/`
- `raw/assets/`

Raw files are immutable. Do not edit raw files after ingestion. Corrections and synthesis belong in compiled wiki pages.

## Naming Conventions

- File names use lowercase kebab-case.
- No spaces in filenames.
- Use Obsidian wikilinks: `[[page-name]]`.
- Prefer descriptive names over short names.
- Domain pages may use prefixes when useful, for example:
  - `elita-slack-thread-routing.md`
  - `k8s-nvidia-runtimeclass.md`
  - `vllm-serving-patterns.md`

## Frontmatter

Every compiled wiki page should start with this frontmatter:

~~~yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query | summary | runbook | decision | architecture
domain: ai-infrastructure | elita-perceptor-energon | openstack-kubernetes-gpu | palo-alto-docs | terraform-ansible-labs | personal-learning | shared
tags: []
sources: []
confidence: high | medium | low
status: draft | reviewed | stale | contested
---
~~~

## Tag Taxonomy

Core tags:

- ai-infra
- gpu
- inference
- llm-serving
- ai-factory
- scaling
- elita
- perceptor
- energon
- rag
- slack
- langgraph
- agentic-ai
- openstack
- kubernetes
- nvidia
- containerd
- helm
- infra-debug
- palo-alto
- pan-os
- panorama
- prisma
- firewall
- networking
- terraform
- ansible
- iac
- automation
- labs
- learning
- study-plan
- certifications
- career
- shared
- glossary
- architecture
- runbook
- decision

New tags must be added here before use.

## Page Creation Rules

Create a page when:

- The topic is central to a source or task.
- The topic appears across multiple sources.
- The answer would be painful to re-derive later.
- The page supports an ongoing project, architecture, runbook, or decision.

Do not create a page for:

- Passing mentions.
- One-off shell output unless it supports a reusable runbook.
- Temporary debugging noise.
- Content outside the active context unless the operator asks for it.

## Cross-Domain Rules

If a concept applies to two or more domains, prefer `_shared/`.

Examples:

- `vllm.md`
- `rag.md`
- `kubernetes.md`
- `gpu-scheduling.md`
- `agentic-memory.md`

Domain pages can link to shared pages.

## Update Policy

When new information conflicts with existing content:

1. Check dates and source quality.
2. Keep both positions if the contradiction is real.
3. Mark the page as `status: contested`.
4. Add `confidence: low` or `medium`.
5. Log the contradiction in `log.md`.

## Index Policy

Every compiled page must be listed in `index.md`.

Keep entries short:

~~~markdown
- [[page-name]] — one-line summary.
~~~

## Logging Policy

Every meaningful wiki action must append to `log.md`.

Format:

~~~markdown
## [YYYY-MM-DD] action | subject
- Created:
- Updated:
- Notes:
~~~

Actions:

- create
- ingest
- update
- query
- lint
- archive
- decision
