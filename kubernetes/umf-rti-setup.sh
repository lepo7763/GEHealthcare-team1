#!/usr/bin/env bash
# Prepare the UMF RTI capture prerequisites in the integration namespace.
#
# This script does NOT build or push an image. It reuses the platform runtime
# image that already contains the RTI 6.1.2 libraries and Java API.
#
# First-time setup (from the repository root):
#   1. Install kubectl, Python 3, and JDK 17+.
#   2. Run: ./kubernetes/umf-rti-setup.sh
#      If collector/build/umf-rti-collector.jar is missing, the script extracts
#      the build-time nddsjava.jar from the platform image and builds the
#      collector automatically.
#
# Optional environment variables:
#   NAMESPACE            default iomt-integration
#   PLATFORM_NAMESPACE   default pm
#   IMAGE                platform runtime image
#   COPY_SDDS            default true; false keeps a dedicated SDDS identity
#                        instead of copying the diagnostics UI material
#                        (which includes MDHEndPoint.key.pem)
#   APPLY_RESOURCES      true to apply kubernetes/iomt-integration-resources.yaml
#   RTI_LICENSE_FILE     default axone-umf-rtitools/docker/rti_license.dat
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NAMESPACE="${NAMESPACE:-iomt-integration}"
PLATFORM_NAMESPACE="${PLATFORM_NAMESPACE:-pm}"
IMAGE="${IMAGE:-192.168.0.3:30003/spectro-images/us-artifactory.apps.ge-healthcare.net/docker-axone-all/axone-umfcompatibilitycheck:uw-badger-latest}"
QOS_CONFIGMAP="${QOS_CONFIGMAP:-umf-rti-qos}"
QOS_KEY="${QOS_KEY:-CommissioningQoS.xml}"
PLATFORM_QOS_CONFIGMAP="${PLATFORM_QOS_CONFIGMAP:-axone-adminui-diagnosticsui-qos-comm-configmap}"
SDDS_SECRET="${SDDS_SECRET:-umf-rti-sdds}"
COLLECTOR_SECRET="${COLLECTOR_SECRET:-umf-rti-collector}"
LICENSE_SECRET="${LICENSE_SECRET:-umf-rti-license}"
COLLECTOR_JAR="${COLLECTOR_JAR:-$ROOT_DIR/collector/build/umf-rti-collector.jar}"
NDDSJAVA_JAR="$ROOT_DIR/collector/lib/nddsjava.jar"
RTI_LICENSE_FILE="${RTI_LICENSE_FILE:-$ROOT_DIR/axone-umf-rtitools/docker/rti_license.dat}"
COPY_SDDS="${COPY_SDDS:-true}"
APPLY_RESOURCES="${APPLY_RESOURCES:-true}"

log() { printf '==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || fail "kubectl is required"

log "Using namespace $NAMESPACE and platform namespace $PLATFORM_NAMESPACE"
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || fail "namespace $NAMESPACE does not exist"
kubectl get namespace "$PLATFORM_NAMESPACE" >/dev/null 2>&1 || fail "namespace $PLATFORM_NAMESPACE does not exist"

if [[ "$APPLY_RESOURCES" == "true" ]]; then
  log "Applying integration namespace quota / LimitRange"
  kubectl apply -f "$ROOT_DIR/kubernetes/iomt-integration-resources.yaml"
else
  log "Skipping quota/LimitRange (set APPLY_RESOURCES=true to apply)"
fi

# ---------------------------------------------------------------------------
# Collector JAR
# ---------------------------------------------------------------------------
if [[ ! -f "$COLLECTOR_JAR" ]]; then
  if [[ ! -f "$NDDSJAVA_JAR" ]]; then
    log "Build-time nddsjava.jar not found; extracting it from the platform image"
    command -v python3 >/dev/null 2>&1 ||
      fail "python3 is required to extract collector/lib/nddsjava.jar"
    [[ -f "$ROOT_DIR/scripts/extract-nddsjava.py" ]] ||
      fail "scripts/extract-nddsjava.py is missing"
    python3 "$ROOT_DIR/scripts/extract-nddsjava.py" \
      --image "$IMAGE" \
      --output "$NDDSJAVA_JAR"
  fi
  log "Collector JAR not found; building it"
  [[ -x "$ROOT_DIR/collector/build.sh" ]] || fail "collector/build.sh is missing"
  "$ROOT_DIR/collector/build.sh"
fi

log "Creating/updating Secret $NAMESPACE/$COLLECTOR_SECRET"
kubectl create secret generic "$COLLECTOR_SECRET" -n "$NAMESPACE" \
  --from-file=umf-rti-collector.jar="$COLLECTOR_JAR" \
  --dry-run=client -o yaml | kubectl apply -f -

# ---------------------------------------------------------------------------
# QoS ConfigMap (read-only copy from the platform)
# ---------------------------------------------------------------------------
log "Copying $PLATFORM_NAMESPACE/$PLATFORM_QOS_CONFIGMAP -> $NAMESPACE/$QOS_CONFIGMAP"
QOS_DIR="$(mktemp -d)"
trap 'rm -rf "$QOS_DIR"' EXIT
kubectl get configmap "$PLATFORM_QOS_CONFIGMAP" -n "$PLATFORM_NAMESPACE" -o json |
  python3 -c '
import json, os, sys
data = json.load(sys.stdin).get("data", {})
key = sys.argv[2]
if key not in data:
    raise SystemExit(f"platform ConfigMap does not contain {key}")
with open(os.path.join(sys.argv[1], key), "w", encoding="utf-8") as handle:
    handle.write(data[key])
' "$QOS_DIR" "$QOS_KEY"
kubectl create configmap "$QOS_CONFIGMAP" -n "$NAMESPACE" \
  --from-file="$QOS_KEY=$QOS_DIR/$QOS_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

# ---------------------------------------------------------------------------
# SDDS identity
# ---------------------------------------------------------------------------
if [[ "$COPY_SDDS" == "true" ]]; then
  warn "Copying the diagnostics UI SDDS identity, including its private key,"
  warn "into $NAMESPACE/$SDDS_SECRET. Use a dedicated UMF RTI identity for"
  warn "shared or production environments."
  SDDS_DIR="$(mktemp -d)"
  kubectl get configmap axone-adminui-diagnosticsui-sdds-comm-configmap \
    -n "$PLATFORM_NAMESPACE" -o json |
    python3 -c '
import json, os, sys
data = json.load(sys.stdin).get("data", {})
required = [
    "Commissioning_CA.cert.pem",
    "Commissioning_Governance.p7s",
    "Commissioning_Permission.p7s",
    "MDHEndPoint.cert.pem",
    "MDHEndPoint.key.pem",
]
missing = [key for key in required if key not in data]
if missing:
    raise SystemExit("platform SDDS ConfigMap is missing: " + ", ".join(missing))
for key in required:
    with open(os.path.join(sys.argv[1], key), "w", encoding="utf-8") as handle:
        handle.write(data[key])
' "$SDDS_DIR"
  kubectl create secret generic "$SDDS_SECRET" -n "$NAMESPACE" \
    --from-file="$SDDS_DIR" \
    --dry-run=client -o yaml | kubectl apply -f -
  rm -rf "$SDDS_DIR"
else
  if kubectl get secret "$SDDS_SECRET" -n "$NAMESPACE" >/dev/null 2>&1; then
    log "Secret $NAMESPACE/$SDDS_SECRET already exists; leaving it unchanged"
  else
    fail "Secret $NAMESPACE/$SDDS_SECRET is missing. Create it for your
dedicated UMF RTI identity, or run again without COPY_SDDS=false to copy the
platform identity."
  fi
fi

# ---------------------------------------------------------------------------
# RTI license
# ---------------------------------------------------------------------------
[[ -f "$RTI_LICENSE_FILE" ]] || fail "RTI license not found at $RTI_LICENSE_FILE"
log "Creating/updating Secret $NAMESPACE/$LICENSE_SECRET"
kubectl create secret generic "$LICENSE_SECRET" -n "$NAMESPACE" \
  --from-file=rti_license.dat="$RTI_LICENSE_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

# ---------------------------------------------------------------------------
# Image availability (best effort)
# ---------------------------------------------------------------------------
log "Checking whether the platform image is already cached on a node"
if kubectl get nodes -o json | grep -qF "$IMAGE"; then
  log "Image is present in the node image cache"
else
  warn "Image was not found in the node image cache. The Job uses"
  warn "imagePullPolicy=IfNotPresent and will pull it from the registry."
fi

cat <<EOF

UMF RTI prerequisites are ready in namespace $NAMESPACE:
  ConfigMap/$QOS_CONFIGMAP
  Secret/$SDDS_SECRET
  Secret/$COLLECTOR_SECRET
  Secret/$LICENSE_SECRET

Image: $IMAGE
The capture Job uses imagePullPolicy=IfNotPresent and hostNetwork=false.
To run an ad-hoc capture, start the backend and call:

  curl -o umf.zip \\
    'http://127.0.0.1:8000/api/logs/zip?services=umf-rti&umf_domain_id=32&umf_duration_seconds=30'
EOF
