# Architecture

This document covers the current architecture of SotonGPT, as of 14 July 2026 and the second day of the PoC pilot.

** diagram to go here

## Open WebUI

SotonGPT uses [Open WebUI](https://openwebui.com/) to serve an interactive chat for non-technical users, and also API
endpoints for more technical users. The API allows direct communication with the LLMs bypassing the chat window, and
acts as a centralised model hub with a consistent interface between the Ollama and vLLM servers. The Open WebUI pod uses
port 8080, forwarded to port 80 via the ingress at [https://sotongpt.soton.ac.uk](https://sotongpt.soton.ac.uk).
Environment variables for performance are documented in the deployment manifest. Only 1 replica of Open WebUI is run. If
required, Open WebUI can run multiple replicas with Redis, see
[here](https://docs.openwebui.com/troubleshooting/multi-replica/) for more details.

## PostgreSQL database

A PostgreSQL database with pgvector support is used as the relational and vector database backend. PostgreSQL stores
user information, chats, and file IDs. pgvector handles the processed embeddings for files uploaded. Without either of
these backends, Open WebUI is practically unusable with concurrent users.

## Redis

Redis is used for sharing state between pod replicas and OpenWebUI workers. If neither of these are required, then
the Redis support can be disabled by commenting out the environment variables starting with `WEBSOCKET_` in the
deployment manfiest of Open WebUI.

## Ollama

Ollama serves models for background tasks in Open WebUI, such as generating tags, titles, and embeddings for documents.
On deployment, a one-time job downloads the `gemma3:1b` and `nomic-embed-text` models used for text and embedding
generation, respectively. The Ollama service runs entirely on the CPU. It should therefore not be used to generate text
in a chat with a user.

## vLLM

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

### Hardware and other limitations using vLLM

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

### VRAM requirements beyond model weights

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

## KubeAI

Not every model in SotonGPT runs as a hand-written vLLM deployment. A subset are instead managed through
[KubeAI](https://www.kubeai.org/), a Kubernetes operator that provisions and manages vLLM (and other) inference servers
declaratively, via a `Model` custom resource, rather than the raw `Deployment` + `PersistentVolume` + `Service` layout
used elsewhere in `kubernetes/services/vllm`. KubeAI sits alongside the standalone vLLM deployments described above; it
doesn't replace them.

### Installation

KubeAI is installed via its Helm chart:

```bash
helm repo add kubeai https://kubeai.org
helm repo update

helm upgrade --install kubeai kubeai/kubeai \
 --wait \
 --timeout 10m \
 -n sotongpt \
 -f kubeai-values.yaml \
 --set secrets.huggingface.token=$HF_TOKEN
```

The Hugging Face token is passed in at install time via `$HF_TOKEN` (rather than committed to the values file), since
several of the models KubeAI manages are pulled directly from the Hugging Face Hub at startup.

The accompanying `kubeai-values.yaml` configures several things:

- **`resourceProfiles.nvidia-gpu-rtx8000`**: defines the node selector (`nvidia.com/gpu.product: "Quadro-RTX-8000"`) and
  the CPU, memory, and GPU requests/limits for a single RTX 8000 "unit". Each `Model` manifest references this profile
  by name and requests a multiple of it (e.g. `nvidia-gpu-rtx8000:2` for a two-GPU, tensor-parallel model), so KubeAI
  knows how to schedule and size the pods it creates.
- **`open-webui.enabled: false`**: KubeAI ships with an optional Open WebUI subchart of its own. This is disabled, as
  SotonGPT already runs its own Open WebUI deployment (see above) rather than the one bundled with KubeAI.
- **`modelServers.VLLM.images`**: pins the vLLM image (`vllm/vllm-openai:v0.19.0`) that KubeAI uses for every model it
  serves through the VLLM engine, keeping the version consistent across all KubeAI-managed models.
- **`cacheProfiles.longhorn`**: configures model weight caching onto a shared Longhorn-backed filesystem
  (`/models/{model_name}/cache/`), so weights don't need to be re-downloaded from Hugging Face every time a pod restarts
  or is rescheduled.
- **`metrics.prometheusOperator.vLLMPodMonitor`**: enables a `PodMonitor` so the existing Prometheus Operator release
  scrapes vLLM metrics from KubeAI-managed pods, feeding the Grafana dashboards referenced elsewhere in this
  documentation.

### Model manifests

Each KubeAI-managed model is defined by its own `Model` resource, stored under `kubernetes/services/kubeai/models`. For
example, the Llama 3.1 8B manifest:

```yaml
apiVersion: kubeai.org/v1
kind: Model
metadata:
  name: llama-3.1-8b-instruct-fp16
  namespace: sotongpt
spec:
  features: [TextGeneration]
  url: hf://NousResearch/Meta-Llama-3.1-8B-Instruct
  engine: VLLM
  args:
    - --max-model-len=16384
    - --max-num-batched-token=16384
    - --gpu-memory-utilization=0.85
    - --dtype=float16
  resourceProfile: nvidia-gpu-rtx8000:1
  minReplicas: 2
  cacheProfile: longhorn
```

The `args` field is passed straight through to the underlying vLLM engine, in the same way the standalone deployments
configure vLLM directly; `resourceProfile` and `minReplicas` are what tell KubeAI how many GPUs to request per replica
and how many replicas to keep running. `--dtype=float16` reflects the same Turing-architecture constraint described
above: none of the KubeAI-managed models use bfloat16.

Models currently deployed via KubeAI:

| Model | Manifest | GPUs (tensor-parallel) | Quantisation | Context length | Min replicas | Notes |
|---|---|---|---|---|---|---|
| Llama 3.1 8B Instruct | `llama-3-1-instruct.yaml` | 1 | none (fp16) | 16,384 | 2 | Smallest model, single-GPU footprint |
| Qwen3.6 35B (non-reasoning) | `qwen3-6-non-reasoning.yaml` | 2 | AWQ | 131,072 | 2 | Thinking disabled by default (`enable_thinking: false`); speculative decoding and tool calling enabled |
| Qwen3.6 35B (reasoning) | `qwen3-6-reasoning.yaml` | 2 | AWQ | 131,072 | 4 | Same base model as above, with the `qwen3` reasoning parser enabled instead of thinking disabled; higher `minReplicas` to absorb reasoning workload |
| Qwen3 32B (reasoning) | `qwen3-32b.yaml` | 2 | AWQ | 32,768 | 2 | Reasoning parser and tool calling enabled |

A few points worth noting about these manifests:

- **AWQ quantisation** is what makes it feasible to run 32B–35B parameter models on a pair of RTX 8000s at all, trading
  a small amount of accuracy for a substantially smaller VRAM footprint compared to full-precision weights, leaving more
  headroom for KV cache (see the VRAM discussion above).
- **Speculative decoding** (`--speculative-config` with `qwen3_next_mtp`) is used on both Qwen3.6 35B models to improve
  token generation speed by predicting and verifying multiple tokens per step.
- **Chunked prefill and prefix caching** (`--enable-chunked-prefill`, `--enable-prefix-caching`) are enabled on all
  three larger models, which particularly benefits the long-context (131k token) Qwen3.6 deployments and repeated or
  shared-prefix conversations.
- **Tool calling** (`--enable-auto-tool-choice`, `--tool-call-parser=qwen3_coder`) is enabled on every model except the
  non-reasoning/reasoning distinction changes only how "thinking" is exposed, not whether tool calls are supported.
- The **non-reasoning and reasoning Qwen3.6 variants share the same underlying weights**
  (`hf://QuantTrio/Qwen3.6-35B-A3B-AWQ`) and are otherwise near-identical manifests; they're deployed as two separate
  `Model` resources purely to expose thinking on/off as distinct, independently scalable endpoints in Open WebUI.
Restarting or troubleshooting a KubeAI-managed model (including the trade-offs between deleting the whole `Model`
resource versus deleting a single misbehaving pod) is covered in the operations runbook rather than here.
