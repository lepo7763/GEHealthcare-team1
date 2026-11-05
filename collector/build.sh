#!/usr/bin/env bash
# Build the headless UMF RTI collector and run its dependency-free self-tests.
#
# Build-time requirements:
#   - JDK 17+ (java, javac and jar on PATH)
#   - collector/lib/nddsjava.jar (extracted from the platform runtime image)
#
# The runtime image already contains nddsjava.jar and the UMF type classes, so
# only the small collector JAR produced here is mounted into the capture Job.
set -euo pipefail

cd "$(dirname "$0")"

LIB_JAR="lib/nddsjava.jar"
BUILD_DIR="build"
CLASSES_DIR="$BUILD_DIR/classes"
TEST_CLASSES_DIR="$BUILD_DIR/test-classes"
OUT_JAR="$BUILD_DIR/umf-rti-collector.jar"

if ! command -v javac >/dev/null 2>&1; then
  echo "error: javac not found; install JDK 17 or newer" >&2
  exit 1
fi

JAVAC_VERSION="$(javac -version 2>&1)"
case "$JAVAC_VERSION" in
  javac\ 1[7-9]*|javac\ [2-9][0-9]*) ;;
  *)
    echo "error: JDK 17 or newer is required (found $JAVAC_VERSION)" >&2
    exit 1
    ;;
esac

if [[ ! -f "$LIB_JAR" ]]; then
  cat >&2 <<'EOF'
error: collector/lib/nddsjava.jar is missing.

Extract it from the platform runtime image at build time, for example:

  python3 scripts/extract-nddsjava.py \
    --image 192.168.0.3:30003/spectro-images/us-artifactory.apps.ge-healthcare.net/docker-axone-all/axone-umfcompatibilitycheck:uw-badger-latest \
    --output collector/lib/nddsjava.jar

or, when you have kubectl access:

  kubectl cp pm/<platform-pod>:/opt/axone-umfcompatibilitycheck/lib/nddsjava.jar \
    collector/lib/nddsjava.jar

The JAR is a build-time dependency only; the runtime image already has it.
EOF
  exit 1
fi

rm -rf "$CLASSES_DIR" "$TEST_CLASSES_DIR" "$OUT_JAR"
mkdir -p "$CLASSES_DIR" "$TEST_CLASSES_DIR"

# shellcheck disable=SC2046
javac --release 17 -cp "$LIB_JAR" -d "$CLASSES_DIR" \
  $(find src/main/java -name '*.java' | sort)

# shellcheck disable=SC2046
javac --release 17 -cp "$LIB_JAR:$CLASSES_DIR" -d "$TEST_CLASSES_DIR" \
  $(find src/test/java -name '*.java' | sort)

java -cp "$LIB_JAR:$CLASSES_DIR:$TEST_CLASSES_DIR" \
  com.gehc.iomt.umfrti.CollectorSelfTest

jar --create --file "$OUT_JAR" \
  --main-class com.gehc.iomt.umfrti.UmfRtiCollector \
  -C "$CLASSES_DIR" .

echo "built $OUT_JAR ($(wc -c < "$OUT_JAR") bytes)"
