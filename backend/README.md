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
- `kubectl` access to the lab cluster for live collection
- **JDK 17+** only if you are building the UMF RTI collector JAR

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

## UMF RTI capture

Select the service with a repeated query parameter:

```bash
curl -o diagnostics.zip \
  'http://127.0.0.1:8000/api/logs/zip?services=container-logs&services=umf-rti&umf_domain_id=32&umf_duration_seconds=120'
```

The UMF RTI portion is a short-lived Kubernetes Job in `iomt-integration`. It
reuses the platform runtime image (no image build/push), mounts the collector
JAR/license/QoS/SDDS resources, joins the selected domain with
`AxoneNetQoSLibrary::umfgeneral_qos`, and writes NDJSON to its pod log. The
backend reads that log, writes the UMF RTI files, and deletes the Job. The Job
also has `ttlSecondsAfterFinished` as a safety net.

### Query parameters

| Parameter | Default | Validation | Notes |
|---|---|---|---|
| `services` | `container-logs` | `container-logs`, `umf-rti` | Repeat the parameter for multiple services. At least one is required. |
| `umf_domain_id` | `32` | 0–100 | 32 is the live UMF domain in the lab. Domain 12 requires a dedicated identity. |
| `umf_duration_seconds` | `120` | 30–600 | Elapsed seconds shown on the UMF RTI progress bar. |
| `umf_max_bytes` | 20 MiB | 1 KiB–100 MiB | Caps the collector log read from the pod. |

### Package contents

```text
manifest.json
logs/<namespace>/<pod>/<container>.log          # if container-logs selected
umf-rti/umf-rti-discovery.ndjson                # JSON records
umf-rti/umf-rti-summary.json                    # counts, peer, status
umf-rti/README.txt
```

`umf-rti-discovery.ndjson` contains one JSON object per line:

- `collector` — collector/RTI versions, profile, peer, local participant QoS.
- `participant` — GUID, name, domain, vendor, protocol, lease, locator counts.
- `topic` — topic/type name and whether it was observed live.
- `writer` / `reader` — topic, type, GUID, participant GUID/name, liveness, and
  a structured QoS object (reliability, durability, deadline, liveliness,
  history/ownership/presentation/partition where available).
- `summary` — domain, duration, and counts.

No sample values are read or written. Probe readers use an always-false content
filter (`1 = 0`), so user data is not delivered to the collector.

### UMF RTI implementation notes

- **Peer format:** the Job sets
  `NDDS_DISCOVERY_PEERS=udpv4://axone-router-1.pm.svc.cluster.local` with no
  port. RTI derives the port from the domain. A suffix such as `:15410` is
  treated as part of the hostname by this RTI build and fails DNS resolution.
  The backend still validates the router Service's `domain-<id>-*` ports and
  records the expected port in the summary.
- **Endpoint discovery:** DDS only exposes publication/subscription built-in
  data for endpoints with a local match. The collector creates short-lived
  local probe readers/writers on the platform-allowed topics (`umf_cfg`,
  `umfcmd_req`, `umfcmd_resp`, `umf_cfg_state`), reads the matched built-in
  data, and then deletes the participant. It does not read samples.
- **Topic names:** `TopicBuiltinTopicData` is not available for secure
  discovered topics in this RTI runtime. Topic records come from matched UMF
  endpoints plus the configured platform topic probes; the summary records the
  number of raw discovered topic handles as context.
- **Domain 12:** the commissioning identity in this lab permits domains 2 and
  32. A domain-12 capture fails with a security error unless a dedicated UMF
  RTI identity is provisioned. The UI shows a warning when domain 12 is chosen.

### Prerequisites

The capture needs these resources in `iomt-integration`:

| Kind | Name |
|---|---|
| ConfigMap | `umf-rti-qos` |
| Secret | `umf-rti-sdds` |
| Secret | `umf-rti-collector` |
| Secret | `umf-rti-license` |

Run `../kubernetes/umf-rti-setup.sh` to create/update them. For the lab fallback
identity, use `COPY_SDDS=true ../kubernetes/umf-rti-setup.sh`; this copies the
diagnostics UI SDDS material (including its private key) and is not a
production identity.

If the backend runs in-cluster, apply `../kubernetes/umf-rti-rbac.yaml` so the
`iomt-network-backend` ServiceAccount can create/delete Jobs and read pod logs.

### Environment variables

All settings have lab defaults in `app/umf_rti/config.py`. The most useful
overrides are:

| Variable | Default |
|---|---|
| `IOMT_UMF_RTI_IMAGE` | platform `axone-umfcompatibilitycheck:uw-badger-latest` image |
| `IOMT_UMF_RTI_NAMESPACE` | `iomt-integration` |
| `IOMT_UMF_RTI_DISCOVERY_PEERS` | resolved from `pm/axone-router-1` |
| `IOMT_UMF_RTI_QOS_CONFIGMAP` | `umf-rti-qos` |
| `IOMT_UMF_RTI_SDDS_SECRET` | `umf-rti-sdds` |
| `IOMT_UMF_RTI_COLLECTOR_SECRET` | `umf-rti-collector` |
| `IOMT_UMF_RTI_LICENSE_SECRET` | `umf-rti-license` |
| `IOMT_UMF_RTI_CPU_REQUEST` / `MEMORY_REQUEST` | `100m` / `256Mi` |
| `IOMT_UMF_RTI_CPU_LIMIT` / `MEMORY_LIMIT` | `1` / `1Gi` |
| `IOMT_UMF_RTI_JOB_TTL_SECONDS` | `600` |
| `IOMT_UMF_RTI_WAIT_TIMEOUT_SECONDS` | `360` |
| `IOMT_UMF_RTI_MAX_RECORDS` | `5000` |

## Building the collector

The collector source is in `../collector`. Build-time requirements are JDK 17+
and `collector/lib/nddsjava.jar`. Extract the JAR from the platform image with:

```bash
python3 ../scripts/extract-nddsjava.py \
  --output ../collector/lib/nddsjava.jar
```

Then:

```bash
../collector/build.sh
```

The output is `collector/build/umf-rti-collector.jar` (tens of KB). The
runtime image already contains `nddsjava.jar` and the platform UMF type
classes, so only the small collector JAR is mounted into the Job.

`kubernetes/umf-rti-setup.sh` performs both steps automatically when the
collector JAR is missing, so a fresh checkout only needs
`./kubernetes/umf-rti-setup.sh`.

## Directory Structure

This repository groups all parts of a certain feature under folders titled with
that feature name. The container log routing/schemas/service live in
`log_collection`; the UMF RTI Job/QoS logic lives in `umf_rti`; the
cross-service zip/manifest orchestration lives in `diagnostics`. Routers are
attached to the app in `main.py`.

## Kubernetes Cluster Authentication

Any feature that connects to the Kubernetes cluster requires you to authenticate. To do this, ssh into the MiniEdge in Morgridge Hall and copy the contents of the `/etc/rancher/k3s/k3s.yaml` file to your local machine's `~/.kube/config` file. **Do not push this file to the GitHub repo as it contains unencrypted credentials.**
