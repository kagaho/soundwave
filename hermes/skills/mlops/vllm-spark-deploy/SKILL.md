---
name: vllm-spark-deploy
description: Deploy a vLLM-served LLM on an NVIDIA DGX Spark (or compatible GB10/SM121 platform like ASUS GX10) via Kubernetes — covers NVIDIA driver upgrade flow, the DGX Spark vLLM image compatibility matrix, time-slicing opt-out per node, hostNetwork DNS workaround, and the reference manifest with verified parser flags for Qwen3-Coder-Next.
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [k8s, vllm, dgx-spark, gb10, blackwell, gpu, inference, nvidia]
    category: mlops
---

# Deploy vLLM on NVIDIA DGX Spark (GB10 / SM121)

## When to Use

Deploying any vLLM-served LLM on a DGX Spark node (or compatible
GB10/SM121 platform: ASUS GX10, Dell Pro Max with GB10, etc.). Spark
has 128 GB unified memory (LPDDR5x, ~119 GB usable), ARM64 CPU, and
the Blackwell consumer compute capability sm_121.

This skill does **not** cover Jetson AGX Thor (sm_90) — see
`vllm-jetson-deploy` for that. Quirks differ enough (firmware-baked
drivers on Thor vs apt-managed on Spark; gpu-operator-broken on Thor
vs operator-friendly on Spark) that a unified skill obscures more
than it shares.

## Background

DGX Spark systems ship with **DGX OS** (NVIDIA's customized Ubuntu),
even when the hardware is OEM-branded (ASUS, Dell, etc.). Three things
matter for vLLM deployment:

1. **CUDA compatibility matrix.** vLLM container images bundle a
   specific CUDA runtime that requires a minimum host driver version.
   Mismatch → container starts but cannot see GPU.
2. **MoE > dense on unified memory.** Empirically observed ~7x
   throughput difference between MoE and dense models of equivalent
   parameter count, because memory bandwidth (not compute) is the
   bottleneck on Spark's unified architecture.
3. **GPU exposed via gpu-operator** (unlike Thor). The standard
   nvidia-device-plugin DaemonSet works fine. Time-slicing is enabled
   globally by default — opt out per-node if a workload needs full GPU.

## Procedure

### 1. Verify hardware and driver

```
# Confirm GB10 detection
nvidia-smi

# DGX OS info
cat /etc/dgx-release    # DGX_PLATFORM=GX10, DGX_NAME="DGX Spark", etc.

# Current driver and CUDA
nvidia-smi | grep -E 'Driver Version|CUDA Version'

# Kernel
uname -r
```

Note: `nvidia-smi` shows "Memory-Usage: Not Supported" on GB10. This
is expected — unified memory has no separate VRAM pool to report.

### 2. Match driver to vLLM image

NVIDIA NGC publishes vLLM images at `nvcr.io/nvidia/vllm:YY.MM-py3`.
There is no `latest` tag.

| Image tag        | vLLM    | CUDA  | Driver min | Notes                          |
|------------------|---------|-------|------------|--------------------------------|
| `25.09-py3`      | 0.10.1  | 13.0  | 580.x      | First DGX Spark support release. No Qwen3-Coder-Next support (vLLM too old). |
| `26.01-py3`      | 0.13.0  | 13.1  | 590.x      | Mid-cycle, limited utility.    |
| `26.03-py3`      | 0.17.1  | ?     | ?          | Skip.                          |
| `26.04-py3`      | 0.19.0  | 13.2  | 595.58+    | Full Qwen3-Coder-Next-FP8 support, qwen3_coder parser. **Recommended.** |

To check what a specific image bundles:

```
docker run --rm nvcr.io/nvidia/vllm:26.04-py3 vllm --version
```

### 3. Upgrade NVIDIA driver if needed

If `nvidia-smi` shows a driver older than what the target image needs,
upgrade:

```
# Confirm package availability
sudo apt update
apt search 'nvidia-driver-595-open'

# Drain the node first (gpu-operator pods will resettle after reboot)
kubectl drain <NODE> --ignore-daemonsets --delete-emptydir-data --force

# Dry-run to see what apt will do
sudo apt install --dry-run nvidia-driver-595-open 2>&1 | tail -50

# Apply
sudo apt install nvidia-driver-595-open
sudo reboot
```

After reboot, **two pitfalls** to know:

**(a) Kernel switched without matching module installed.** If the
kernel package was upgraded alongside the driver and the new kernel
boots without the matching `linux-modules-nvidia-*` module
preinstalled, `nvidia-smi` fails with "couldn't communicate with the
NVIDIA driver". The `.ko` files are sometimes present but unindexed.
Fix:

```
ls /lib/modules/$(uname -r)/kernel/nvidia-*-open/  # .ko files present?
sudo depmod -a
sudo modprobe nvidia nvidia_uvm nvidia_drm
nvidia-smi   # should now report new driver version
```

**(b) Firmware update may also be triggered on first boot.** Wait a
full minute after `reboot` before reconnecting. DGX OS may apply
firmware updates that complete before the user-facing system is
back. A second voluntary reboot after firmware update is sometimes
useful.

### 4. Verify Docker-to-GPU after driver upgrade

```
docker run --rm --gpus all nvcr.io/nvidia/vllm:26.04-py3 nvidia-smi
```

Should show GB10 with new driver inside the container. If this fails
with "could not select device driver" or "libnvidia-ml.so missing",
upgrade `nvidia-container-toolkit`:

```
sudo apt install nvidia-container-toolkit libnvidia-container-tools libnvidia-container1
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo nvidia-ctk runtime configure --runtime=containerd
sudo systemctl restart containerd
```

### 5. Opt out of time-slicing for this workload (if applicable)

If the cluster runs `gpu-operator` with a time-slicing ConfigMap, the
node will advertise multiple virtual GPU slots (e.g., `nvidia.com/gpu: 2`).
For a model that consumes most of the 119 GB unified memory, this is
misleading — the k8s scheduler will happily place two workloads that
together OOM the node.

Inspect:

```
kubectl -n gpu-operator get configmap time-slicing-config -o yaml
kubectl describe node <NODE> | grep -E 'nvidia.com/gpu(.replicas|.sharing|:)'
```

If the default profile uses `sharing.timeSlicing` with `replicas: 2+`,
add a `single` profile (omitting the sharing block — `replicas: 1`
inside a `sharing.timeSlicing` block is rejected by k8s-device-plugin
with `number of replicas must be >= 2`):

```
kubectl -n gpu-operator apply -f - <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config
  namespace: gpu-operator
data:
  any: |-
    version: v1
    sharing:
      timeSlicing:
        resources:
          - name: nvidia.com/gpu
            replicas: 2
  single: |-
    version: v1
    flags:
      migStrategy: none
EOF
```

Label the node to use the `single` profile and force reload:

```
kubectl label node <NODE> nvidia.com/device-plugin.config=single --overwrite

DP_POD=$(kubectl -n gpu-operator get pod -l app=nvidia-device-plugin-daemonset \
  -o wide | grep <NODE> | awk '{print $1}')
kubectl -n gpu-operator delete pod $DP_POD
```

After ~30s, verify:

```
kubectl describe node <NODE> | grep 'nvidia.com/gpu:'
# Expect: Capacity: 1, Allocatable: 1 (was 2 and 2)
```

### 6. Pre-stage the HuggingFace cache (optional but recommended)

vLLM downloads the model on first run via HuggingFace. With
`hostNetwork: true` this works, but for ~85 GB models a pre-warm avoids
re-downloading on pod recreation:

```
# As the user who will own the cache (e.g., rteixeira)
pip install -U "huggingface_hub[cli]"
hf download Qwen/Qwen3-Coder-Next-FP8 \
  --local-dir ~/.cache/huggingface/hub/models--Qwen--Qwen3-Coder-Next-FP8 \
  --resume-download
```

### 7. Deploy the manifest

Reference Deployment for Qwen3-Coder-Next-FP8 (~85 GB model + ~25 GB
KV cache at 64K context). Replace `<NODE>` with the target node name
and adjust paths.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: qwen3-coder-next
  namespace: ai
  labels:
    app: qwen3-coder-next
    workload: coding-llm
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: qwen3-coder-next
  template:
    metadata:
      labels:
        app: qwen3-coder-next
        workload: coding-llm
    spec:
      nodeSelector:
        kubernetes.io/hostname: <NODE>
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet
      terminationGracePeriodSeconds: 60
      containers:
        - name: vllm
          image: nvcr.io/nvidia/vllm:26.04-py3
          imagePullPolicy: IfNotPresent
          command: ["vllm"]
          args:
            - serve
            - Qwen/Qwen3-Coder-Next-FP8
            - --host
            - 0.0.0.0
            - --port
            - "8002"
            - --tensor-parallel-size
            - "1"
            - --max-model-len
            - "65536"
            - --gpu-memory-utilization
            - "0.80"
            - --enable-auto-tool-choice
            - --tool-call-parser
            - qwen3_coder
            - --enable-prefix-caching
            - --served-model-name
            - Qwen/Qwen3-Coder-Next-FP8
          env:
            - name: HF_HOME
              value: /root/.cache/huggingface
          ports:
            - containerPort: 8002
              name: http
              protocol: TCP
          resources:
            limits:
              nvidia.com/gpu: "1"
          volumeMounts:
            - name: huggingface-cache
              mountPath: /root/.cache/huggingface
          securityContext:
            capabilities:
              drop: ["ALL"]
            allowPrivilegeEscalation: false
      volumes:
        - name: huggingface-cache
          hostPath:
            path: /home/<USER>/.cache/huggingface
            type: Directory
---
apiVersion: v1
kind: Service
metadata:
  name: qwen3-coder-next
  namespace: ai
  labels:
    app: qwen3-coder-next
spec:
  type: ClusterIP
  selector:
    app: qwen3-coder-next
  ports:
    - name: http
      port: 8000
      targetPort: 8002
      protocol: TCP
```

Notes on choices:

- `hostNetwork: true` + `dnsPolicy: ClusterFirstWithHostNet`: required
  if the docker daemon on this node has `iptables: false` (common in
  setups that coexist with k8s/flannel). Without hostNetwork, the
  container cannot resolve external DNS (HuggingFace download fails).
  With ClusterFirstWithHostNet, the container can still resolve
  `*.svc.cluster.local` for in-cluster service discovery.
- `--port 8002` on the pod, `port: 8000 → targetPort: 8002` in the
  Service. The Service-facing port stays consistent with other LLM
  services in the namespace; the pod port avoids conflicting with
  anything else on the host.
- `--gpu-memory-utilization 0.80`: tested empirically. At 0.85, total
  RAM usage hits ~104 GB on a 119 GB node — too tight. 0.80 leaves
  ~24 GB headroom for the system and any small co-resident workload.
- `--max-model-len 65536`: 64K context window. Qwen3-Coder-Next is
  trained for 256K but KV cache at 256K alone consumes ~25 GB. 64K
  is sufficient for most coding agent workflows.
- `--enable-prefix-caching`: critical for coding agent loops that
  re-process the same prompt skeleton per turn.
- No readiness/liveness probes: cold start of an 80B MoE on Spark is
  ~2-3 minutes. A naive HTTP probe will kill the pod before it can
  serve.

### 8. Verify

Service-side, from another pod in the same namespace:

```
# Models registered?
kubectl exec -n ai <POD> -- curl -s \
  http://qwen3-coder-next.ai.svc.cluster.local:8000/v1/models | jq

# Generation works?
kubectl exec -n ai <POD> -- curl -s \
  http://qwen3-coder-next.ai.svc.cluster.local:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen3-Coder-Next-FP8","messages":[{"role":"user","content":"hello"}]}' \
  | jq '.choices[0].message.content'

# Tool calling structured (the real test)?
kubectl exec -n ai <POD> -- curl -s \
  http://qwen3-coder-next.ai.svc.cluster.local:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"Qwen/Qwen3-Coder-Next-FP8",
    "messages":[{"role":"user","content":"Read /etc/hostname"}],
    "tools":[{"type":"function","function":{"name":"read_file","description":"Read","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}}],
    "tool_choice":"auto"
  }' | jq '.choices[0].message.tool_calls'
```

Expected: third command returns
`[{"id":"...","type":"function","function":{"name":"read_file","arguments":"{\"path\":\"/etc/hostname\"}"}}]`.
Empty array `[]` means the parser flag is wrong — try `qwen3_xml`
instead of `qwen3_coder` (validated fallback per NVIDIA forum for
long-running Hermes Agent sessions).

## Tool-call parser selection

vLLM does not auto-detect tool-call formats. The parser flag is
per-model-family. List parsers supported in any specific image:

```
docker run --rm nvcr.io/nvidia/vllm:26.04-py3 \
  vllm serve --help=Frontend 2>&1 | grep -A 2 'tool-call-parser'
```

For Spark deploys typically:

| Model family               | Parser flag                                                    |
|----------------------------|----------------------------------------------------------------|
| Qwen3-Coder / Qwen3-Coder-Next | `--tool-call-parser qwen3_coder` (recommended) or `qwen3_xml` |
| Qwen3 (chat / instruct)    | `--tool-call-parser hermes` or `qwen3_xml`                     |
| gpt-oss (OpenAI harmony)   | `--tool-call-parser openai`                                    |
| Llama 3.x / 4              | `--tool-call-parser llama3_json` / `llama4_json`               |
| DeepSeek V3.x              | `--tool-call-parser deepseek_v32`                              |
| GLM 4.5+ (where compatible)| `--tool-call-parser glm45` or `glm47`                          |
| Mistral / Mixtral          | `--tool-call-parser mistral`                                   |

Without `--enable-auto-tool-choice` and a parser flag, the model still
generates tool calls in its training format, but vLLM drops them and
returns `tool_calls: []` to OpenAI-SDK clients. Hermes Agent parses
raw output so it still works, but stricter clients (LangChain,
direct OpenAI SDK) will not.

## Pitfalls

- **NVFP4 quantized models crash on GB10/SM121.** Confirmed bug,
  manifests as "CUDA illegal instruction". Avoid all NVFP4 variants;
  use FP8 (native Blackwell acceleration) or INT4 AutoRound instead.
- **Stock vLLM (PyPI / source build) does NOT work on sm_121.**
  Prebuilt PyTorch CUDA kernels only include sm_120. Use the NVIDIA
  NGC container images (above) — they include sm_121 patches.
- **`hostPath` is host-user-specific.** The reference manifest mounts
  `/home/<USER>/.cache/huggingface`. When porting to a new node or
  user, update the path or migrate to a PVC.
- **CUDA 13.2 driver mismatch with old DGX OS.** If the container
  needs driver 595.58+ but DGX OS BaseOS hasn't pushed it yet,
  check `apt search 'nvidia-driver-595'`. If absent, check
  `/etc/dgx-release` (`DGX_OTA_VERSION`) and consider DGX OTA upgrade
  via `dgx-dashboard`. ASUS GX10 ships DGX OS with `dgx-dashboard`
  but without `dgxos-update` CLI.
- **`Memory-Usage: Not Supported` in nvidia-smi is normal on GB10.**
  Use `free -h` for RAM (it's the same physical pool) and
  `nvidia-smi --query-gpu=utilization.gpu,power.draw,temperature.gpu --format=csv`
  for GPU activity.
- **Time-slicing with `replicas: 1` is rejected.** The k8s-device-plugin
  fails with "number of replicas must be >= 2" when a sharing block
  is present with `replicas: 1`. To disable sharing, omit the entire
  `sharing.timeSlicing` block.
- **gpu-operator daemonsets stuck "Unknown" after reboot.** Pods that
  were on the node before reboot may show as `Unknown` indefinitely.
  Delete them; the DaemonSet controller recreates clean.

## Common debugging table

| Symptom | Likely cause | Fix |
|---|---|---|
| `Failed to infer device type` in container | Driver too old for container CUDA version | Upgrade driver to match image's CUDA bundle |
| `libcuda.so.1: cannot open shared object file` | `--gpus all` not effective; toolkit not registered | `nvidia-ctk runtime configure --runtime=docker; systemctl restart docker` |
| `nvidia-smi: NVIDIA-SMI has failed` after reboot | Kernel changed, module not indexed | `sudo depmod -a; sudo modprobe nvidia` |
| DNS resolution times out in container | Docker daemon `iptables: false` | Use `hostNetwork: true` + `dnsPolicy: ClusterFirstWithHostNet`, or `--network host` for ad-hoc docker runs |
| `tool_calls: []` despite model intent visible | Wrong `--tool-call-parser` flag | Try parser variants (e.g., `qwen3_xml` instead of `qwen3_coder`) |
| Pod Pending with `0/N nodes available, Insufficient nvidia.com/gpu` | Time-slicing replicas changed mid-flight, or device-plugin not registered | Verify `kubectl describe node <NODE> \| grep 'nvidia.com/gpu:'` shows expected count |
| OOM kill mid-load | `--gpu-memory-utilization` too high for co-resident workloads | Reduce to 0.75-0.80, or eliminate other GPU consumers |

## In-cluster networking notes

Even with `hostNetwork: true`, the Service+selector pattern works
normally — k8s adds an iptables rule that routes
`qwen3-coder-next.ai.svc.cluster.local:8000` to the host's port 8002.
Other pods in the same namespace can call the Service without knowing
the underlying port.

Setting `dnsPolicy: ClusterFirstWithHostNet` (not the default
`ClusterFirst`, which is broken when hostNetwork is true) lets the
hostNetwork'd pod resolve other `*.svc.cluster.local` names — useful
if vLLM is part of a larger pipeline that calls other in-cluster
services.

## Related skills

- `vllm-jetson-deploy` — equivalent for Jetson AGX Thor (sm_90)
- (future) `vllm-tool-call-debug` — diagnosing tool_calls returning empty arrays
- (future) `dgx-ota-update` — coordinated firmware/driver/kernel update via DGX dashboard
