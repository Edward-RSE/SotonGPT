# Updating Open WebUI

This document covers the steps required to safely update Open WebUI to a newer version. If these steps are not followed,
you can corrupt the database tables.

1. Naviate into the directory containing the Open WebUI manifests (e.g. `/opt/sotongpt/kubernetes/services/openwebui`)

2. Take a note of the current settings of the deployment, so that you can restore anything changed. In particular, you
   will need to note how many replicas of Open WebUI are running and the number of Uvicorn workers (`UNVICORN_WORKERS`
   in `config-map.yaml`)

3. Scale Open WebUI down to 0 replicas, so no pods are running: `kubectl -n sotongpt scale deploy/openwebui
   --replicas=0`

4. Set `UVICORN_WORKERS: "1"` in `config-map.yaml` and apply it (`kubectl apply -f config-map.yaml`). As there are no
   pods running, you do not need to restart the deployment to apply the change.

5. Confirm that `ENABLE_DB_MIGRATIONS=True` or ommitted in `deployment.yaml` so Open WebUI will run any database
   migrations when it next starts up.

6. Update the image tag in `deployment.yaml`. For example, change `image: ghcr.io/open-webui/open-webui:v0.10.2` to
   `ghcr.io/open-webui/open-webui:v0.11.0` to udpate from v0.10.2 to 0.11.0.

7. Apply the deployment and scale up to exactly 1 replica, so the migration runs on the new image: `kubectl apply -f
   deployment.yaml && kubectl -n sotongpt scale deploy/openwebui --replicas=1`

8. Watch the pod logs to confirm the migration completes successfully before doing anything else: `kubectl -n sotongpt
   logs -f deploy/openwebui`

9. Once healthy, restore your original worker count in `config-map.yaml` (e.g. back to `"4"`), apply it, and restart:
   `kubectl apply -f config-map.yaml && kubectl -n sotongpt rollout restart deploy/openwebui`

10. Scale back up to your original replica count: `kubectl -n sotongpt scale deploy/openwebui --replicas=3`
