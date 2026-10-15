# IoMT Analysis Tool — Backend

This is the first slice of the IoMT Analysis Tool: a minimal FastAPI service
that currently exposes a single health-check endpoint.

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

## Kubernetes Cluster Authentication

Any feature that connects to the Kubernetes cluster requires you to authenticate. To do this, ssh into the MiniEdge in Morgridge Hall and copy the contents of the `/etc/rancher/k3s/k3s.yaml` file to your local machine's `~/.kube/config` file. **Do not push this file to the GitHub repo as it contains unencrypted credentials.**