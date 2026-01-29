# Deploying SotonGPT with Kubernetes

We have decided to go with Kubernetes (K8s) as our method to deploy and manage the individual components of SotonGPT.
The main reasons for this are:

1. Scalability: K8s will let us scale resources vertically and horizontally automatically as demand for the system
   grows. Whilst this is possible with a Docker Compose project, it isn't automated to the same degree especially with
   container replication and load balancing.
2. Resillience: K8s takes care of health checks and restarting failed/stuck containers automatically.
3. Future growth: The architecture can be extended to support additional services, replicas, or nodes without requiring
   a redesign of the deployment approach.
4. Operational advatnages: Built-in logging, metrics, and health probes means monitoring and debugging SotonGPT should
   be easier.

We'll be using [K3s](https://k3s.io/) to create the K8s cluster. K3s is a certified Kubernetes distribution designed for
production deployments in resource-constrained, remote locations or inside IoT appliances. Not exactly our usecase, but
it creates a lightweight K8s cluster (K3s is a single <70MB binary) so we can dedicate as much resource as possible to
OpenWebUI and the vLLM containers.

## Installing and configuring K3s

You can follow the installation [quick-start guide](https://docs.k3s.io/quick-start) and other installation
instrunctions to install K3s. However, installation can also be handled by a one-liner to use the default configuration:

```bash
$ curl -sfL https://get.k3s.io | sh -
```

This will install K3s and configure a K3s service which will automatically restart on reboots. It also installs all the
necessary K8s utilities, such as `kubectl`. The default configuration will set up a single-node configuration, with the
control plane and worker node workloads running on the same machine. Additinal "agent" nodes can be added to the cluster
using the same script.

You can verify that everything is working by running the following command, which should show the system containers
responsible for running the cluster.

```bash
$ kubectl get pods -A                                                           [10:08]
NAMESPACE     NAME                                      READY   STATUS      RESTARTS       AGE
kube-system   coredns-7f496c8d7d-q2jgx                  1/1     Running     1 (144m ago)   25h
kube-system   helm-install-traefik-629wm                0/1     Completed   1              25h
kube-system   helm-install-traefik-crd-s4tlb            0/1     Completed   0              25h
kube-system   local-path-provisioner-578895bd58-nbxgb   1/1     Running     1 (144m ago)   25h
kube-system   metrics-server-7b9c9c4b9c-fcxcp           1/1     Running     1 (144m ago)   25h
kube-system   nvidia-device-plugin-daemonset-r5f8h      1/1     Running     1 (18h ago)    24h
kube-system   svclb-traefik-70f9e36b-87knb              2/2     Running     2 (144m ago)   25h
kube-system   traefik-6f5f87584-dkznx                   1/1     Running     1 (144m ago)   25h
```

Chances are, you will be greeted by the follow error when you try to use `kubectl` the first time.

```
ARN[0000] Unable to read /etc/rancher/k3s/k3s.yaml, please start the server with --write-kubeconfig-mode to modify kube config permissions
error: error loading config file "/etc/rancher/k3s/k3s.yaml": open /etc/rancher/k3s/k3s.yaml: permission denied
```

This occurs because the default K3 sconfiguration file is owned by root and in a restricted directory. You can either
always use `sudo` when running `kubectl` (like with Docker when you haven't configured rootless access), set the file
permission to 600 or create a user-specific configuration file. We'll go with the latter option, with instructions on
how to set that up [here](https://dev.to/olymahmud/resolving-the-k3s-config-file-permission-denied-error-27e5).

### Setting up GPU resources

K3s thankfully supports managing GPU resources. However, there is some leg work we have to do first. We need to:

1. Install NVIDIA GPU drivers
2. Install the NVIDIA Container Runtime
3. Install the NVIDIA device plugin for K8s
4. Set the default container runtime for K3s to the NVIDIA container runtime

#### GPU drivers and container runtime

```bash
$ curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
    && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list \
    && sudo apt update
```

```bash
$ export NVIDIA_CONTAINER_TOOLKIT_VERSION=1.18.2-1
$ sudo apt-get install -y \
      nvidia-container-toolkit=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      nvidia-container-toolkit-base=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      libnvidia-container-tools=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      libnvidia-container1=${NVIDIA_CONTAINER_TOOLKIT_VERSION}
```

## Deployment guide

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
