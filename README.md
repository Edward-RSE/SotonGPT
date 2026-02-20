# SotonGPT

This is a repository containing the files used to deploy SotonGPT. Note that a GPU is required to deploy SotonGPT using
both Docker and Kubernetes.

## Deploying SotonGPT with Docker

An early and experimental version of SotonGPT can be deployed using Docker. **This is not the supported, or correct,
method of deployment for SotonGPT.**

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

More details about the K8s architecture can be found in
[kubernetes/README.md](https://github.com/Edward-RSE/SotonGPT/blob/main/kubernetes/README.md).

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

This will create a namespace `sotongpt` and deploy the base services: Open WebUI, Postgres and Ollama. To deploy an LLM
server, apply one of the models in the vLLM service directory:

```bash
kubectl apply -k kubernetes/vllm/qwen2_5-14b-instruct
```

You can check that the pods have been deployed and have started up correctly by using:

```bash
$ kubectl get pods -n sotongpt
NAME                                    READY   STATUS    RESTARTS   AGE
NAME                                                    READY   STATUS                     RESTARTS        AGE
ollama-background-tasks-deployment-545c5c57dc-w8hq5     1/1     Running                    1 (5h38m ago)   2d
ollama-model-loader-5mqsq                               0/1     Completed                  0               2d
openwebui-deployment-76bcf8f9c7-9z7h9                   1/1     Running                    1 (5h35m ago)   2d
postgres-deployment-7c47858d5f-48pmw                    1/1     Running                    1 (5h38m ago)   2d
vllm-qwen2-5-14b-instruct-deployment-5ccb868dc6-lbwb6   1/1     Running                    0               5h34m
```

If you see a status of anything other than "Running", you can check the event history of the pod using `kubectl describe
pod -n sotongpt <pod-name>`. If the vLLM pod is stuck in pending, it's possible that K3s has been unable to allocate the
requested resources to the pod. This usually happens when a spare GPU cannot be found on the node, of if a persistent
volume has not been configured correctly.

You can then access SotonGPT at [http://sotongpt.soton.ac.uk](http://sotongpt.soton.ac.uk).

## Monitoring of vLLM and the K3s cluster

To monitor the status of both the K3s cluster and the metrics of the vLLM servers, we use the kube-prometheus stack with
a Grafana dashboard. This can be deployed using a script in monitoring directory,

```bash
cd kubernetes/monitoring && ./helm-deploy.sh
```

To enable monitoring the metrics API endpoints of the vLLM servers, we need to configure a K8s Service Monitor:

```bash
cd kubernetes/monitoring && kubectl apply -f service-monitor-vllm.yaml
```

This Service Monitor will target any service with the label `app: vllm` and create a Grafana dashboard showing metrics
such as the token throughput and E2E latency. If there is no vLLM dashboard, you will need to import it manually using
the [pre-made JSON template](https://grafana.com/grafana/dashboards/23991-vllm/).

The dashboard has been configured to be accessible at
[http://dashboard.sotongpt.soton.ac.uk](http://dashboard.sotongpt.soton.ac.uk).

## Load testing the deployment

We have provided a script using [Locust](https://locust.io/) which can be used to load test the SotonGPT deployment.
This script will send requests to the chat completions endpoint to the available models, including sending requests to
the file uploads endpoint and using the file in the chat completion.

## Components of SotonGPT

### Open WebUI

SotonGPT uses [Open WebUI](https://openwebui.com/) to serve an interactive chat for non-technical users, and also serves
multiple API endpoints for more technical users. The API allows direct communication with the LLMs bypassing the chat
window, and acts as a centralised model hub with a consistent interface between Ollama and vLLM servers. SotonGPT uses
v0.8.3 of Open WebUI. The pod exposes port 8080, forwarded to port 80 via the ingress at
[http://sotongpt.soton.ac.uk](http://sotongpt.soton.ac.uk). Environment variables for performance are documented in the
deployment manifest. Only 1 replica of Open WebUI is run. If required, Open WebUI can run multiple replicas with Redis,
see [here](https://docs.openwebui.com/troubleshooting/multi-replica/) for more details.

#### PostgreSQL database

A PostgreSQL database with pgvector support is used as the relational and vector database backend. PostgreSQL stores
user information, chats, and file IDs. pgvector handles the processed embeddings for files uploaded. Without either of
these backends, Open WebUI is practically unusable with concurrent users.

#### Authenticated login

TODO: this will allow login using university credentials.

### Ollama

Ollama serves models for background tasks in Open WebUI, such as generating tags, titles, and embeddings for documents.
On deployment, a one-time job downloads the `gemma3:1b` and `nomic-embed-text` models used for text and embedding
generation, respectively. The Ollama service runs entirely on the CPU. It should therefore not be used to generate text
in a chat with a user.

### vLLM

vLLM is a high-performance inference engine designed specifically for large language models (LLMs). It serves as the
primary backend for handling user queries in SotonGPT, providing efficient and scalable inference for multiple model
variants. While Ollama is suitable for lightweight, background tasks, vLLM is the backbone of SotonGPT due to its
superior performance and scalability:

- **High throughput**: vLLM uses techniques like PagedAttention and continuous batching to process multiple requests
  simultaneously, achieving significantly higher throughput for inference.
- **Low latency**: vLLM has low time-to-first-token and inter-token latency, crucial for interactive chat applications.
- **Scalability**: Easily scales across multiple GPUs.
- **Model support**: Broad compatibility with popular open-source models, including those from Meta, Mistral, and Qwen.

However, there are several weaknesses with vLLM:

- **Activate energy**: Steeper learning curve for deployment and optimisation.
- **Complexity**: Requires more setup and configuration compared to Ollama.
- **Resource intensive**: Demands powerful GPUs and significant memory, increasing infrastructure costs.
- **Overhead**: Additional latency for very small models or single requests due to batching overhead.

Unlike Ollama, vLLM can only serve one model at once. Therefore each  directory in `kubernetes/services/vllm` is a
deployment for a different LLM. Each deployment includes:

- **deployment.yaml**: Defines pod specifications, resource limits, and container configuration.
- **pv.yaml** & **pvc.yaml**: Persistent storage for storing model weights and used for caching.
- **service.yaml**: Kubernetes service for discovery.
- **kustomization.yaml**: Kustomization file, defining the components of a vLLM deployment.

There is no default set of vLLM models. The currently provided models will all fit and perform *good enough* on either
one or two RTX 8000s.

#### Hardware and other limitations using vLLM

vLLM deployments are resource-intensive and state-of-the-art (SOTA) models also have specific requirements.
Understanding these constraints is essential when selecting models to deploy.  The RTX 8000 GPUs available on the
SotonGPT host are based on NVIDIA's Turing architecture (Compute Capability 7.5). This has significant implications for
model compatibility:

- No bfloat16 support: Turing GPUs do not support the bfloat16 data type. Most SOTA models released after 2023 are
  trained and released exclusively in bf16. vLLM must therefore use float16 instead, which degrades performance for some
  models.
- No FlashAttention 2: FA2 requires Compute Capability (CC) 8.0 (Ampere) or higher. The RTX 8000 has CC 7.5, meaning
  vLLM will fall back to slower attention implementations.

In practice, these architectural limitations mean that many models which would otherwise fit within the available VRAM
of something more modern like an L40, simply cannot be deployed on RTX 8000s regardless of their size. For example,
Google's gemma3:7b model does not load and nor does OpenAI's gpt-oss:20b.

#### VRAM requirements beyond model weights

Each RTX 8000 has 48 GB of VRAM, and a two-GPU tensor-parallel configuration (splitting the model weights across two
GPUs) provides 96 GB VRAM in total. However, the raw model weights represent only a fraction of the total VRAM consumed
by vLLM. vLLM's memory usage is dominated by two additional components:

- **KV cache**: The key-value cache stores the attention keys and values for all tokens in the current batch of active
requests. Its size scales with the number of concurrent users, the maximum context length, the architecture of the
models (such as number of layers) and the data type in use. For a model with a large context window and many concurrent
users, the KV cache can easily consume several times the memory used by the model weights themselves. For example, a 7B
parameter model loaded in float16 requires roughly 14 GB for weights alone, but serving 50 concurrent users with 8k
context lengths could demand an additional 20–40 GB of KV cache depending on the model architecture. vLLM pre-allocates
KV cache at startup (controlled by `--gpu-memory-utilization`), so the number of requests that can be batched
simultaneously is constrained by whatever VRAM remains after the weights are loaded.
- **CUDA and framework overhead**: PyTorch, the CUDA runtime, and vLLM's own internal buffers consume several gigabytes
of VRAM before any model is loaded. This overhead is typically in the range of 2–4 GB per GPU.

The practical consequence is that even a model whose weights comfortably fit within available VRAM may leave
insufficient room for a meaningful KV cache. This results in poor concurrency and high queuing latency under load, or
vLLM may even fail to load the model.

When evaluating whether a model is suitable for deployment, the question is not just "do the weights fit?" but "do the
weights fit and leave enough room for a KV cache?"

#### Model selection guidance

Given the above, models suitable for deployment on one or two RTX 8000s must satisfy all of the following: they must be
loadable in float16 (not exclusively bf16), must not require FP8 or other unsupported quantisation formats, must fit in
VRAM with sufficient headroom for the KV cache, and must not require Compute Capability 8.0+ features. In practice this
significantly restricts the choice of SOTA models, and newer flagship models from most providers are unlikely to be
compatible.

#### Current models

There are currently FIVE LLMs configured in `kubernetes/services/vllm` which have been tested to work on the SotonGPT
host and have acceptable interactive token throughput:

- Llama3 70B
- Qwen2.5 7B Instruct
- Qwen2.5 14B Instruct
- Qwen2.5 32B Instruct
- Qwen3 32B
