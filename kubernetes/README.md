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

## Configuration Files

`dev-resources.yaml` defines developer namespace resource quotas and container defaults.

`iomt-integration-resources.yaml` defines resource quotas and container defaults for shared integration testing.

`umf-rti-setup.sh` creates the UMF RTI ConfigMap/Secrets from the platform resources.

Updates to resource configurations should be coordinated with the team.
