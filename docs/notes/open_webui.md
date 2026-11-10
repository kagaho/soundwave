

- open-webui Deployment    

```
kubectl apply -f deployments/01-open-webui.yaml
```
  
- open-webui Service (ClusterIP). This version routes / to OpenWebUI.   
  
```
kubectl apply -f configmap/02-haproxy-config.yaml
```
  
- haproxy-gw Service as NodePort (or LoadBalancer if you have it)   
  
```
kubectl apply -f deployments/03-haproxy-gw.yaml
```

HAProxy routes:

```
/ → open-webui
/ollama → your ollama backend (optional; only if you run Ollama as a Service in K8s)
```

- Access:  
http://<megatron-node-ip>:31200/

