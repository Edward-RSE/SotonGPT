# Deploying with Kubernetes

SotonGPT can be deployed using Kubernetes

```
kubectl apply -k .
```

OpenWebUI is served to chat-dev.soton.ac.uk. Need to update /etc/hosts to be able
to access it, e.g. for k3s find the IP for the node:

```bash
$ kubectl get nodes -o wide
NAME   STATUS   ROLES           AGE    VERSION        INTERNAL-IP    EXTERNAL-IP   OS-IMAGE             KERNEL-VERSION      CONTAINER-RUNTIME
r3x    Ready    control-plane   100m   v1.34.3+k3s1   192.168.0.40   <none>        Ubuntu 24.04.3 LTS   6.14.0-37-generic   containerd://2.1.5-k3s1
```

Then modify /etc/hosts with the INTERNAL-IP value,

```
192.168.0.40 chat-dev.soton.ac.uk
```
