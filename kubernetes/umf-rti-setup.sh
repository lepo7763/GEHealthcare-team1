#!/usr/bin/env bash
# Provisions the Kubernetes ConfigMap and Secrets in 'iomt-integration'
# required by the UMF RTI diagnostic Job.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${IOMT_UMF_RTI_NAMESPACE:-iomt-integration}"
JAR_PATH="$REPO_ROOT/collector/build/umf-rti-collector.jar"
LICENSE_PATH="$REPO_ROOT/axone-umf-rtitools/docker/rti_license.dat"

echo "=== 1. Checking collector JAR and license file ==="
if [[ ! -f "$JAR_PATH" ]]; then
  echo "ERROR: Collector JAR not found at $JAR_PATH. Run ./collector/build.sh first."
  exit 1
fi
if [[ ! -f "$LICENSE_PATH" ]]; then
  echo "ERROR: RTI license not found at $LICENSE_PATH."
  exit 1
fi

echo "=== 2. Applying updated ResourceQuota and LimitRange in $NAMESPACE ==="
kubectl apply -f "$REPO_ROOT/kubernetes/iomt-integration-resources.yaml"

echo "=== 3. Creating/Updating ConfigMap 'umf-rti-qos' from 'pm' namespace ==="
TMP_QOS="$(mktemp)"
trap 'rm -f "$TMP_QOS" /tmp/sdds_dump.json' EXIT
kubectl get configmap axone-adminui-diagnosticsui-qos-comm-configmap -n pm \
  -o jsonpath='{.data.CommissioningQoS\.xml}' > "$TMP_QOS"

kubectl create configmap umf-rti-qos -n "$NAMESPACE" \
  --from-file=CommissioningQoS.xml="$TMP_QOS" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "=== 4. Creating/Updating Secret 'umf-rti-collector' ==="
kubectl create secret generic umf-rti-collector -n "$NAMESPACE" \
  --from-file=umf-rti-collector.jar="$JAR_PATH" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "=== 5. Creating/Updating Secret 'umf-rti-license' ==="
kubectl create secret generic umf-rti-license -n "$NAMESPACE" \
  --from-file=rti_license.dat="$LICENSE_PATH" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "=== 6. Checking Secret 'umf-rti-sdds' ==="
if [[ "${COPY_SDDS:-false}" == "true" ]]; then
  echo "WARNING: Copying live SDDS identity material from pm/axone-adminui-diagnosticsui-sdds-comm-configmap (Lab Fallback)."
  TMP_SDDS_DIR="$(mktemp -d)"
  for KEY in Commissioning_CA.cert.pem Commissioning_Governance.p7s Commissioning_Permission.p7s MDHEndPoint.cert.pem MDHEndPoint.key.pem; do
    kubectl get configmap axone-adminui-diagnosticsui-sdds-comm-configmap -n pm \
      -o jsonpath="{.data.${KEY//./\\.}}" > "$TMP_SDDS_DIR/$KEY"
  done
  kubectl create secret generic umf-rti-sdds -n "$NAMESPACE" \
    --from-file="$TMP_SDDS_DIR" \
    --dry-run=client -o yaml | kubectl apply -f -
  rm -rf "$TMP_SDDS_DIR"
else
  if kubectl get secret umf-rti-sdds -n "$NAMESPACE" >/dev/null 2>&1; then
    echo "Secret 'umf-rti-sdds' already exists in $NAMESPACE."
  else
    echo "NOTE: Secret 'umf-rti-sdds' does not exist yet."
    echo "Re-run with COPY_SDDS=true ./kubernetes/umf-rti-setup.sh to copy lab SDDS material."
  fi
fi

echo "=== Setup complete! Resources in $NAMESPACE: ==="
kubectl get cm,secret -n "$NAMESPACE"