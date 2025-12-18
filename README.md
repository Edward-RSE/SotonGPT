# SotonGPT

This is a repository containing the Docker project files for SotonGPT.

SotonGPT is based on OpenWebUI and vLLM. The service can be started by using `docker compose`:

```bash
docker compose up -d
```

The model vLLM uses and engine arguments are defined in the `.env` file.

## Kubernetes

SotonGPT can be deployed using to a local K8s cluster using [https://minikube.sigs.k8s.io/docs/](Minikube).

```bash
minikube start
```

```bash
kubectl apply -k kubernetes/manifest/
```

Add to /etc/hosts

```
127.0.0.1 sotongpt.minikube.local
```

```bash
minikube tunnel
```

Connect to the WebUI in your browser using <http://sotongpt.minikube.local>.

