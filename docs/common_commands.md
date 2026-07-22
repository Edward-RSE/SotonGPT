# Common Commands

This covers the operational commands for managing SotonGPT when something is on fire: listing deployments, restarting
Open WebUI, standalone vLLM models, and KubeAI-backed models. All commands are assumed to be run on srv0885 which is the
control plane of the K8s cluster.

## Listing Deployments

Before restarting anything, it's worth listing the current deployments in the `sotongpt` namespace so you can confirm
the exact name of the resource you're targeting.

```bash
kubectl -n sotongpt get deploy
```

This returns every deployment in the `sotongpt` namespace, along with the number of ready replicas, up-to-date replicas,
and how long each has been running. You may wish to use this output in collaboration with the Grafana dashboards to
figure out which deployment is misbehaving.

## Restarting Open WebUI

Open WebUI doesn't need restarting but you may need to do it. This is most commonly required after adding or removing an
LLM connection to/from the backend. This is because Open WebUI caches its list of available models, and that cache
doesn't always refresh automatically when the underlying model connections/list changes.

```bash
kubectl -n sotongpt rollout restart deployment openwebui
```

Other situations where restarting Open WebUI is worthwhile include:

- The UI shows stale or incorrect model names after a configuration change
- Open WebUI appears unresponsive or is throwing errors unrelated to the models themselves
- After updating environment variables or config maps that Open WebUI reads on startup

To confirm the restart has completed successfully, check the rollout status:

```bash
kubectl -n sotongpt rollout status deployment openwebui
```

## Restarting a Model Running in vLLM

Standalone vLLM deployments are used for models that only need a single replica. These are more straightforward to
manage than KubeAI-backed models, and a restart is generally safe to run without much risk of breaking the deployment.

First, list the deployments to find the correct name:

```bash
kubectl -n sotongpt get deploy
```

Look for a deployment name matching the pattern `vllm-<model-name>`, for example `vllm-qwen3-32b`. All vLLM deployments
are prefixed with `vllm-`, which makes them easy to distinguish from Open WebUI and KubeAI resources.

Once you've identified the correct deployment name, restart it:

```bash
kubectl -n sotongpt rollout restart deployment vllm-qwen3-32b
```

Bear in mind that vLLM models can take a little while to become ready again after a restart, since the model weights
need to be reloaded into GPU memory. Use the following to watch progress:

```bash
kubectl -n sotongpt rollout status deployment vllm-qwen3-32b
```

If you want to check on pod-level detail (e.g. to see if a pod is stuck in `CrashLoopBackOff` or `Pending`), run:

```bash
kubectl -n sotongpt get pods
```

## Restarting a Model Running via KubeAI

Some models use KubeAI as the backend to manage vLLM replicas (with a reverse proxy to distribute requests§), rather
than running as a standalone vLLM deployment. These are defined differently, so the restart process is different: you
delete the model resource and reapply the manifest.

Navigate to the KubeAI models directory:

```bash
cd /opt/stongpt/kubernetes/services/kubeai/models
```

Delete the model resource, then reapply it:

```bash
kubectl delete -f llama3-1.yaml
kubectl apply -f llama3-1.yaml
```

### Why this is more fragile

Unlike standalone vLLM deployments, which only ever run a single replica and restart cleanly, KubeAI-managed models
involve an extra layer of orchestration responsible for scaling replicas up and down. Deleting and reapplying the
manifest means KubeAI has to re-provision the model from scratch, including re-establishing whatever autoscaling or
replica logic it manages. This process is more prone to getting stuck or ending up in an inconsistent state than a
straightforward deployment restart.

**Recommendation:** if a KubeAI-backed model is working, it's best left alone unless there's a genuine need to restart
it (e.g. picking up a config change in the manifest, or recovering from a genuinely broken state). If a restart does go
wrong, check the KubeAI controller logs and the model's pod events before attempting further changes:

```bash
kubectl -n sotongpt get pods
kubectl -n sotongpt describe pod <pod-name>
```

### A lighter-weight alternative: deleting the problematic pod

Rather than deleting and reapplying the whole manifest, it's often enough to delete just the specific pod that's
misbehaving, and let the controller (KubeAI) replace it. This is a less disruptive intervention than a full
delete-and-reapply, since it doesn't force KubeAI to re-provision the model.

The tricky part is identifying which pod is actually the problem, particularly when a model is running multiple
replicas. This is where the Grafana dashboards come in: use them to spot the misbehaving replica (e.g. one showing
abnormal GPU memory usage, request latency, or error rates compared to its siblings), then cross-reference against
`kubectl get pods` to find its name.

```bash
kubectl -n sotongpt get pods
kubectl -n sotongpt delete pod <pod-name>
```

Once deleted, the controller should spin up a replacement automatically. Keep an eye on the pod list to confirm the new
pod reaches `Running` and passes its readiness checks:

```bash
kubectl -n sotongpt get pods -l model=llama3-1 -w
```

## Quick Reference

| Task | Command |
|---|---|
| List all deployments | `kubectl -n sotongpt get deploy` |
| Restart Open WebUI | `kubectl -n sotongpt rollout restart deployment openwebui` |
| Restart a vLLM model | `kubectl -n sotongpt rollout restart deployment vllm-<model-name>` |
| Restart a KubeAI model | `cd /opt/stongpt/kubernetes/services/kubeai/models && kubectl delete -f <model>.yaml && kubectl apply -f <model>.yaml` |
| Delete a single problematic pod (identified via Grafana) | `kubectl -n sotongpt delete pod <pod-name>` |
| Check rollout status | `kubectl -n sotongpt rollout status deployment <name>` |
| Check pod status | `kubectl -n sotongpt get pods -l app=<name>` |
