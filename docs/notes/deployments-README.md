# AI Cluster Deployment - Clean Setup

## Architecture

| Node | GPU | Services |
|------|-----|----------|
| **soundwave** | RTX 4090 (24GB) | nemotron-asr (STT) |
| **shockwave** | AGX Thor (128GB) | qwen3-72b (main LLM router) |
| **megatron** | DGX Spark | qwen3-coder-awq + riva-tts (coding + TTS) |
| **thundercracker** | CPU only | gcal-mcp, gmail-mcp |

## Deployment Order

### Step 1: port allocation

Node | Range | Service | Ports
soundwave | 20001-20100 | nemotron-asr | HTTP 20001, gRPC 20051
shockwave | 21001-21100 | qwen3-72b | 21001	
megatron  | 22001-22100	| (next)	
thundercracker | 8501-10000 | gcal-mcp 8200,gmail-mcp 8100	(existing, keep)

### Step 2: Verify clean state
```bash
kubectl -n ai get deploy
# Expected: gcal-mcp, gmail-mcp, haproxy-gw, open-webui only
```

### Step 3: Create TTS cache on megatron
```bash
ssh megatron "mkdir -p ~/.cache/nim-tts"
```

### Step 4: Deploy services (in order)
```bash
# ASR on soundwave (RTX 4090)
kubectl apply -f 01-nemotron-asr-soundwave.yaml

- Test:
curl -s http://10.108.71.179:20001/v1/health/ready


# Qwen3-72B on shockwave (Thor) - main LLM
kubectl apply -f 02-qwen3-72b-shockwave.yaml

- Test:
curl -s http://10.102.132.120:21001/v1/models



# Coder + TTS on megatron (DGX Spark)
kubectl apply -f 03-megatron-services.yaml
```

### Step 5: Monitor startup
```bash
# Watch all pods
kubectl -n ai get pods -w

# Check ASR logs (first startup builds TensorRT, ~7 min)
kubectl -n ai logs -f deploy/nemotron-asr

# Check Qwen3-72B logs
kubectl -n ai logs -f deploy/qwen3-72b

# Check megatron services
kubectl -n ai logs -f deploy/megatron-services -c vllm
kubectl -n ai logs -f deploy/megatron-services -c tts
```

## Service Endpoints

After deployment:
```bash
kubectl -n ai get svc
```

| Service | Port | Protocol | Usage |
|---------|------|----------|-------|
| nemotron-asr | 50051 | gRPC | Speech-to-Text |
| nemotron-asr | 9000 | HTTP | Health checks |
| qwen3-72b | 8000 | HTTP | OpenAI-compatible LLM |
| qwen3-coder-awq | 8000 | HTTP | OpenAI-compatible LLM |
| riva-tts | 50052 | gRPC | Text-to-Speech |
| riva-tts | 9000 | HTTP | Health checks |

## Voice Chat Pipeline

Update voice-chat.py with:
- ASR: `<nemotron-asr-svc-ip>:50051`
- LLM: `http://<qwen3-72b-svc-ip>:8000` (or qwen3-coder-awq for coding)
- TTS: `<riva-tts-svc-ip>:50052`

## Notes

- **Soundwave**: Standard k8s GPU allocation (`nvidia.com/gpu: 1`)
- **Shockwave**: Privileged mode required (Thor not exposed via device plugin)
- **Megatron**: Privileged mode for GPU sharing between vLLM and Riva TTS
- First startup of NIM containers builds TensorRT engines (~5-10 min), cached after
