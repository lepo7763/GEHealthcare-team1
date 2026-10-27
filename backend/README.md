# IoMT Analysis Tool — Backend

FastAPI service for the IoMT Analysis Tool. It currently exposes:

- `GET /api/health` — liveness/readiness.
- `GET /api/environments/check` — Kubernetes reachability/authentication check.
- `GET /api/logs/progress` — per-service progress for the running collection.
- `GET /api/logs/zip` — container logs and/or a UMF RTI discovery capture.
- `GET /api/logs/demo.zip` — simulated package for UI development.

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

## UMF RTI

Run the setup helper once, from the repository root:

```bash
./kubernetes/umf-rti-setup.sh
```

It creates the UMF RTI resources in `iomt-integration` and builds the collector
JAR if it is missing. Re-run it after changing the collector source.

Then request a capture:

```bash
curl -o diagnostics.zip \
  'http://127.0.0.1:8000/api/logs/zip?services=umf-rti&umf_domain_id=32&umf_duration_seconds=120'
```

See [`../kubernetes/README.md`](../kubernetes/README.md) for setup details and
[`../collector/README.md`](../collector/README.md) for the collector.

## Directory Structure

This repository groups all parts of a certain feature under folders titled with
that feature name. The container log routing/schemas/service live in
`log_collection`; the UMF RTI Job/QoS logic lives in `umf_rti`; the
cross-service zip/manifest orchestration lives in `diagnostics`. Routers are
attached to the app in `main.py`.

## Kubernetes Cluster Authentication

Any feature that connects to the Kubernetes cluster requires you to authenticate. To do this, ssh into the MiniEdge in Morgridge Hall and copy the contents of the `/etc/rancher/k3s/k3s.yaml` file to your local machine's `~/.kube/config` file. **Do not push this file to the GitHub repo as it contains unencrypted credentials.**
