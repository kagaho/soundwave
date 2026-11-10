# OpenWebUI on Kubernetes with HAProxy API Gateway and Self-Signed TLS

This document describes how to deploy **OpenWebUI** in Kubernetes and expose it through **HAProxy** acting as an **API Gateway**, including **HTTPS termination with a self-signed certificate**.

The deployment was tested in a **multi-node Kubernetes cluster with Flannel CNI** and GPU-enabled nodes.

---

# Architecture

```
Client
   │
   │ HTTPS
   ▼
HAProxy API Gateway
(NodePort 31443 / 31200)
   │
   │ ClusterIP
   ▼
OpenWebUI Service
   │
   ▼
OpenWebUI Pod
   │
   ├── PersistentVolume (UI data)
   └── PersistentVolume (Ollama models)
```

Components:

| Component             | Purpose                                |
| --------------------- | -------------------------------------- |
| **OpenWebUI**         | Web UI for interacting with LLM models |
| **HAProxy**           | API Gateway and TLS termination        |
| **PersistentVolumes** | Store OpenWebUI data and Ollama models |
| **Flannel CNI**       | Pod networking                         |
| **NodePort Service**  | Exposes HAProxy externally             |

---

# Cluster Assumptions

| Item             | Value                                |
| ---------------- | ------------------------------------ |
| Namespace        | `ai`                                 |
| GPU node         | `megatron`                           |
| Node external IP | `192.168.16.8`                       |
| CNI              | Flannel                              |
| Storage          | hostPath (no StorageClass available) |

---

# 1 Create Namespace

```bash
kubectl create namespace ai
```

---

# 2 Storage Configuration

Since the cluster **does not use a StorageClass**, we create **hostPath persistent volumes pinned to the GPU node**.

## storage.yaml

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-open-webui-data-megatron
spec:
  capacity:
    storage: 10Gi
  accessModes:
  - ReadWriteOnce
  storageClassName: local-hostpath
  persistentVolumeReclaimPolicy: Retain
  nodeAffinity:
    required:
      nodeSelectorTerms:
      - matchExpressions:
        - key: kubernetes.io/hostname
          operator: In
          values:
          - megatron
  hostPath:
    path: /var/lib/openwebui/data
    type: DirectoryOrCreate
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-open-webui-ollama-megatron
spec:
  capacity:
    storage: 50Gi
  accessModes:
  - ReadWriteOnce
  storageClassName: local-hostpath
  persistentVolumeReclaimPolicy: Retain
  nodeAffinity:
    required:
      nodeSelectorTerms:
      - matchExpressions:
        - key: kubernetes.io/hostname
          operator: In
          values:
          - megatron
  hostPath:
    path: /var/lib/openwebui/ollama
    type: DirectoryOrCreate
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: open-webui-data
  namespace: ai
spec:
  accessModes:
  - ReadWriteOnce
  storageClassName: local-hostpath
  resources:
    requests:
      storage: 10Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: open-webui-ollama
  namespace: ai
spec:
  accessModes:
  - ReadWriteOnce
  storageClassName: local-hostpath
  resources:
    requests:
      storage: 50Gi
```

Apply:

```bash
kubectl apply -f storage.yaml
```

Verify:

```bash
kubectl get pv,pvc -n ai
```

---

# 3 Deploy OpenWebUI

## openwebui.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: open-webui
  namespace: ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: open-webui
  template:
    metadata:
      labels:
        app: open-webui
    spec:
      runtimeClassName: nvidia
      nodeSelector:
        kubernetes.io/hostname: megatron
      containers:
      - name: open-webui
        image: ghcr.io/open-webui/open-webui:ollama
        ports:
        - containerPort: 8080
        env:
        - name: PORT
          value: "8080"
        volumeMounts:
        - name: data
          mountPath: /app/backend/data
        - name: ollama
          mountPath: /root/.ollama
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: open-webui-data
      - name: ollama
        persistentVolumeClaim:
          claimName: open-webui-ollama
---
apiVersion: v1
kind: Service
metadata:
  name: open-webui
  namespace: ai
spec:
  selector:
    app: open-webui
  ports:
  - port: 8080
    targetPort: 8080
  type: ClusterIP
```

Apply:

```bash
kubectl apply -f openwebui.yaml
```

---

# 4 HAProxy Gateway Configuration

## haproxy-config.yaml

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: haproxy-gw-config
  namespace: ai
data:
  haproxy.cfg: |
    global
      log stdout format raw local0
      maxconn 4096

    defaults
      log global
      mode http
      option httplog
      timeout connect 5s
      timeout client  300s
      timeout server  300s

    frontend fe_http
      bind *:8080
      http-request redirect scheme https code 301

    frontend fe_https
      bind *:8443 ssl crt /etc/haproxy/tls/tls.pem
      default_backend be_openwebui

    backend be_openwebui
      balance roundrobin
      server s1 open-webui.ai.svc.cluster.local:8080 check
```

Apply:

```bash
kubectl apply -f haproxy-config.yaml
```

---

# 5 Create Self-Signed TLS Certificate

```bash
HOST=openwebui.lab.local

openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
-keyout tls.key \
-out tls.crt \
-subj "/CN=${HOST}" \
-addext "subjectAltName=DNS:${HOST},IP:192.168.16.8"

kubectl -n ai create secret tls haproxy-tls \
--cert=tls.crt \
--key=tls.key
```

---

# 6 Deploy HAProxy Gateway

## haproxy.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: haproxy-gw
  namespace: ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: haproxy-gw
  template:
    metadata:
      labels:
        app: haproxy-gw
    spec:
      nodeSelector:
        kubernetes.io/hostname: megatron
      initContainers:
      - name: make-pem
        image: busybox:1.36
        command:
        - sh
        - -c
        - cat /tls-src/tls.crt /tls-src/tls.key > /tls-out/tls.pem && chmod 644 /tls-out/tls.pem
        volumeMounts:
        - name: tls-src
          mountPath: /tls-src
        - name: tls-out
          mountPath: /tls-out
      containers:
      - name: haproxy
        image: haproxy:3.0
        command:
        - /usr/local/sbin/haproxy
        args:
        - -W
        - -db
        - -f
        - /usr/local/etc/haproxy/haproxy.cfg
        ports:
        - containerPort: 8080
        - containerPort: 8443
        volumeMounts:
        - name: cfg
          mountPath: /usr/local/etc/haproxy/haproxy.cfg
          subPath: haproxy.cfg
        - name: tls-out
          mountPath: /etc/haproxy/tls
      volumes:
      - name: cfg
        configMap:
          name: haproxy-gw-config
      - name: tls-src
        secret:
          secretName: haproxy-tls
      - name: tls-out
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: haproxy-gw
  namespace: ai
spec:
  type: NodePort
  selector:
    app: haproxy-gw
  ports:
  - name: http
    port: 8080
    targetPort: 8080
    nodePort: 31200
  - name: https
    port: 8443
    targetPort: 8443
    nodePort: 31443
```

Apply:

```bash
kubectl apply -f haproxy.yaml
```

---

# 7 Testing

HTTP redirect

```bash
curl http://192.168.16.8:31200
```

HTTPS access

```bash
curl -k https://192.168.16.8:31443
```

---

# 8 Optional Local DNS

Add to `/etc/hosts`:

```bash
192.168.16.8 openwebui.lab.local
```

Test:

```bash
curl -k https://openwebui.lab.local:31443
```

---

# Final Result

You now have:

| Component | Status                  |
| --------- | ----------------------- |
| OpenWebUI | Running in Kubernetes   |
| HAProxy   | Acting as API Gateway   |
| TLS       | Self-signed certificate |
| Access    | HTTPS via NodePort      |

---

# Future Improvements

Possible next steps:

* Replace NodePort with **LoadBalancer**
* Add **Let's Encrypt TLS**
* Deploy **Ingress Controller**
* Integrate **OIDC authentication**
* Add **rate limiting and WAF policies**

---

# Summary

This deployment provides a **minimal but production-style architecture** for serving OpenWebUI through a **secure HAProxy gateway inside Kubernetes**, with persistent storage and GPU scheduling.

---
