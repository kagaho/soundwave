# Soundwave

Self-hosted AI infrastructure for a heterogeneous Kubernetes lab: GPU inference, agents, speech, gateways, and MCP integrations.

**Version 1.0.0. Private publication candidate awaiting owner review.** These are reference configurations and experiments, not a turnkey installer. Hardware, container versions, storage, and endpoints must be adapted to your environment.

## Start here

- [Cluster setup](kubernetes-multiarch-install-guide-flannel.md)
- [Gateway setup](HA-Proxy.md)
- [Gmail and Calendar MCP architecture](phase1-multi-agent-deployment.md)
- `deployments/`, `configmap/`, `volumes/` — original manifest examples.

1. Read the component guide and select only the workloads you need.
2. Adapt node selectors, model images, storage paths, network addresses, and resource requirements. Hostnames are illustrative role names.
3. Create credentials outside Git using your secret manager. See [SECURITY.md](SECURITY.md).
4. Review each manifest before applying it. Do not apply an entire directory recursively; it may include archives, debugging pods, or privileged GPU workarounds.

## Reference architecture

| Logical node | Reference hardware | Role |
| --- | --- | --- |
| soundwave | x86_64, RTX 4090 | Control plane and GPU/speech experiments |
| shockwave | ARM64, Jetson AGX Thor | Edge inference |
| megatron | ARM64, DGX Spark | Inference, gateway, UI, and storage experiments |
| thundercracker | x86_64, CPU | Agents, MCP adapters, and utilities |

Clients reach the gateway and UI; inference and MCP services communicate inside the cluster. Historical guides describe different model placements. Their deployment status is not inferred from the repository. LangGraph routing and additional modalities remain design proposals unless a component explicitly implements them.

## Releases and validation

The clean release line is `1.0.0` (legacy), `2.0.0` (rewrite plus security staging), and `2.1.0` (wiki integration). See [CHANGELOG.md](CHANGELOG.md), [release guidance](docs/releases/RELEASING.md), and the [publication checklist](docs/security/public-release-checklist.md).

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/check-release.py
```

Validation checks source structure and security invariants without contacting a cluster. It does not establish runtime compatibility. [Contributions](CONTRIBUTING.md) should document component-specific tests.

## Licensing and attribution

The root license is pending owner selection. Review [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); bundled integrations preserve their license files. This is an independent personal project with no vendor affiliation.
