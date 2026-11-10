# Third-party notices

Soundwave integrates independently licensed services and model runtimes. The project license does not grant rights to their source, weights, container images, documentation, or trademarks.

- **Hermes Agent:** Nous Research; the original local mirror identifies the upstream license as MIT. Upstream implementation is intentionally excluded from the sanitized releases. The supplied Kubernetes example references a locally built image; obtain and build a separately reviewed upstream version. Project-specific skills and manifests live in `hermes/`.
- **Hermes LLM Wiki + Obsidian:** bundled starting at `2.1.0` in `integrations/hermes-llm-wiki-obsidian/`. Preserve its original `LICENSE` and copyright. The source license text is incomplete compared with the standard MIT text; obtain owner approval of a complete license before publication.
- **Kubernetes, NVIDIA runtimes, HAProxy, Open WebUI, MCP servers, model backends, Obsidian, and other referenced tools:** install separately and review their own licenses and model terms.
- **Artwork and screenshots in `assets/`:** inherited from the original project. Ownership and permission to redistribute must be reviewed by the owner. Character names and imagery may involve third-party rights; no endorsement is claimed.

The top-level license, when selected, applies only to the maintainer's original contributions and does not replace third-party notices.
