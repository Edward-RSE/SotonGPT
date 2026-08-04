# Monitoring SotonGPT via Grafana

To monitor the various components of SotonGPT, the repository includes service and pod monitors in the
`kubernetes/monitoring` directory, along with the Grafana dashboard JSON files. This setup requires the
[Kube-Prometheus-Grafana](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack)
stack to be installed on the Kubernetes cluster. Installation of this stack is typically expected to follow the deployment
process in the [soton-k8s](https://github.com/southampton-RSG/soton-k8s) repository.

- `vllm-pod-monitor.yaml`: a pod monitor that scrapes the `/metrics` endpoint for each standalone vLLM instance. The
  KubeAI deployment via Helm also deploys its own pod monitor. This is accompanied by the `vllm-dashboard.json`
  Grafana dashboard, which aggregates metrics from both the standalone vLLM instances and the KubeAI vLLMs.

- `openwebui-exporter.yaml`: a service monitor that scrapes the Open WebUI analytics and admin API endpoints.
  It is accompanied by the `openwebui-dashboard.json` Grafana dashboard and requires a valid admin API key configured
  via the `OPENWEBUI_API_KEY` secret.

- `otel-service-monitor.yaml`: a service monitor that scrapes the OpenTelemetry endpoints exposed by Open WebUI.
  The metrics provided through the OpenTelemetry protocol are currently quite limited. This service monitor is
  accompanied by the `openwebui-otel-dashboard.json` dashboard.
