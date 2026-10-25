# GEHealthcare-team1

## Backend

The backend is a FastAPI service located in `backend/`. See
[backend/README.md](backend/README.md) for setup, dev server, and test
instructions.

## UMF RTI

The UMF RTI capture is a headless, short-lived Kubernetes Job that reuses the
platform's RTI runtime image. It captures discovery/QoS metadata only (no sample
values). See:

- [collector/README.md](collector/README.md) — Java collector build/runtime
- [kubernetes/README.md](kubernetes/README.md) — prerequisites, RBAC, domains
- [backend/README.md](backend/README.md) — API and package contents

## Frontend

The React/Vite UI is in `frontend/`. Run `npm install` and `npm run dev` for the
development server, or `npm run build` for a production bundle.
