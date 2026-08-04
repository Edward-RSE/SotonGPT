# Launching an LLM on SotonGPT

You can launch an LLM in SotonGPT either as a standalone vLLM instance or through KubeAI. The approach you choose depends
on whether you want direct control over the serving pod or a more Kubernetes-native workflow.

## Using vLLM

A Helm chart in `kubernetes/helm/charts/vllm` can be used to launch standalone vLLM instances. This is a good option
when you want a single replica and want to manage the pod lifecycle manually. Example values files for supported models are
stored in `kubernetes/services/vllm/`.

To launch a model that already exists, run the install script:

```bash
cd kubernetes/services/vllm
./install-model.sh tiny-llama
```

To create and launch a new model, create a directory for the model and add a `values.yaml` file with the following
content, then adjust the settings as needed:

```yaml
# ---------------------------------------------------------------------------
# REQUIRED — must be provided at install time, no defaults
# ---------------------------------------------------------------------------
model:
  # Short name used to name the related pods, services, and other resources
  name: tiny-llama
  # Hugging Face model ID
  id: TinyLlama/TinyLlama-1.1B-Chat-v1.0

# ---------------------------------------------------------------------------
# OPTIONAL — sensible defaults, override only when needed
# ---------------------------------------------------------------------------
namespace: sotongpt
numReplicas: "1"

# Free-form vLLM CLI arguments. The model ID is prepended automatically.
vllmArgs:
  - --host
  - 0.0.0.0
  - --port
  - "8000"
  - --gpu-memory-utilization
  - "0.6"
  - --max-model-len
  - "1024"
  - --max-num-seqs
  - "1"
  - --dtype
  - float16

# Resource requirements for the pod
resources:
  limits:
    gpu: "1"
    cpu: "6"
    memory: 12Gi
  requests:
    gpu: "1"
    cpu: "4"
    memory: 4Gi
  storage: 6Gi
```

At minimum, provide the values under the `model` section. The remaining settings can be left at the Helm chart defaults.
Storage will be provisioned from the default storage class; on the SotonGPT cluster, this is Longhorn.

## Using KubeAI

KubeAI provides a higher-level Kubernetes workflow for launching models. It is particularly useful when you want a more
managed and scalable approach to serving models without manually handling each deployment detail.

Key advantages of KubeAI include:

- Simplified model lifecycle management through Kubernetes-native manifests.
- Automatic scaling based on configured replica settings and resource profiles.
- Cleaner separation between model definition, runtime arguments, and infrastructure requirements.
- Easier management of multiple models in a shared cluster environment.

After installing the service, you create a model manifest that describes the model, runtime arguments, and resource
profile, then apply it to the cluster.

Install KubeAI with the repository script:

```bash
export HF_TOKEN=YOUR_HF_TOKEN
cd kubernetes/services/kubeai
./install-kubeai.sh
```

Once installed, create a manifest such as the following:

```yaml
apiVersion: kubeai.org/v1
kind: Model
metadata:
  name: qwen3-32b
  namespace: sotongpt
spec:
  features: [TextGeneration]
  url: hf://abhishekchohan/Qwen3-32B-AWQ
  engine: VLLM
  args:
    - --quantization=awq_marlin
    - --dtype=float16
    - --tensor-parallel-size=2
    - --gpu-memory-utilization=0.90
    - --kv-cache-dtype=auto
    - --max-model-len=32768
    - --max-num-batched-tokens=32768
    - --max-num-seqs=64
    - --enable-chunked-prefill
    - --enable-prefix-caching
    - --enable-auto-tool-choice
    - --tool-call-parser=qwen3_coder
    - --reasoning-parser=qwen3
    - --default-chat-template-kwargs
    - '{"enable_thinking":false}'
  resourceProfile: nvidia-gpu-rtx8000:2
  minReplicas: 2
  cacheProfile: longhorn
```

Launch the model by applying the manifest:

```bash
kubectl apply -f model.yaml
```
