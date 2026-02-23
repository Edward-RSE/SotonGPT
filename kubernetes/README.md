# Kubernetes Deployment

## Directory structure

The deployment is organised into three main directories:

```
.
├── base                           # Core Kubernetes configurations (namespace, storage class, etc.)
├── monitoring                     # Monitoring setup for K3s and vLLM services using Prometheus and Grafana
└── services                       # Application services comprising SotonGPT
    ├── ollama                     # Ollama instance for background tasks in Open WebUI
    ├── vllm                       # vLLM inference servers, with each subdirectory representing a model deployment
    │   ├── llama3-70b
    │   ├── qwen2_5-14b-instruct
    │   ├── qwen2_5-32b-instruct
    │   ├── qwen2_5-7b-instruct
    │   ├── qwen3-32b
    │   └── tiny-llama
    ├── redis                       # Redis for state management between Open WebUI workers and replicas
    ├── openwebui                   # Open WebUI web chat interface
    └── postgres                    # PostgreSQL database with pgvector for Open WebUI
```

The `base` and `monitoring` directories contain infrastructure-related manifests for cluster setup and observability.
The `services` directory houses the core application components.

## Deployment diagram

TODO: this need finishing

![Deployment diagram](deployment_diagram.png)

