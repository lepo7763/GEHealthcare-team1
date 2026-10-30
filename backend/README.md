# IoMT Analysis Tool — Backend

FastAPI service for the IoMT Analysis Tool. It currently exposes:

- `GET /api/health` — liveness/readiness.
- `GET /api/environments/check` — Kubernetes reachability/authentication check.
- `GET /api/logs/progress` — per-service progress for the running collection.
- `GET /api/logs/zip` — container logs and/or a UMF RTI discovery capture.
- `GET /api/logs/demo.zip` — simulated package for UI development.
- `GET /api/logs/export` — Axone system log export in CSV or JSON.

## Requirements

- **Python 3.14** (any recent Python3 version should work, but 3.14 is ideal so everyone has the same version)
- **venv + pip**
- `kubectl` access to the cluster for live collection
- **JDK 17+** if the setup helper needs to build the UMF RTI collector JAR

## Setup

Run from inside `backend/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the dev server

Run from inside `backend/`:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Run the tests

Run from inside `backend/`:

```bash
pytest
```

The tests mock both the CoreV1 and BatchV1 clients and do not require a live
cluster.

## Container log collection

`GET /api/logs/zip` historically collected every container log in the cluster
and returned a zip with `manifest.json` and `logs/<namespace>/<pod>/<container>.log`.
That behavior is preserved. `include_previous=true` also fetches the previous
instance log for containers whose restart count is greater than zero.

## Directory Structure

This repository groups all parts of a certain feature under folders titled with
that feature name. The container log routing/schemas/service live in
`log_collection`; the UMF RTI Job/QoS logic lives in `umf_rti`; the
cross-service zip/manifest orchestration lives in `diagnostics`. Routers are
attached to the app in `main.py`.

## Axone log export

The Sessions page includes **Export Axone logs**. Select one device or all
devices, enter the local time range,
and choose CSV or JSON. An optional integer event category selects the event
variant of each query. Category names are not mapped to codes; confirm codes
with the team. A device/source UUID identifies an Axone device, not a pod or
container name.

The frontend calls `GET /api/logs/export` on this backend. The backend forwards
the request to the appropriate one of the eight endpoints in the
[Axone API guide](docs/log-export-api-guide.md). The original ZIP download is
still available at `GET /api/logs/zip`.

Set `AXONE_LOG_EXPORT_URL` to the Axone service's base URL (scheme, host, and
port only; no path prefix). The default is `http://axone-log-export-tcp:9200`.
For a backend in a different namespace, for example:

```powershell
$env:AXONE_LOG_EXPORT_URL = "http://axone-log-export-tcp.<namespace>.svc.cluster.local:9200"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run the backend as a pod inside the cluster so it can reach this internal
service. Kubernetes API credentials alone do not provide access to service DNS
or the cluster network. The browser calls the backend, so it does not need
direct access to the Axone service. Vite forwards `/api` requests to port 8000
in development; a production web server must also route `/api` to the backend.

Example backend request:

```text
GET /api/logs/export?scope=device&format=csv&deviceuuid=d4e5f6a7-1234-5678-9abc-def012345678&startTimestamp=2024-01-15T09:00:00.000&endTimestamp=2024-01-15T09:45:00.000
```

- `scope`: `device` (default) or `all`; device scope requires `deviceuuid`.
- `format`: `csv` (default) or `json`; both return a file download.
- `startTimestamp` and `endTimestamp`: local timestamps with seconds and optional
  millisecond precision, without a timezone suffix. End must be strictly later.
- One device: maximum 7 days. All devices: maximum 1 hour and matching hour
  components on both timestamps.
- `eventCategory`: optional integer; omit it for all events. Zero is a valid
  integer input; the upstream service determines which codes it recognizes.

Validation errors return a useful message. Upstream failures return 502,
connection failures 503, and timeouts 504. Each upstream request has a 60-second
timeout. Downloads are not cached.

## Kubernetes Cluster Authentication

Any feature that connects to the Kubernetes cluster requires Kubernetes API
authentication. For local access, SSH into the MiniEdge in Morgridge Hall and
copy `/etc/rancher/k3s/k3s.yaml` to your local machine's `~/.kube/config` file.
**Do not push this file to the GitHub repository because it contains unencrypted
credentials.** The Axone export proxy uses the internal HTTP service described
above.
