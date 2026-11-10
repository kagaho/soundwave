# Hermes on Kubernetes

This folder contains Soundwave-specific manifests, optional configuration templates, and skills. Obtain the Hermes Agent implementation separately; it is not vendored here. The deployment references `localhost/hermes-agent:v0.13.0`, an image you must build and make available to the selected node.

## Prerequisites and setup

1. Review [AGENTS.md](AGENTS.md) for storage, ownership, and security constraints.
2. Create namespace `ai`; review the host-local storage path and node selector in `hermes-pvc.yaml`. The `agent-sandbox` claim referenced by the deployment must also exist; its example is in [deployments/volumes](../deployments/volumes/agent-sandbox-pvc.yaml).
3. Copy `hermes-secrets.yaml.example` to the ignored `hermes-secrets.yaml` and fill it locally. Apply the real Secret separately, never commit it.
4. Review and apply the PVC and deployment individually. Keep `strategy: Recreate`, the storage node selector, and nonroot UID/GID `10000` consistent with the volume ownership.
5. Configure the Hermes provider and model endpoint in its persistent runtime home. The deployment starts idle; it does not start a gateway automatically.

```bash
kubectl -n ai apply -f hermes-pvc.yaml
kubectl -n ai apply -f hermes-secrets.yaml
kubectl -n ai apply -f hermes-deploy.yaml
kubectl -n ai rollout status deployment/hermes
```

Run these from this folder after adapting the manifests. No build recipe for the local image is supplied, so this is not a complete installer.

## Configuration and skills

`hermes-config/memories/*.example` are optional blank examples. Actual `USER.md` and `MEMORY.md` must remain local and are excluded from Git and workspace sync. Do not overwrite an existing agent's memories with examples.

Use `bash scripts/sync-to-pod.sh` to copy tracked reference files into the pod workspace. The script sends only tracked files, excluding secrets, memories, scripts, and upstream source. It does not install active skills or restart workloads. For active skills, stream reviewed content with `kubectl exec -i ... -- tee` as documented in `AGENTS.md`; avoid `kubectl cp` because it can preserve incompatible UIDs.

The wiki integration in version 2.1 provides a separate installer under `integrations/`.
