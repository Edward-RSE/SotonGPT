# SotonGPT

This is a repository containing the files used to deploy SotonGPT. Note that Helm and GPUs are required to deploy
SotonGPT.

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

