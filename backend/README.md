# IoMT Analysis Tool — Backend

FastAPI service for health checks, Kubernetes container log ZIP downloads, and
Axone system log exports in CSV or JSON.

## Requirements

- **Python 3.14** (any recent Python3 version should work, but 3.14 is ideal so everyone has the same version)
- **venv + pip**

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

## Example request

```bash
curl http://127.0.0.1:8000/api/health
```

## Directory Structure

This repository groups all parts of a certain feature under folders titled with that feature name. For example, the routing, schemas and service components of the container log collection feature are all in the `log_collection` directory, and the router is attached to the app in `main.py`.

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

The Kubernetes container ZIP export requires Kubernetes API authentication. For local access, ssh into the MiniEdge in Morgridge Hall and copy the contents of the `/etc/rancher/k3s/k3s.yaml` file to your local machine's `~/.kube/config` file. **Do not push this file to the GitHub repo as it contains unencrypted credentials.** The Axone export proxy uses the internal HTTP service described above.
