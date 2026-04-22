#!/bin/bash
set -ou pipefail

MODEL_DIR=$1
TEMP_NAME=${MODEL_DIR%/}
MODEL_NAME=${TEMP_NAME//_/-}

helm uninstall $MODEL_NAME -n sotongpt

# Wait for all pods with MODEL_NAME to terminate (timeout: 2 minutes)
echo "Waiting for pods with '$MODEL_NAME' to terminate..."
TIMEOUT=120
ELAPSED=0
INTERVAL=5

while true; do
    POD_COUNT=$(kubectl get pod -n sotongpt --no-headers 2>/dev/null \
        | grep "$MODEL_NAME" \
        | wc -l)

    if [ "$POD_COUNT" -eq 0 ]; then
        echo "All '$MODEL_NAME' pods have terminated."
        break
    fi

    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "Timeout: pods with '$MODEL_NAME' still running after ${TIMEOUT}s." >&2
        kubectl get pod -n sotongpt | grep "$MODEL_NAME" >&2
        exit 1
    fi

    echo "  ${POD_COUNT} pod(s) still terminating... (${ELAPSED}s elapsed)"
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

helm install $MODEL_NAME ../../helm/charts/vllm/ -f $MODEL_DIR/values.yaml -n sotongpt
kubectl get pod -n sotongpt
