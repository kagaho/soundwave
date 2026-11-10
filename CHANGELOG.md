# Changelog

All entries describe sanitized reference snapshots. No live cluster validation is implied.

## 2.0.0

- Reorganize deployment references and add Hermes, speech tools, and agent experiments.
- Incorporate the original security staging PR: remove Tavily deployment and credentials, dashboard tokens, upstream mirror, and duplicate ASR prototypes.
- Replace personal memories with examples and harden OAuth callback handling and token permissions.
- Add release validation and migration guidance.

## 1.0.0

- Preserve the original Kubernetes, gateway, inference, and Gmail/Calendar MCP design as a sanitized reference.
- Exclude TLS credentials and editor state; add release and security documentation.
