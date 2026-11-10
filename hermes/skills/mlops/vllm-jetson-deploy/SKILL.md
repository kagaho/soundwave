---
name: vllm-jetson-deploy
description: Deploy a vLLM-served LLM on Jetson AGX Thor (shockwave) via Kubernetes — covers the gpu-operator workaround, the standalone device-plugin pattern, and per-model-family tool-call parser flags.
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [k8s, vllm, jetson, gpu, soundwave, nvidia, inference]
    category: mlops
---

# Deploy vLLM on Jetson AGX Thor (Soundwave shockwave)

## When to Use

Deploying any vLLM-served model on the `shockwave` Jetson AGX Thor node in
the Soundwave cluster. Covers the device-plugin gotcha that breaks the
default NVIDIA gpu-operator path on this hardware.

Does **not** cover DGX Spark (`megatron`) — that's a different SM family
(GB10/SM12x) with different constraints. Make a separate skill if needed.

## Background

The NVIDIA gpu-operator's bundled `nvidia-container-toolkit-daemonset` and
`nvidia-device-plugin-daemonset` get stuck in `Init` forever on Thor because
the L4T/JetPack base image has firmware-baked drivers — the operator's
init containers can't reconcile against it.

The fix: bypass the operator entirely on shockwave with a standalone,
privileged `k8s-device-plugin` DaemonSet pinned via nodeSelector. The
operator's daemonsets remain Init-blocked on shockwave; they're harmless
as long as nothing schedules onto them.

## Procedure

### 1. Verify the device plugin DaemonSet exists

It should already be deployed at `kube-system/nvidia-device-plugin-shockwave`.
Check:

    kubectl -n kube-system get ds nvidia-device-plugin-shockwave

If missing, apply this manifest:

    apiVersion: apps/v1
    kind: DaemonSet
    metadata:
      name: nvidia-device-plugin-shockwave
      namespace: kube-system
    spec:
      selector:
        matchLabels: {app: nvidia-device-plugin-shockwave}
      template:
        metadata:
          labels: {app: nvidia-device-plugin-shockwave}
        spec:
          nodeSelector:
            kubernetes.io/hostname: shockwave
          priorityClassName: system-node-critical
          containers:
            - name: nvidia-device-plugin
              image: nvcr.io/nvidia/k8s-device-plugin:v0.17.0
              securityContext:
                privileged: true
              volumeMounts:
                - name: device-plugin
                  mountPath: /var/lib/kubelet/device-plugins
          volumes:
            - name: device-plugin
              hostPath:
                path: /var/lib/kubelet/device-plugins

### 2. Verify GPU resource is exposed

    kubectl describe node shockwave | grep -A2 'Allocatable:'

Should show `nvidia.com/gpu: 1`. If not, the device plugin pod failed to
register — check `kubectl -n kube-system logs ds/nvidia-device-plugin-shockwave`.

### 3. Deploy the vLLM workload

Reference Deployment for gpt-oss-120b (working, deployed 2026-03-27):

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: gpt-oss-120b
      namespace: ai
    spec:
      replicas: 1
      selector:
        matchLabels: {app: gpt-oss-120b}
      template:
        metadata:
          labels: {app: gpt-oss-120b}
        spec:
          nodeSelector:
            kubernetes.io/hostname: shockwave
          hostNetwork: true
          containers:
            - name: vllm
              image: ghcr.io/nvidia-ai-iot/vllm:latest-jetson-thor
              imagePullPolicy: IfNotPresent
              command: ["vllm"]
              args:
                - serve
                - openai/gpt-oss-120b
                - --gpu-memory-utilization
                - "0.8"
                # See "Tool calling" section below for per-model parser flags
              env:
                - name: TIKTOKEN_ENCODINGS_BASE
                  value: /etc/encodings
              ports:
                - {name: http, containerPort: 8000}
              resources:
                limits:
                  nvidia.com/gpu: "1"
              volumeMounts:
                - {name: huggingface-cache, mountPath: /root/.cache/huggingface}
                - {name: tiktoken-cache,    mountPath: /etc/encodings}
          volumes:
            - name: huggingface-cache
              hostPath:
                # WARNING: this path is host-user-specific. Replace with a
                # neutral location (e.g., /opt/hf-cache) for portability, or
                # use a PVC backed by your node's local storage.
                path: /home/operator/.cache/huggingface
                type: Directory
            - name: tiktoken-cache
              hostPath:
                path: /home/operator/.cache/tiktoken
                type: Directory

### 4. Tool calling — choose parser by model family

vLLM does **not** auto-detect tool-call formats. The flag depends on the
model family:

| Model family            | Required vLLM flags                                          |
|-------------------------|--------------------------------------------------------------|
| gpt-oss (harmony)       | `--enable-auto-tool-choice --tool-call-parser openai`        |
| Qwen3-Coder             | `--enable-auto-tool-choice --tool-call-parser qwen3_coder`   |
| Qwen3 (other variants)  | `--enable-auto-tool-choice --tool-call-parser qwen3_xml` or `hermes` |
| Nous Hermes models      | `--enable-auto-tool-choice --tool-call-parser hermes`        |
| Llama 3.x Instruct      | `--enable-auto-tool-choice --tool-call-parser llama3_json`   |
| Llama 4                 | `--enable-auto-tool-choice --tool-call-parser llama4_json` or `llama4_pythonic` |
| Mistral / Mixtral       | `--enable-auto-tool-choice --tool-call-parser mistral`       |
| DeepSeek V3.x           | `--enable-auto-tool-choice --tool-call-parser deepseek_v32`  |
| GLM 4.5 / 4.7           | `--enable-auto-tool-choice --tool-call-parser glm45` (or `glm47`) |

To list all parsers supported by your specific vLLM build:

    kubectl -n ai exec deploy/<vllm-deploy> -- vllm serve --help=Frontend 2>&1 | grep tool-call-parser


Without these flags, vLLM still serves the model, and the model still
*generates* tool calls in its training format — but vLLM drops them
and returns `tool_calls: []` to the OpenAI API. Clients like Hermes
Agent that parse raw output may still work; clients using the OpenAI
SDK strictly will not.

The current gpt-oss-120b deploy intentionally omits these flags (Hermes
parses raw output). If you add an OpenAI-SDK client (e.g., direct
LangChain or OpenAI SDK), add `--enable-auto-tool-choice --tool-call-parser openai`.

### 5. Expose the service

    apiVersion: v1
    kind: Service
    metadata:
      name: gpt-oss-120b
      namespace: ai
    spec:
      selector: {app: gpt-oss-120b}
      ports:
        - {port: 8000, targetPort: 8000, name: http}

Reachable in-cluster at `gpt-oss-120b.ai.svc.cluster.local:8000`.

## Pitfalls

- **Don't try to "fix" the gpu-operator daemonsets on shockwave.** The two
  pods (`nvidia-container-toolkit-daemonset-*` and `nvidia-device-plugin-daemonset-*`)
  on shockwave will remain `Init:0/1` and `Init:0/2` forever. They are
  expected casualties. Trying to force them to run risks breaking the
  GPU on the other nodes (megatron, soundwave) where they work fine.

- **`*.svc.cluster.local` does not resolve from the host.** Test endpoints
  from inside a pod (`kubectl exec`), not from the cluster node shell.

- **gpt-oss models need tiktoken encodings pre-cached.** The
  `TIKTOKEN_ENCODINGS_BASE` env + `/etc/encodings` mount is mandatory for
  gpt-oss specifically. Other model families don't need this.

- **Thor is SM90, GB10/DGX Spark is SM12x.** Models requiring FlashMLA
  kernels (e.g., GLM-4.5+ MoE) need SM100/SM90 — work on Thor in theory
  but not on DGX Spark. Verify kernel requirements before assuming a
  model will run.

- **No readiness/liveness probes by design.** Thor cold start for a 120B
  MoE is several minutes. A naive probe will kill the pod before it loads.
  If you must add probes, set `initialDelaySeconds: 600`+ and use
  `httpGet: /v1/models`.

- **`hostNetwork: true` is used here** so the pod can hit external HF
  mirrors at full speed during model download. Removable once the HF
  cache is warm.

- **HostPath cache dirs are user-specific.** The reference Deployment mounts
  `/home/operator/.cache/{huggingface,tiktoken}` from the host. This works
  because the shockwave node has these directories pre-populated. When
  porting to a new node or sharing the manifest, change to a neutral path
  (e.g., `/opt/hf-cache`) or migrate to a PVC. `type: Directory` (not
  `DirectoryOrCreate`) means the path must exist before the pod schedules.

## Disabling gpu-operator daemonsets on Thor

The gpu-operator's `container-toolkit` and `device-plugin` daemonsets get
stuck in `Init:0/x` forever on Thor (firmware-baked drivers conflict with
the operator's init containers). To stop the operator from trying to
schedule them on shockwave, set the deployment labels to `false`:

    kubectl label node shockwave \
      nvidia.com/gpu.deploy.container-toolkit=false \
      nvidia.com/gpu.deploy.device-plugin=false \
      --overwrite

After ~30s the stuck pods on shockwave are terminated by the DaemonSet
controller and the operator stops re-scheduling. The standalone
`nvidia-device-plugin-shockwave` in `kube-system` continues exposing
`nvidia.com/gpu: 1` on the node.

The other already-disabled labels (`driver=false`, `gpu-feature-discovery=false`,
`operator-validator=false`, `dcgm-exporter=false`) were set at cluster
setup time for the same reason — Thor's JetPack ships its own drivers.
Leave them as-is.

Note: `gpu-operator-node-feature-discovery-worker` may continue running
on shockwave even with `node-feature-discovery=false` — it's deployed
without a nodeSelector matching that flag specifically. It's harmless
(provides node labels) and shouldn't be disabled manually.


## Verification

After deploying, from inside another pod in the `ai` namespace:

    curl -s http://gpt-oss-120b.ai.svc.cluster.local:8000/v1/models | jq

Should list the served model.

For tool-calling verification, see the parser table above — the expected
output depends on whether you added the `--tool-call-parser` flag.

Test the model end-to-end with a simple completion:

    curl -s http://gpt-oss-120b.ai.svc.cluster.local:8000/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{"model":"openai/gpt-oss-120b","messages":[{"role":"user","content":"hello"}]}' \
      | jq '.choices[0].message.content'

After deploying, verify tool calling works structurally:

    # From inside any pod in the ai namespace:
    curl -s http://gpt-oss-120b.ai.svc.cluster.local:8000/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{
        "model":"openai/gpt-oss-120b",
        "messages":[{"role":"user","content":"What is the weather in Amsterdam?"}],
        "tools":[{"type":"function","function":{"name":"get_weather","description":"Get weather","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],
        "tool_choice":"auto"
      }' | jq '.choices[0].message.tool_calls'

Expected: `[{ "id": "...", "type": "function", "function": { "name": "get_weather", "arguments": "{\"city\":\"Amsterdam\"}" } }]`.

If you see `[]` (empty array) with the model's intent visible in
`reasoning` instead, the parser flag is missing or wrong.


## Related skills (future)

- `mlops/dgx-spark-deploy` — equivalent for megatron (different SM, no Jetson quirks)
- `mlops/vllm-tool-call-debug` — diagnosing tool_calls returning empty arrays
