# IoMT Kubernetes Development Sandbox

## Overview

This directory contains the Kubernetes configuration for the GE HealthCare IoMT Analysis Tool capstone development sandbox.

The environment uses an existing single-node K3s cluster on the lab machine. Each developer has a dedicated namespace for testing, and the team has a shared namespace for integration testing.

## Accessing the Cluster

1. Connect your laptop to the approved lab network using Ethernet.
2. SSH into the lab machine using the provided credentials.
3. Verify Kubernetes connectivity:

`kubectl cluster-info`

All Kubernetes commands should be executed in the lab machine's SSH session unless otherwise specified.

Connection details and credentials are provided separately and should not be committed to Git.

## Development Namespaces

| Namespace | Purpose |
|---|---|
| `iomt-dev-1` through `iomt-dev-6` | Individual developer workspaces |
| `iomt-integration` | Shared application integration testing |

Each developer should work in their assigned namespace.

Namespaces provide logical separation but are not security boundaries in this setup. Developers currently share Kubernetes credentials and must avoid modifying one another's resources.

## Common Commands

List your running Pods:

`kubectl get pods -n iomt-dev-1`

Deploy a Kubernetes manifest:

`kubectl apply -f application.yaml -n iomt-dev-1`

Inspect a Pod:

`kubectl describe pod POD_NAME -n iomt-dev-1`

View container logs:

`kubectl logs POD_NAME -n iomt-dev-1`

Execute a command inside a container:

`kubectl exec -n iomt-dev-1 POD_NAME -- COMMAND`

Remove resources defined by a manifest:

`kubectl delete -f application.yaml -n iomt-dev-1`

Replace `iomt-dev-1` with your assigned namespace. Ensure manifests do not specify a conflicting namespace.

## Resource Limits

Each developer namespace has the following aggregate quotas:

| Resource | Quota |
|---|---|
| CPU requests | 200m |
| CPU limits | 500m |
| Memory requests | 128Mi |
| Memory limits | 256Mi |
| Pods | 2 |

The integration namespace has larger quotas: 1 CPU request, 2 CPU limits, 1Gi memory requests, 2Gi memory limits, and 4 Pods. Container defaults are 100m/256Mi requests and 500m/1Gi limits.

These initial limits are deliberately conservative because the lab machine also runs existing services. The UMF RTI Job requests 100m/256Mi and limits 1 CPU/1Gi, leaving room for the backend pod.

## Important Guidelines

- Only deploy resources into assigned development or integration namespaces.
- Do not modify existing GE HealthCare system namespaces.
- Remove temporary Pods when finished testing.
- Use approved container images. The lab environment may not have internet access.
- Do not run network scans or traffic captures against existing Portrait Mobile services without authorization.
- Do not commit credentials, internal infrastructure details, or sensitive diagnostic data.

## UMF RTI Capture

The UMF RTI service runs a short-lived Kubernetes **Job** in `iomt-integration`.
It does **not** build, push, or deploy a new image. It reuses the platform's
RTI runtime image:

```text
192.168.0.3:30003/spectro-images/us-artifactory.apps.ge-healthcare.net/docker-axone-all/axone-umfcompatibilitycheck:uw-badger-latest
```

That image is public-read in Harbor and already cached on the lab node. The
Job mounts the collector JAR, the RTI license, the platform QoS ConfigMap, and
the SDDS identity as read-only volumes. It uses `hostNetwork: false`, no
ServiceAccount token, a non-root UID (2017), and no added capabilities. The Job
is deleted immediately after the run, with `ttlSecondsAfterFinished` as a
safety net.

### First-time setup

From the repository root:

1. Install `kubectl`, Python 3, and JDK 17+.
2. Run the setup helper:

```bash
./kubernetes/umf-rti-setup.sh
```

If the collector JAR is not present, the helper extracts the build-time
`collector/lib/nddsjava.jar` from the platform image and builds
`collector/build/umf-rti-collector.jar` automatically. If you prefer to do it
manually:

```bash
python3 scripts/extract-nddsjava.py --output collector/lib/nddsjava.jar
./collector/build.sh
./kubernetes/umf-rti-setup.sh
```

Run the setup helper again after changing the collector source.

It creates/updates:

| Kind | Name | Purpose |
|---|---|---|
| ConfigMap | `umf-rti-qos` | Copy of the platform `CommissioningQoS.xml` |
| Secret | `umf-rti-sdds` | SDDS certificates/private key for the capture identity |
| Secret | `umf-rti-collector` | The collector JAR (`collector/build/umf-rti-collector.jar`) |
| Secret | `umf-rti-license` | `rti_license.dat` |

The helper fills the `umf-rti-sdds` Secret with the diagnostics UI SDDS material
(including `MDHEndPoint.key.pem`) from `pm`.

### Domains and discovery

- **Domain 32** is the live UMF domain in this lab and is the UI default.
- **Domain 12** is selectable, but the commissioning identity in this lab only
  permits domains 2 and 32. RTI security will reject a domain-12 participant
  with an actionable error unless a dedicated identity is provisioned.
- The discovery peer is
  `udpv4://axone-router-1.pm.svc.cluster.local` **without a port suffix**. RTI
  derives the port from the domain. In this RTI build a suffix such as
  `:15410` is treated as part of the hostname and fails DNS resolution. The
  backend still validates that the router Service exposes `domain-<id>-*`
  ports and records the expected port in the summary.
- The capture is discovery/QoS only. It does not read or write sample values.
  Probe readers use an always-false content filter (`1 = 0`), so user data is
  not delivered to the collector.

### Verification

After a capture, the Job/Pod should be gone:

```bash
kubectl get jobs,pods -n iomt-integration -l iomt-analysis-tool/service=umf-rti
```

## Configuration Files

`dev-resources.yaml` defines developer namespace resource quotas and container defaults.

`iomt-integration-resources.yaml` defines resource quotas and container defaults for shared integration testing.

`umf-rti-setup.sh` creates the UMF RTI ConfigMap/Secrets from the platform resources.

Updates to resource configurations should be coordinated with the team.
