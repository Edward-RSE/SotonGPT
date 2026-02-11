
helm repo add \
    prometheus-community \
    https://prometheus-community.github.io/helm-charts
helm repo update
helm install \
    monitoring \
    prometheus-community/kube-prometheus-stack \
    -f values.yaml \
    --namespace monitoring \
    --create-namespace
