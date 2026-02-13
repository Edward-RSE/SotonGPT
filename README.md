# SotonGPT

This is a repository containing the files used to deploy SotonGPT. Note that a GPU is required to deploy SotonGPT using
both Docker and Kubernetes.

## Deploying SotonGPT with Docker

An early and experimental version of SotonGPT can be deployed using Docker. **This is not the supported method of
deployment for SotonGPT.**

First download the repository and navigate into it:

```bash
git clone git@github.com:Edward-RSE/SotonGPT.git && cd SotonGPT/docker
```

The current configuration is to deploy a vLLM server running Qwen/Qwen3-0.6B. If you want to change this, modify the
provided `.env` file. To launch SotonGPT, run the following command:

```bash
docker compose up
```

## Deploying SotonGPT with Kubernetes

We have decided to go with Kubernetes (K8s) as our method to deploy and manage the individual components of SotonGPT.
The main reasons for this are:

1. Scalability: K8s will let us scale resources vertically and horizontally automatically as demand for the system
   grows. Whilst this is possible with a Docker Compose project, it isn't automated to the same degree especially with
   container replication and load balancing.
2. Resilience: K8s takes care of health checks and restarting failed/stuck containers automatically.
3. Future growth: The architecture can be extended to support additional services, replicas, or nodes without requiring
   a redesign of the deployment approach.
4. Operational advantages: Built-in logging, metrics, and health probes means monitoring and debugging SotonGPT should
   be easier.

We'll be using [K3s](https://k3s.io/) to create the K8s cluster. K3s is a certified Kubernetes distribution designed for
production deployments in resource-constrained, remote locations or inside IoT appliances. Not exactly our usecase, but
it creates a lightweight K8s cluster (K3s is a single <70MB binary) so we can dedicate as much resource as possible to
OpenWebUI and the vLLM containers.

## Architecture

More details about the K8s architecture can be found in [kubernetes/README.md](kuberenetes/README.md).

## Installing and configuring K3s

You can follow the installation [quick-start guide](https://docs.k3s.io/quick-start) and other installation
instrunctions to install K3s. However, installation can also be handled by a one-liner to use the default configuration:

```bash
curl -sfL https://get.k3s.io | sh -
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

The first steps should be install the latest stable graphics drivers and the NVIDIA container runtime. In most systems,
drivers can be installed through the package manager:

```bash
sudo apt install nvidia-driver-590
```

To install the container runtime, we have to add the NVIDIA repositories to the package manager (this assumes you have
Curl and GPG installed):

```bash
$ curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
    && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list \
    && sudo apt update
```

Now we can install the packages required:

```bash
$ export NVIDIA_CONTAINER_TOOLKIT_VERSION=1.18.2-1
$ sudo apt install -y \
      nvidia-container-toolkit=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      nvidia-container-toolkit-base=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      libnvidia-container-tools=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      libnvidia-container1=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      nvidia-container-runtime
```

Once this is installed, restart the K3s service. If everything has gone to plan, K3s will automatically add the NVIDIA
container runtime to the containerd configuration. This can be confirmed by grep'ing for nvidia in the K3s containerd
configuration file:

```bash
sudo systemctl restart k3s && grep nvidia /var/lib/rancher/k3s/agent/etc/containerd/config.toml
```

The final two steps are to installed the NVIDIA device plugin for K8s and set the NVIDIA container runtime as the
default runtime. To install the plugin, run the following command:

```bash
kubectl create -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.17.1/deployments/static/nvidia-device-plugin.yml
```

Confirmation installation by looking at the kube-system pods:

```bash
$ kubectl get pods -n kube-system | grep nvidia
nvidia-device-plugin-daemonset-r5f8h      1/1     Running     2 (63m ago)   28h
```

Finally, we can check that the GPUs have been found by K3s by running the following, which will print the nodes in the
K3s cluster and the number of available GPUs on the node:

```bash
$ kubectl get nodes "-o=custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu"
NAME   GPU
r3x    1
```

You may optionally also wish to configure the NVIDIA container runtime to be the default container. To do this, we need
to modify the K3s service definition to add an additional argument. Add `--default-runtime nvidia` to `ExecStart` in
`/etc/systemd/system/k3s.service`:

```service
...
ExecStart=/usr/local/bin/k3s \
   server --default-runtime nvidia \
```

## Deploying SotonGPT to K3s

To deploy SotonGPT, clone the git repository and navigate into the directory:

```bash
git clone git@github.com:Edward-RSE/SotonGPT.git && cd SotonGPT
```

Assuming all is OK with your K3s installation, as you should need to do use `kubectl` to apply the SotonGPT manifests to
the cluster:

```bash
kubectl apply -k kubernetes/
```

This will create a namespace `sotongpt`. Check that the pods have been deployed, as well as the persistent volumes
claims:

```bash
$ kubectl get pods -n sotongpt
NAME                                    READY   STATUS    RESTARTS   AGE
openwebui-deployment-646f76d7d5-lxw59   1/1     Running   0          6s
vllm-server-6c78b6877c-hqthv            0/1     Pending   0          6s
$ kubectl get pvc -n sotongpt
NAME            STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   VOLUMEATTRIBUTESCLASS   AGE
openwebui-pvc   Bound    openwebui-pv                               64Gi       RWO            manual         <unset>                 111s
vllm-server     Bound    pvc-0635d727-a4f6-45dd-958a-9751e182e0d5   64Gi       RWO            hostpath       <unset>                 111s
```

If you see a status of anything other than "Running", you can check the event history of the pod using `kubectl describe
pod -n sotongpt <pod-name>`. If the vLLM pod is stuck in pending, it's possible that K3s has been unable to allocate the
requested resources to the pod. This usually happens when a spare GPU cannot be found on the node.

### Development on Linux

The OpenWebUI interface for a development deployment can be reached at the url
[http://chat-dev.soton.ac.uk](http://chat-dev.soton.ac.uk). K3s will take care of redirecting requests and load
balancing using Traefik. However, you will need to update the `/etc/hosts` file on your system for a local deployment,
to direct the URL to the IP address of the worker running the OpenWebUI pod. In K3s, you can find the address using:
to access it, e.g. for k3s find the IP for the node:

```bash
$ kubectl get nodes -o wide
NAME   STATUS   ROLES           AGE    VERSION        INTERNAL-IP    EXTERNAL-IP   OS-IMAGE             KERNEL-VERSION      CONTAINER-RUNTIME
r3x    Ready    control-plane   100m   v1.34.3+k3s1   192.168.0.40   <none>        Ubuntu 24.04.3 LTS   6.14.0-37-generic   containerd://2.1.5-k3s1
```

Then modify `/etc/hosts` with the INTERNAL-IP value:

```text
192.168.0.40 chat-dev.soton.ac.uk
```

### Development on macOS for non-LLM server related services

K3s is not available on macOS. You will need to either use Minikube (which doesn't work that magnificently either) or
use something like Docker Desktop which uses Kubeadm to create a single node cluster. As there is no NVIDIA GPU support
on macOS, you will also have to use an overlay to launch an Ollama server instead of vLLM.

```bash
kubectl apply -k overlays/ollama-dev
```

Since this uses Ollama instead, you cannot develop the vLLM service on macOS.
