# UMF RTI Collector

Small Java 17 program that runs inside the platform's RTI runtime image. It
joins a UMF domain with the platform secure QoS profile and emits discovery/QoS
data as newline-delimited JSON. It does not read or write sample values.

## First-time setup

From `collector/`:

```bash
# 1. Extract the build-time RTI Java API from the platform image
python3 ../scripts/extract-nddsjava.py --output lib/nddsjava.jar

# 2. Build the collector JAR
./build.sh
```

Requirements:

- JDK 17+ (`java`, `javac`, `jar`)
- `lib/nddsjava.jar` — build-time only. The runtime image already has it, plus
  the native RTI libraries and platform UMF generated type classes; only
  `build/umf-rti-collector.jar` is mounted into the Job.

The build also runs the dependency-free self-tests in
`src/test/java/com/gehc/iomt/umfrti/CollectorSelfTest.java`.

> Running `../kubernetes/umf-rti-setup.sh` from the repository root does the
> extraction and build automatically if the collector JAR is missing.

## Run

Inside the platform image (the Job sets these environment variables):

```bash
export NDDS_QOS_PROFILES=/opt/axone-tools/qos/CommissioningQoS.xml
java -cp /opt/umf-rti/umf-rti-collector.jar:<platform-app.jar>:<nddsjava.jar> \
  -Djava.library.path=/opt/axone-umfcompatibilitycheck/lib \
  com.gehc.iomt.umfrti.UmfRtiCollector \
  --domain 32 \
  --duration 120 \
  --qos-file /opt/axone-tools/qos/CommissioningQoS.xml \
  --qos-profile AxoneNetQoSLibrary::umfgeneral_qos
```

`--peer` can add a discovery peer explicitly. Prefer
`NDDS_DISCOVERY_PEERS=udpv4://axone-router-1.pm.svc.cluster.local` (no port
suffix): RTI derives the port from the domain, and this RTI build treats
`host:port` as a hostname.

## Output

One JSON object per line on stdout:

- `collector` — versions, profile, peer, local participant QoS.
- `participant` — discovered participants.
- `topic` — observed/configured UMF topics.
- `writer` / `reader` — matched remote endpoints, GUIDs, liveness, QoS.
- `summary` — counts and capture metadata.
- `error` — fatal error record (non-zero exit).

RTI stderr and internal collector warnings stay in the backend pod log for
diagnostics. They are not copied into the output package.

## Endpoint probes

DDS only exposes publication/subscription built-in data for endpoints with a
local match. On creation the collector makes short-lived local probe endpoints
for the platform-allowed UMF topics:

| Topic | Reader | Writer | QoS profile |
|---|---|---|---|
| `umf_cfg` | yes, `1 = 0` filter | no | `umfcfgnrt_qos` |
| `umfcmd_req` | yes, `1 = 0` filter | yes | `umfcfgnrt_qos` / `umfcmd_qos` |
| `umfcmd_resp` | yes, `1 = 0` filter | yes | `umfcfgnrt_qos` / `umfcmd_qos` |
| `umf_cfg_state` | no | yes | `umfcfgnrt_state_qos` |

The probe readers use an always-false content filter so no user samples are
delivered. Probe writers are never written to. All probe entities are deleted
when the participant is deleted.

The platform generated type classes are loaded reflectively from the app JAR
on the classpath. If that JAR is absent, the collector still reports
participants/topic handles and records a warning that endpoint discovery is
unavailable.

## Limitations

- `TopicBuiltinTopicData` is not readable for secure discovered topics in this
  runtime; topic names come from matched endpoints and the configured probes.
- The lab commissioning identity permits domains 2 and 32. Domain 12 needs a
  dedicated UMF RTI identity.
- Discovery is filtered by the RTI security permissions; only topics the
  identity may read/write are visible as endpoints.
