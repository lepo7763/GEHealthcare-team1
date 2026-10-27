# Local development and live Axone testing

This guide runs the frontend and backend on a Windows laptop while forwarding
the Axone log service from the GE HealthCare Kubernetes cluster to local port
9200.

## What runs where

Keep these three PowerShell terminals open during a test session:

| Terminal | Runs on | Purpose |
|---|---|---|
| 1 | Windows | `kubectl port-forward` from local port 9200 to Axone |
| 2 | Windows | FastAPI backend on port 8000 |
| 3 | Windows | Vite frontend, normally on port 5173 |

The working request path is:

```text
Browser -> Vite /api proxy -> FastAPI :8000 -> localhost:9200
        -> Kubernetes port-forward -> Axone service :9200
```

SSH local forwarding is not used because the edge host currently rejects it
with `administratively prohibited`.

## Prerequisites

- An authorized account on the edge host.
- Ethernet access to the edge host. The address used during this setup was
  `192.168.0.3`; use the current address if it changes.
- Python 3.13 or newer, Node.js/npm, and Git installed on Windows.
- The repository at
  `C:~\GEHealthcare-team1`.
- Permission to read the k3s kubeconfig and port-forward the Axone service.

## One-time Windows setup

### 1. Install kubectl

```powershell
winget install -e --id Kubernetes.kubectl
```

Open a new PowerShell window and verify it:

```powershell
kubectl version --client
```

### 2. Copy the cluster kubeconfig

Use a separate file so an existing Kubernetes configuration is not replaced:

```powershell
New-Item -ItemType Directory -Force "$HOME\.kube" | Out-Null

ssh gehc@192.168.0.3 "sudo -n cat /etc/rancher/k3s/k3s.yaml" |
    Set-Content -Encoding utf8 "$HOME\.kube\gehc-k3s.yaml"
```

Restrict the file so only the current Windows user can read or modify it:

```powershell
icacls "$HOME\.kube\gehc-k3s.yaml" /inheritance:r /grant:r "${env:USERNAME}:(R,W)"
```

The original k3s file normally points to `127.0.0.1`, meaning the edge host
itself. Change only the kubeconfig server address to the Ethernet address:

```powershell
$configPath = "$HOME\.kube\gehc-k3s.yaml"
$edgeIp = "192.168.0.3"
$configText = Get-Content -Raw $configPath
$configText = $configText -replace 'server:\s+https://[^:]+:6443', "server: https://${edgeIp}:6443"
$configText | Set-Content -NoNewline -Encoding utf8 $configPath
```

Select this kubeconfig for the current PowerShell window:

```powershell
$env:KUBECONFIG = "$HOME\.kube\gehc-k3s.yaml"
```

Verify cluster access:

```powershell
kubectl config view --minify
kubectl get nodes
kubectl -n pm get endpoints axone-log-export-tcp
```

The expected node is `Ready`, and the Axone endpoint should include port 9200.
An Endpoints deprecation warning from newer Kubernetes versions is harmless for
this test.

### What is the protected file?

`C:~\.kube\gehc-k3s.yaml` is a Kubernetes access file, commonly
called a kubeconfig. It tells `kubectl` where the cluster is and contains a
client certificate and private key that prove the user is allowed to access it.
In simple terms, it is both the cluster address and a login credential. Keep it
private, do not send it to anyone, and never commit it to Git.

## One-time project setup

### Backend

From PowerShell:

```powershell
cd C:~\GEHealthcare-team1\backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Python 3.14 may be used instead when installed.

### Frontend

```powershell
cd C:~\GEHealthcare-team1\frontend
npm ci
```

## Start a test session

### Terminal 1: Kubernetes port-forward

Open PowerShell and select the kubeconfig:

```powershell
$env:KUBECONFIG = "$HOME\.kube\gehc-k3s.yaml"
kubectl get nodes
kubectl -n pm port-forward service/axone-log-export-tcp 9200:9200
```

Leave this terminal running. Expected output:

```text
Forwarding from 127.0.0.1:9200 -> 9200
```

If port 9200 is already occupied, identify its owner instead of stopping an
unknown process:

```powershell
$listener = Get-NetTCPConnection -LocalPort 9200 -State Listen
$listener | Select-Object LocalAddress, LocalPort, OwningProcess
Get-Process -Id $listener.OwningProcess
```

Close an obsolete SSH or forwarding terminal with `Ctrl+C`, then retry the
port-forward.

### Terminal 2: backend

```powershell
cd C:~\GEHealthcare-team1\backend
.\.venv\Scripts\Activate.ps1
$env:AXONE_LOG_EXPORT_URL = "http://127.0.0.1:9200"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Set `AXONE_LOG_EXPORT_URL` in the same terminal before starting Uvicorn. Leave
the backend running.

### Terminal 3: frontend

```powershell
cd C:~\GEHealthcare-team1\frontend
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`.

## Verify every layer

Use another local PowerShell terminal.

Check the backend and Vite proxy:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://localhost:5173/api/health
```

Both should return `status: ok`. This proves the local applications work but
does not by itself prove Axone connectivity.

Check Axone directly through the Kubernetes forward:

```powershell
curl.exe -sS -o NUL -w "Axone HTTP %{http_code}; bytes=%{size_download}`n" "http://127.0.0.1:9200/getLogsByDate?startTimestamp=2026-10-25T13%3A00%3A00.000&endTimestamp=2026-10-25T13%3A01%3A00.000"
```

Check the same type of export through the backend:

```powershell
curl.exe -sS -o NUL -w "Backend HTTP %{http_code}; bytes=%{size_download}`n" "http://127.0.0.1:8000/api/logs/export?scope=all&format=json&startTimestamp=2026-10-25T13%3A00%3A00.000&endTimestamp=2026-10-25T13%3A01%3A00.000"
```

Both should report HTTP 200 before testing through the browser.

## Test the Axone Logs page

Start with:

- **All devices**
- **JSON**
- Event category left blank
- A known populated 5-15 minute historical interval
- Start and end times within the same clock hour

The UUID displayed as placeholder text in the one-device input is example data,
not a confirmed device on the cluster. Obtain a real device/source UUID from a
known record before testing one-device exports.

A successful download is not enough to prove the data is correct. Open the file
and confirm the expected UUID, description, category, severity, and timestamp.
An empty JSON array or header-only CSV is a successful but empty result.

## Stop the session

Press `Ctrl+C` in each of these terminals:

1. Frontend
2. Backend
3. Kubernetes port-forward

The kubeconfig remains on disk for later sessions. The `$env:KUBECONFIG`
assignment applies only to the PowerShell process where it was set, so set it
again when opening a new port-forward terminal.

## Troubleshooting

- `Unable to listen on port 9200`: an old tunnel or process still owns the port.
- `HTTP 000`: no HTTP response was received; check the port-forward terminal.
- Backend `503`: the backend could not complete its connection to Axone.
- Backend `502`: Axone returned a server-side failure.
- Backend `504`: the Axone request exceeded the backend's 60-second timeout.
- `x509` error from `kubectl`: stop and obtain a kubeconfig/certificate valid for
  the edge Ethernet address; do not disable TLS verification.
- No new `Handling connection for 9200` line: the request did not reach the
  Kubernetes port-forward.

