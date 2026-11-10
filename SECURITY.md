# Security policy

Soundwave is a self-hosted AI infrastructure reference. Deployment examples require review for your hardware and network.

## Reporting a vulnerability

Use GitHub private vulnerability reporting when enabled, or a private channel to the maintainer. Do not post credentials or exploit details in public issues.

## Credentials

- Provision live Kubernetes Secrets outside Git. Only placeholder templates belong here.
- Keep OAuth files, `.env` files, TLS keys, kubeconfigs, agent memory, and wiki sources local.
- A deleted credential remains exposed in earlier commits. Revoke or rotate exposed credentials at the issuer; deleting or sanitizing Git content does not revoke them.
- Use a fresh reviewed repository for this publication. The original private repositories retain sensitive historical data and must remain private.
- Keep model APIs, MCP services, and dashboards on a trusted network behind authentication. A NodePort or a TLS certificate alone does not provide authorization.
- Review `privileged`, host networking, host paths, GPU access, and RBAC before applying any manifest. Historical GPU workarounds can grant broad host access.

## Support

No version currently has a promised security maintenance window. Tags preserve reference snapshots, not a production support guarantee. Report issues against the current main branch.
