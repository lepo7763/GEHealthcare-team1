#!/usr/bin/env bash
# Compiles the UMF RTI Java collector into a lightweight JAR (<20 KB)
# that gets mounted into the runtime Pod via a Kubernetes Secret.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

JAR_DEP="lib/nddsjava.jar"
if [[ ! -f "$JAR_DEP" ]]; then
  echo "ERROR: $JAR_DEP not found."
  echo "Run 'python3 scripts/extract-nddsjava.py' from the repo root first."
  exit 1
fi

rm -rf build
mkdir -p build/classes

echo "Compiling UmfRtiCollector with JDK 17..."
javac --release 17 \
  -cp "$JAR_DEP" \
  -d build/classes \
  $(find src/main/java -name '*.java')

echo "Packaging build/umf-rti-collector.jar..."
jar --create \
  --file build/umf-rti-collector.jar \
  --main-class com.gehc.iomt.umfrti.UmfRtiCollector \
  -C build/classes .

ls -lh build/umf-rti-collector.jar
echo "Build complete!"