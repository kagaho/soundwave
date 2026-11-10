# Kubernetes Multi-OS / Multi-Arch Installation Guide

## Cluster Topology

| Node | Role | OS | Architecture | GPU |
|------|------|----|--------------|-----|
| `soundwave` | Control Plane + Workloads | Fedora 43 | x86_64 (Intel) | NVIDIA RTX 4090 |
| `shockwave` | Worker | Ubuntu 24.04 (JetPack/L4T) | ARM64 | NVIDIA Jetson Thor (integrated) |
| `megatron` | Worker | Ubuntu 24.04 | ARM64 | NVIDIA DGX Spark (Grace Blackwell) |
| `thundercracker` | Worker | Fedora 43 | x86_64 | No GPU |

> **Note on multi-arch:** ARM64 workers are fully supported by Kubernetes and kubeadm. Container images must be multi-arch (most official images are).

> **Note on control plane workloads:** The control node will also schedule pods and jobs. By default kubeadm taints the control plane to prevent this — we will remove that taint after initialisation (Phase 5).

> **Note on GPU heterogeneity:** Each GPU node requires different treatment. The RTX 4090 and DGX Spark use discrete/SXM NVIDIA drivers. The Jetson Thor uses an integrated GPU with the JetPack/L4T driver stack — these are fundamentally different and cannot share the same driver installation path.

> **Note on CNI:** Flannel is used instead of Calico. The Jetson Thor (shockwave) runs a custom tegra kernel (`6.8.12-tegra`) that is missing `ip_set_hash_ip` and `ip_set_hash_net` kernel modules which Calico requires. Flannel uses plain VXLAN with zero ipset dependency and works reliably on all nodes including Jetson.

> **Note on Docker + Kubernetes coexistence:** shockwave and megatron run Docker alongside Kubernetes. Docker must be configured with `"iptables": false` to prevent it from fighting Flannel/kubelet for iptables ownership.

---

## Phase 1 — Pre-flight on ALL Nodes

> Run the following on every node (control + all workers), adapting the package manager as noted.

### 1.1 — Set Hostnames & /etc/hosts

On each node, set its hostname and ensure all nodes can resolve each other.

```bash
# On control node
sudo hostnamectl set-hostname soundwave

# On worker1
sudo hostnamectl set-hostname shockwave

# On worker2
sudo hostnamectl set-hostname megatron

# On worker3
sudo hostnamectl set-hostname thundercracker
```

Then on **every** node, add entries to `/etc/hosts` with your actual IPs:

```bash
sudo tee -a /etc/hosts <<EOF
192.168.15.2  k8s-control soundwave
192.168.16.7  k8s-worker1 shockwave
192.168.16.8  k8s-worker2 megatron
192.168.16.2  k8s-worker3 thundercracker
EOF
```

> **Important:** Make sure `k8s-control` resolves correctly on soundwave itself before running `kubeadm init`. Test with `ping k8s-control` — it must return `192.168.15.2`.

---

### 1.2 — Disable Swap (ALL nodes)

Kubernetes requires swap to be disabled.

```bash
# Disable immediately
sudo swapoff -a

# Disable permanently (remove or comment out swap line)
sudo sed -i '/\bswap\b/s/^/#/' /etc/fstab

# Verify
free -h  # Swap line should show 0
```

> On Fedora 43 with zram, also disable zram:
> ```bash
> sudo systemctl disable --now swap-create@zram0
> sudo touch /etc/systemd/zram-generator.conf   # empty config disables zram
> ```

---

### 1.3 — Load Required Kernel Modules (ALL nodes)

```bash
sudo tee /etc/modules-load.d/k8s.conf <<EOF
overlay
br_netfilter
EOF

sudo modprobe overlay
sudo modprobe br_netfilter

# Verify
lsmod | grep -E "overlay|br_netfilter"
```

---

### 1.4 — Set Kernel Networking Parameters (ALL nodes)

```bash
sudo tee /etc/sysctl.d/k8s.conf <<EOF
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF

sudo sysctl --system
```

> **Jetson Thor (shockwave) extra step:** The tegra kernel uses strict reverse path filtering (`rp_filter=2`) by default which silently drops pod traffic. Disable it permanently:
> ```bash
> sudo tee /etc/sysctl.d/99-k8s-jetson.conf <<EOF
> net.ipv4.conf.all.rp_filter=0
> net.ipv4.conf.enP2p1s0.rp_filter=0
> net.ipv4.conf.default.rp_filter=0
> EOF
> sudo sysctl --system
> ```

---

## Phase 2 — Install Container Runtime (containerd)

### 2A — On Fedora 43 (soundwave and thundercracker)

```bash
# Install containerd via Docker's repo for Fedora
# Note: Fedora 41+ uses DNF5 — use addrepo subcommand, not --add-repo flag
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager addrepo --from-repofile=https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf install -y containerd.io

# Generate default config
sudo mkdir -p /etc/containerd
sudo containerd config default | sudo tee /etc/containerd/config.toml

# Enable SystemdCgroup (required for Kubernetes)
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml

# Start & enable
sudo systemctl enable --now containerd
sudo systemctl status containerd
```

---

### 2B — On Ubuntu (shockwave and megatron — ARM64)

**Standard Ubuntu (megatron):**

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Write as single line — multiline echo causes malformed sources error
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y containerd.io
```

**Shockwave (Jetson Thor) — JetPack conflict fix:**

JetPack pre-configures Docker repos using `.asc` keyring format. Having both `.asc` and `.gpg` entries for the same URL causes a conflict error. Remove all existing Docker repo files first:

```bash
# Remove all conflicting JetPack Docker repo files
sudo rm -f /etc/apt/sources.list.d/docker.list
sudo rm -f /etc/apt/sources.list.d/docker.sources
sudo rm -f /etc/apt/keyrings/docker.gpg
sudo rm -f /etc/apt/keyrings/docker.asc

# Re-add cleanly
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y containerd.io
```

**Both Ubuntu nodes — configure containerd:**

```bash
sudo mkdir -p /etc/containerd
sudo containerd config default | sudo tee /etc/containerd/config.toml
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml

sudo systemctl enable --now containerd
sudo systemctl status containerd
```

**Both Ubuntu nodes — disable Docker iptables management:**

shockwave and megatron run Docker alongside Kubernetes. Docker must not manage iptables or it will conflict with Flannel and kube-proxy:

```bash
sudo mkdir -p /etc/docker
cat <<EOF | sudo tee /etc/docker/daemon.json
{
  "iptables": false
}
EOF

sudo systemctl stop docker
sudo systemctl stop docker.socket
sudo systemctl start docker.socket
sudo systemctl start docker

# Verify it took effect
sudo docker info | grep -i iptables
# Should show: Firewall Backend: none
```

---

## Phase 3 — Install Kubernetes Components (kubeadm, kubelet, kubectl)

> **Current stable release:** Kubernetes 1.32.x (as of early 2026)

### 3A — On Fedora 43 (soundwave and thundercracker)

```bash
sudo tee /etc/yum.repos.d/kubernetes.repo <<EOF
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/repodata/repomd.xml.key
EOF

sudo dnf install -y kubelet kubeadm kubectl
sudo systemctl enable --now kubelet
```

---

### 3B — On Ubuntu (shockwave and megatron)

```bash
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl gpg

curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.32/deb/Release.key | \
  sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

# Write as single line — multiline echo causes malformed sources error
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.32/deb/ /" | sudo tee /etc/apt/sources.list.d/kubernetes.list

sudo apt-get update
sudo apt-get install -y kubelet kubeadm kubectl
sudo apt-mark hold kubelet kubeadm kubectl   # Prevent accidental upgrades

sudo systemctl enable --now kubelet
```

---

## Phase 4 — Firewall Rules

### 4A — Fedora 43 (firewalld) — soundwave and thundercracker

```bash
sudo firewall-cmd --permanent --add-port=6443/tcp      # Kubernetes API server
sudo firewall-cmd --permanent --add-port=2379-2380/tcp  # etcd
sudo firewall-cmd --permanent --add-port=10250/tcp      # kubelet
sudo firewall-cmd --permanent --add-port=10259/tcp      # kube-scheduler
sudo firewall-cmd --permanent --add-port=10257/tcp      # kube-controller-manager
sudo firewall-cmd --permanent --add-port=8472/udp       # Flannel VXLAN
sudo firewall-cmd --permanent --add-port=30000-32767/tcp # NodePort range

sudo firewall-cmd --reload
```

> **Tip:** For a lab environment: `sudo firewall-cmd --set-default-zone=trusted`

---

### 4B — Ubuntu Workers (shockwave and megatron)

ufw is inactive on these nodes — iptables is managed directly by Flannel and kube-proxy. If ufw is active:

```bash
sudo ufw allow 10250/tcp
sudo ufw allow 30000:32767/tcp
sudo ufw allow 8472/udp        # Flannel VXLAN
sudo ufw allow from <CONTROL_IP>
sudo ufw reload
```

---

## Phase 5 — Initialize the Control Plane

Run **only on soundwave**:

```bash
sudo kubeadm init \
  --control-plane-endpoint="k8s-control:6443" \
  --pod-network-cidr=10.244.0.0/16 \
  --cri-socket unix:///var/run/containerd/containerd.sock
```

> **Important:** `10.244.0.0/16` is Flannel's default pod CIDR. Do NOT use `192.168.0.0/16` — it conflicts with the physical network.

After success, set up kubectl access:

```bash
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

kubectl get nodes
kubectl get pods -n kube-system
```

### 5.1 — Allow Workload Scheduling on Control Node

```bash
# Use the actual node name (soundwave), not k8s-control
kubectl taint nodes soundwave node-role.kubernetes.io/control-plane:NoSchedule-

# Verify
kubectl describe node soundwave | grep -i taint
# Should output: Taints: <none>

kubectl label node soundwave node-role.kubernetes.io/worker=worker
```

---

## Phase 6 — Install Flannel CNI

Flannel is a simple VXLAN-based CNI with no ipset dependency. It works reliably across all nodes including the Jetson Thor tegra kernel.

> **Why Flannel instead of Calico?** Calico requires `ip_set_hash_ip` and `ip_set_hash_net` kernel modules which are not compiled into the Jetson tegra kernel (`6.8.12-tegra`). Flannel has no such dependency and auto-detects the `10.244.0.0/16` pod CIDR.

Run on **soundwave only**:

```bash
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml

# Watch until all 4 flannel pods are Running (one per node)
watch kubectl get pods -n kube-flannel

# All nodes should flip to Ready within 1-2 minutes
kubectl get nodes
```

> **After joining workers:** Verify no stale CNI config files exist on any node. This can happen if containerd was restarted during setup:
> ```bash
> sudo ls -la /etc/cni/net.d/
> # Should only contain: 10-flannel.conflist
> # If any other files exist, remove them and restart kubelet:
> sudo rm -f /etc/cni/net.d/10-calico.conflist /etc/cni/net.d/calico-kubeconfig
> sudo systemctl restart kubelet
> ```


Note:  
```
sudo cat /etc/kubernetes/manifests/kube-controller-manager.yaml | grep -E 'cluster-cidr|allocate-node-cidrs'
    - --allocate-node-cidrs=true
    - --cluster-cidr=10.244.0.0/16
```
  
---

## Phase 7 — Join Worker Nodes

### 7.1 — Get the Join Command

On **soundwave**:

```bash
kubeadm token create --print-join-command
```

> Tokens are valid for 24 hours by default.

---

### 7.2 — Join shockwave (Ubuntu ARM64, Jetson Thor)

```bash
sudo kubeadm join k8s-control:6443 --token <TOKEN> \
  --discovery-token-ca-cert-hash sha256:<HASH> \
  --cri-socket unix:///var/run/containerd/containerd.sock
```

> If join fails with `unknown service runtime.v1.RuntimeService`, containerd's CRI plugin is disabled:
> ```bash
> sudo containerd config default | sudo tee /etc/containerd/config.toml
> sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
> sudo systemctl restart containerd
> ```
> If files from a previous failed attempt exist, reset first:
> ```bash
> sudo kubeadm reset -f
> sudo rm -rf /etc/kubernetes /var/lib/kubelet /var/lib/etcd /etc/cni /var/lib/cni
> sudo systemctl restart containerd
> ```

### 7.3 — Join megatron (Ubuntu ARM64, DGX Spark)

Same join command as shockwave.

### 7.4 — Join thundercracker (Fedora 43, x86_64)

Same join command — kubeadm detects the arch automatically.

---

### 7.5 — Label All Nodes (on soundwave)

```bash
# Role labels
kubectl label node shockwave        node-role.kubernetes.io/worker=worker
kubectl label node megatron         node-role.kubernetes.io/worker=worker
kubectl label node thundercracker   node-role.kubernetes.io/worker=worker

# Architecture labels are auto-populated by Kubernetes (kubernetes.io/arch)
# Values are amd64 (not x86_64) and arm64 — do not override
kubectl get nodes -o custom-columns=NAME:.metadata.name,ARCH:.metadata.labels."kubernetes\.io/arch"

# GPU labels
kubectl label node soundwave        gpu=rtx4090      gpu-type=discrete    gpu-vendor=nvidia
kubectl label node shockwave        gpu=jetson-thor   gpu-type=integrated  gpu-vendor=nvidia
kubectl label node megatron         gpu=dgx-spark     gpu-type=sxm         gpu-vendor=nvidia
kubectl label node thundercracker   gpu=none
```

---

## Phase 8 — Verify Cluster

```bash
# All 4 nodes should show Ready
kubectl get nodes -o wide

# All system pods should be Running
kubectl get pods -n kube-system
kubectl get pods -n kube-flannel

# Verify pod CIDR assignments
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.podCIDR}{"\n"}{end}'
# Expected:
# soundwave        10.244.0.0/24
# shockwave        10.244.2.0/24
# megatron         10.244.3.0/24
# thundercracker   10.244.1.0/24

# Test cross-node connectivity (including shockwave)
kubectl run test1 --image=busybox --restart=Never \
  --overrides='{"spec":{"nodeSelector":{"kubernetes.io/hostname":"shockwave"}}}' \
  -- sleep 3600

kubectl run test2 --image=busybox --restart=Never \
  --overrides='{"spec":{"nodeSelector":{"kubernetes.io/hostname":"megatron"}}}' \
  -- sleep 3600

kubectl get pods -o wide
kubectl exec test1 -- ping -c3 <test2-pod-ip>
kubectl delete pod test1 test2
```

---

## Phase 9 — GPU Setup (NVIDIA GPU Operator)

### GPU Stack Overview

```
RTX 4090 (soundwave, x86_64):
  GPU Operator  →  Toolkit + Device Plugin  →  containerd  →  Pod
  Drivers: akmod-nvidia (Fedora, pre-installed)

DGX Spark / Grace Blackwell (megatron, ARM64):
  GPU Operator  →  Toolkit + Device Plugin  →  containerd  →  Pod
  Drivers: nvidia-driver-570+ (pre-installed, Blackwell requires 570+)

Jetson Thor (shockwave, ARM64):
  GPU Operator  →  Toolkit + Device Plugin  →  containerd  →  Pod
  Drivers: JetPack/L4T baked in (DO NOT reinstall — gpu.deploy.driver=false)
```

> All GPU drivers are pre-installed. The GPU Operator is deployed with `driver.enabled=false`.

---

### 9.1 — Verify GPU Drivers

```bash
# On soundwave, shockwave, megatron
nvidia-smi
```

All three should return clean output before proceeding.

---

### 9.2 — Install NVIDIA GPU Operator Helm Chart

Run on **soundwave**:

```bash
helm repo add nvidia https://helm.ngc.nvidia.com/nvidia
helm repo update
kubectl create namespace gpu-operator
```

---

### 9.3 — Label GPU Nodes to Skip Driver Installation

```bash
kubectl label node soundwave  nvidia.com/gpu.deploy.driver=false
kubectl label node shockwave  nvidia.com/gpu.deploy.driver=false
kubectl label node megatron   nvidia.com/gpu.deploy.driver=false
```

---

### 9.4 — Deploy GPU Operator

```bash
kubectl label node shockwave \
  nvidia.com/gpu.deploy.gpu-feature-discovery=false \
  nvidia.com/gpu.deploy.node-feature-discovery=false \
  nvidia.com/gpu.deploy.container-toolkit=false \
  nvidia.com/gpu.deploy.device-plugin=false \
  nvidia.com/gpu.deploy.dcgm-exporter=false \
  nvidia.com/gpu.deploy.operator-validator=false \
  --overwrite
  ```


```bash
helm install gpu-operator nvidia/gpu-operator \
  --namespace gpu-operator \
  --set driver.enabled=false \
  --set toolkit.enabled=true \
  --set devicePlugin.enabled=true \
  --set dcgmExporter.enabled=true \
  --set operator.defaultRuntime=containerd

watch kubectl get pods -n gpu-operator
```
  
- to delete helm:  

```
helm uninstall gpu-operator -n gpu-operator --no-hooks --timeout 30s
kubectl delete namespaces gpu-operator
```

---

### 9.5 — Verify GPU Access

```bash
# Check GPU resources visible per node
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, gpu: .status.capacity["nvidia.com/gpu"]}'

# Test soundwave (RTX 4090)
kubectl run gpu-test-soundwave --image=nvidia/cuda:12.4.0-base-ubuntu22.04 \
  --restart=Never \
  --overrides='{"spec":{"nodeSelector":{"gpu":"rtx4090"},"runtimeClassName":"nvidia"}}' \
  -- nvidia-smi

# Test megatron (DGX Spark)
kubectl run gpu-test-megatron --image=nvidia/cuda:12.4.0-base-ubuntu22.04 \
  --restart=Never \
  --overrides='{"spec":{"nodeSelector":{"gpu":"dgx-spark"},"runtimeClassName":"nvidia"}}' \
  -- nvidia-smi

# Test shockwave (Jetson Thor) — L4T image required
kubectl run gpu-test-shockwave --image=nvcr.io/nvidia/l4t-base:r36.2.0 --restart=Never \
  --overrides='{
    "spec":{
      "nodeSelector":{"gpu":"jetson-thor"},
      "hostPID": true,
      "containers":[{
        "name":"tegra-host",
        "image":"nvcr.io/nvidia/l4t-base:r36.2.0",
        "securityContext":{"privileged":true},
        "command":["sleep","3600"],
        "volumeMounts":[{"name":"host-usrbin","mountPath":"/host/usr/bin","readOnly":true}]
      }],
      "volumes":[{"name":"host-usrbin","hostPath":{"path":"/usr/bin"}}]
    }
  }'


kubectl logs gpu-test-soundwave
kubectl logs gpu-test-megatron
kubectl logs gpu-test-shockwave
```

```
kubectl exec -it gpu-test-shockwave -- /host/usr/bin/tegrastats
03-04-2026 19:08:43 RAM 2888/125772MB (lfb 3x4MB) CPU [0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972] cpu@31.656C tj@31.625C soc012@31.437C soc345@31.062C VDD_GPU 0mW/0mW VDD_CPU_SOC_MSS 4734mW/4734mW VIN_SYS_5V0 5241mW/5241mW VIN 16670mW/8335mW
03-04-2026 19:08:44 RAM 2888/125772MB (lfb 3x4MB) CPU [0%@972,0%@972,1%@972,0%@972,0%@972,0%@972,0%@972,2%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972] cpu@31.656C tj@31.656C soc012@31.468C soc345@31.062C VDD_GPU 0mW/0mW VDD_CPU_SOC_MSS 4734mW/4734mW VIN_SYS_5V0 5241mW/5241mW VIN 16396mW/10350mW
03-04-2026 19:08:45 RAM 2888/125772MB (lfb 3x4MB) CPU [0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972,0%@972] cpu@31.625C tj@31.625C soc012@31.468C soc345@31.093C VDD_GPU 0mW/0mW VDD_CPU_SOC_MSS 4734mW/4734mW VIN_SYS_5V0 5241mW/5241mW VIN 16294mW/11341mW
```

---

### 9.6 — GPU Workload Scheduling Examples

**RTX 4090 (soundwave):**
```yaml
spec:
  runtimeClassName: nvidia
  nodeSelector:
    gpu: rtx4090
  containers:
  - name: my-gpu-job
    image: nvidia/cuda:12.4.0-base-ubuntu22.04
    resources:
      limits:
        nvidia.com/gpu: 1
```

**DGX Spark (megatron):**
```yaml
spec:
  runtimeClassName: nvidia
  nodeSelector:
    gpu: dgx-spark
  containers:
  - name: my-gpu-job
    image: nvidia/cuda:12.4.0-base-ubuntu22.04
    resources:
      limits:
        nvidia.com/gpu: 1
```

**Jetson Thor (shockwave) — L4T image required:**
```yaml
spec:
  runtimeClassName: nvidia
  nodeSelector:
    gpu: jetson-thor
  hostPID: true
  containers:
  - name: my-jetson-job
    image: nvcr.io/nvidia/l4t-ml:r36.2.0-py3
    securityContext:
      privileged: true
    command: ["sleep", "3600"]
    volumeMounts:
    - name: host-usrbin
      mountPath: /host/usr/bin
      readOnly: true
  volumes:
  - name: host-usrbin
    hostPath:
      path: /usr/bin
```


---

## Phase 10 — Multi-Arch Workload Considerations

### Architecture labels are auto-populated

Kubernetes automatically sets `kubernetes.io/arch` on each node using `amd64` (not `x86_64`) and `arm64`.

```yaml
# ARM64 only
spec:
  nodeSelector:
    kubernetes.io/arch: arm64
```

### Ensure your images are multi-arch

```bash
docker manifest inspect nginx:latest | grep -i architecture
docker buildx build --platform linux/amd64,linux/arm64 -t myimage:latest --push .
```

> **Jetson Thor:** Always use L4T-based images (`nvcr.io/nvidia/l4t-*`) for GPU workloads on shockwave. Standard CUDA images do not work on Jetson integrated GPU.

---

## Troubleshooting

| Issue | Check |
|-------|-------|
| Node not joining | `journalctl -xeu kubelet` on worker |
| Pods stuck Pending | `kubectl describe pod <n>` → check taints/events |
| CNI not ready | `kubectl get pods -n kube-flannel` — wait for all Running |
| Stale CNI config on node | `sudo ls /etc/cni/net.d/` → keep only `10-flannel.conflist`, restart kubelet |
| Swap still on | `free -h` → `swapoff -a` again |
| CRI not found | `systemctl status containerd` |
| CRI unknown service error | `containerd config default \| sudo tee /etc/containerd/config.toml` then restart |
| GPU not showing in kubectl | Check GPU Operator pods: `kubectl get pods -n gpu-operator` |
| Jetson GPU not detected | Verify `nvidia.com/gpu.deploy.driver=false` label is set |
| DGX Spark driver mismatch | Ensure driver 570+ is installed (Blackwell requires it) |
| RTX 4090 on Fedora | `lsmod \| grep nvidia` — akmod must have built the module |
| GPU pod stuck Pending | Ensure `runtimeClassName: nvidia` is set in pod spec |
| Docker fighting iptables | Verify `/etc/docker/daemon.json` has `"iptables": false`, restart Docker fully |
| Pod connectivity timeout on Jetson | `cat /proc/sys/net/ipv4/conf/enP2p1s0/rp_filter` — must be 0 |
| Control plane SELinux (Fedora) | Verify with `sestatus` — should be permissive on Fedora 43 workstation |

### Useful debug commands

```bash
# Check kubelet logs
journalctl -fu kubelet

# Check containerd
sudo crictl --runtime-endpoint unix:///var/run/containerd/containerd.sock ps

# Check CNI config on a node
sudo ls -la /etc/cni/net.d/

# Inspect a node
kubectl describe node shockwave

# Check pod CIDR assignments
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.podCIDR}{"\n"}{end}'

# Reset a node (destructive!)
sudo kubeadm reset -f
sudo rm -rf /etc/cni /var/lib/cni /var/lib/kubelet /var/lib/etcd /etc/kubernetes
sudo systemctl restart containerd
```

---

## Next Steps

- **Storage:** Install Longhorn (supports ARM64) for persistent volumes
- **Ingress:** Deploy ingress-nginx or Traefik (both multi-arch)
- **Metrics:** Install metrics-server for `kubectl top`
- **GPU Monitoring:** DCGM Exporter (included in GPU Operator) feeds into Prometheus/Grafana
- **KubeVirt:** Install KubeVirt to add VM support alongside GPU workloads
- **Dashboard:** Deploy Kubernetes Dashboard for a GUI

---

Note: firewalld opening on soundwave:  
   
```
sudo firewall-cmd --permanent --zone=trusted --add-interface=cni0
sudo firewall-cmd --permanent --zone=trusted --add-interface=flannel.1
sudo firewall-cmd --reload
```


