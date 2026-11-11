#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${UMF_RTI_NAMESPACE:-iomt-integration}"
ROUTER_NS="pm"
SECRET_NAME="umf-router-sdds"

echo "Locating axone-router pod in '${ROUTER_NS}'..."
ROUTER_POD=$(kubectl get pods -n "${ROUTER_NS}" -o name | grep axone-router | head -n 1 | cut -d/ -f2)

if [[ -z "${ROUTER_POD}" ]]; then
  echo "Error: axone-router pod not found."
  exit 1
fi

TMP_DIR=$(mktemp -d)
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "Copying SDDS certs from ${ROUTER_POD}..."
kubectl cp "${ROUTER_NS}/${ROUTER_POD}:/opt/axone-router/sdds" "${TMP_DIR}/sdds"
rm -rf "${TMP_DIR}/sdds/tmp"

echo "Applying Secret '${SECRET_NAME}' to '${NAMESPACE}'..."
# doing it this way instead of direct creation cuz idempotent
kubectl -n "${NAMESPACE}" create secret generic "${SECRET_NAME}" \
  --from-file="${TMP_DIR}/sdds" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Setup complete."