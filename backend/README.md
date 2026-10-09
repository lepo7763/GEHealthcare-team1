# IoMT Analysis Tool — Backend

This is the first slice of the IoMT Analysis Tool: a minimal FastAPI service
that currently exposes a single health-check endpoint.

## Requirements

- Python 3.14
- venv + pip

## Setup

Run from inside `backend/`:

```bash
python3.14 -m venv .venv
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
