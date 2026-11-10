# Deployment catalog

Each file is an independently reviewed Kubernetes example. There is no supported recursive deployment command.

| Folder | Contents | Prerequisites |
| --- | --- | --- |
| `gateway/` | HAProxy configuration and deployment | Reviewed TLS Secret and routing |
| `ui/` | Open WebUI | Storage, backend URLs, authentication |
| `llms/` | vLLM and Ollama examples | Architecture-compatible image, GPU runtime, weights/cache |
| `speech/` | ASR and Riva TTS | NVIDIA access and external NGC Secrets |
| `mcp/` | Gmail and Calendar bridges | Locally generated Google OAuth tokens, separate Secrets |
| `volumes/` | Persistent volume/claim examples | Local host paths, node placement, capacity and ownership |
| `apps/` | Optional services | Component-specific review |
| `archive/` | Historical configurations | Reference only; older versions and privileged GPU workarounds |

Start with [cluster setup](../docs/setup/kubernetes-multiarch-install-guide-flannel.md), [gateway notes](../docs/setup/HA-Proxy.md), and [the MCP architecture](../docs/architecture/phase1-multi-agent-deployment.md). Apply storage and external Secrets before workloads that need them. The `hermes/` and `nanobot/` folders contain their own manifests.

All node names, IPs, host paths, images, and model choices describe a lab reference. Inspect `nodeSelector`, `hostPath`, `hostNetwork`, `privileged`, service exposure, and RBAC before applying a file. The Tavily deployment has been removed; web search is optional and is not a prerequisite for Hermes.

Use `kubectl -n ai rollout status deployment/NAME`, logs, and the component's health endpoint to validate a deployment after an authorized apply. Static CI does not test GPU compatibility or cluster availability.
