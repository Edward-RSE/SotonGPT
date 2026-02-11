helm upgrade monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring \
  -f values.yaml
