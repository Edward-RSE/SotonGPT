# Common Commands

List the current deployments, which can be restarted

```bash
kubectl -n sotongpt get deploy
```

To restart Open WebUI (which, amongst other reasons, sometimes you need to do when you add or remove an LLM due to how
the caching for the list of models works)

```bash
kubectl -n sotongpt rollout restart deployment openwebui
```

To restart a model running in vLLM

```bash
kubectl -n sotongpt get deploy
```

Find a deployment which looks like `vllm-qwen3-32b`, all vLLM deployment start with `vllm-`

```bash
kubectl -n sotongpt rollout restart deployment vllm-qwen3-32b
```

To restart a model which uses KubeAI as the backend to spin up replicas, navigate to the KubeAI directory

```bash
cd /opt/stongpt/kubernetes/services/kubeai/models
```

Now you need to delete the model and launch it again

```bash
kubectl delete -f llama3-1.yaml
kubectl apply -f llama3-1.yaml
```

This is more fragile than the standalone vLLM models which only support 1 replica. So if something breaks, perhaps
best to leave it alone.
