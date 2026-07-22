#!/bin/bash

helm repo add kubeai https://kubeai.org
helm repo update

helm upgrade --install kubeai kubeai/kubeai \
	--wait \
	--timeout 10m \
	-n sotongpt \
	-f kubeai-values.yaml \
	--set secrets.huggingface.token=$HF_TOKEN \
