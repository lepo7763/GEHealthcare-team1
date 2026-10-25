package com.gehc.iomt.umfrti;

import com.rti.dds.domain.DomainParticipant;
import com.rti.dds.domain.DomainParticipantFactory;
import com.rti.dds.domain.DomainParticipantQos;
import com.rti.dds.domain.builtin.ParticipantBuiltinTopicData;
import com.rti.dds.infrastructure.InstanceHandleSeq;
import com.rti.dds.infrastructure.InstanceHandle_t;
import com.rti.dds.infrastructure.StatusKind;
import com.rti.ndds.config.LogVerbosity;
import com.rti.ndds.config.Logger;
import com.rti.ndds.config.Version;

import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Headless UMF RTI discovery collector.
 *
 * <p>Joins the selected UMF domain with the platform's secure QoS profile,
 * discovers participants, and uses short-lived local probe endpoints to make
 * RTI report the remote UMF writers/readers and their QoS.  Only discovery and
 * QoS data is emitted as newline-delimited JSON on stdout.  No sample values
 * are read or written.</p>
 */
public final class UmfRtiCollector {

    private static final String COLLECTOR_VERSION = "1.0.0";
    private static final int DEFAULT_DOMAIN = 32;
    private static final int DEFAULT_DURATION = 120;
    private static final int MAX_RECORDS_DEFAULT = 5000;
    private static final long POLL_INTERVAL_MILLIS = 2000L;

    private final int domain;
    private final int durationSeconds;
    private final String qosFile;
    private final String qosProfile;
    private final String peer;
    private final int maxRecords;
    private final boolean noProbes;

    private final DiscoverySnapshot snapshot = new DiscoverySnapshot();
    private final Map<String, String> participantNames = new LinkedHashMap<>();
    private final PrintWriter out = new PrintWriter(System.out, true);
    private int emittedRecords;
    private boolean recordLimitWarned;
    private boolean topicDataWarningAdded;

    private UmfRtiCollector(int domain, int durationSeconds, String qosFile,
            String qosProfile, String peer, int maxRecords, boolean noProbes) {
        this.domain = domain;
        this.durationSeconds = durationSeconds;
        this.qosFile = qosFile;
        this.qosProfile = qosProfile;
        this.peer = peer;
        this.maxRecords = maxRecords;
        this.noProbes = noProbes;
    }

    public static void main(String[] args) {
        Options options;
        try {
            options = Options.parse(args);
        } catch (IllegalArgumentException e) {
            Map<String, Object> error = errorRecord("Invalid collector arguments: " + e.getMessage());
            System.out.println(Json.write(error));
            System.out.flush();
            System.exit(64);
            return;
        }

        Logger.get_instance().set_verbosity(options.verbose
                ? LogVerbosity.NDDS_CONFIG_LOG_VERBOSITY_STATUS_REMOTE
                : LogVerbosity.NDDS_CONFIG_LOG_VERBOSITY_ERROR);

        UmfRtiCollector collector = new UmfRtiCollector(options.domain, options.duration,
                options.qosFile, options.qosProfile, options.peer,
                options.maxRecords, options.noProbes);
        int exitCode = collector.run();
        System.exit(exitCode);
    }

    private int run() {
        Instant startedAt = Instant.now();
        long startedNanos = System.nanoTime();
        DomainParticipantFactory factory = null;
        DomainParticipant participant = null;
        int exitCode = 0;
        try {
            if (!Files.isReadable(Path.of(qosFile))) {
                snapshot.addWarning("QoS file is not readable: " + qosFile
                        + ". RTI will use NDDS_QOS_PROFILES or its default profiles.");
            }
            factory = DomainParticipantFactory.get_instance();
            DomainParticipantQos participantQos = new DomainParticipantQos();
            String[] profile = splitProfile(qosProfile);
            factory.get_participant_qos_from_profile(participantQos, profile[0], profile[1]);
            participant = factory.create_participant(domain, participantQos, null,
                    StatusKind.STATUS_MASK_NONE);
            if (participant == null) {
                throw new IllegalStateException("RTI returned a null DomainParticipant for domain " + domain);
            }
            if (peer != null && !peer.isBlank()) {
                try {
                    participant.add_peer(peer);
                } catch (Throwable t) {
                    snapshot.addWarning("Could not add discovery peer " + peer + ": " + t.getMessage());
                }
            }

            emitLocalParticipant(participant, participantQos);

            List<EndpointProbe> probes = List.of();
            if (!noProbes) {
                probes = EndpointProbe.createAll(participant, factory,
                        profile[0], "iomt-umf-rti-probe", snapshot.warnings());
                if (probes.isEmpty()) {
                    snapshot.addWarning("No UMF endpoint probes could be created. "
                            + "Participant discovery is still captured, but UMF writers/readers "
                            + "cannot be reported. Ensure the platform UMF type classes are on "
                            + "the Java classpath (the platform app JAR is included by the Job).");
                }
            } else {
                snapshot.addWarning("Endpoint probing was disabled (--no-probes); "
                        + "only participants and discovered topic handles are reported.");
            }

            long deadline = startedNanos + durationSeconds * 1_000_000_000L;
            while (System.nanoTime() < deadline) {
                pollParticipants(participant);
                pollTopicHandles(participant);
                for (EndpointProbe probe : probes) {
                    probe.collect(snapshot, participantNames, this::emit);
                }
                long remainingMillis = Math.max(0L,
                        (deadline - System.nanoTime()) / 1_000_000L);
                sleep(Math.min(POLL_INTERVAL_MILLIS, remainingMillis));
            }

            // One final poll catches endpoints discovered just before the deadline.
            pollParticipants(participant);
            for (EndpointProbe probe : probes) {
                probe.collect(snapshot, participantNames, this::emit);
            }
            addMissingEndpointParticipants();
            addConfiguredTopics();
            emitSummary(startedAt, startedNanos, probes.size());
        } catch (Throwable t) {
            Map<String, Object> error = errorRecord("UMF RTI collection failed on domain "
                    + domain + ": " + messageOf(t));
            error.put("error_class", t.getClass().getName());
            error.put("domain", domain);
            error.put("hint", hintFor(t));
            emit(error, true);
            exitCode = 2;
        } finally {
            if (participant != null) {
                try {
                    participant.delete_contained_entities();
                } catch (Throwable ignored) {
                    // Best effort: probe entities can outlive a failed cleanup.
                }
            }
            if (factory != null && participant != null) {
                try {
                    factory.delete_participant(participant);
                } catch (Throwable ignored) {
                    // The process is about to exit; do not mask the collection result.
                }
            }
            out.flush();
        }
        return exitCode;
    }

    private void emitLocalParticipant(DomainParticipant participant, DomainParticipantQos qos) {
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("type", "collector");
        record.put("collector_version", COLLECTOR_VERSION);
        record.put("rti_version", rtiVersion());
        record.put("domain", domain);
        record.put("duration_seconds", durationSeconds);
        record.put("qos_profile", qosProfile);
        record.put("qos_file", qosFile);
        record.put("peer", peer);
        record.put("local_participant_qos", QosFormatter.localParticipant(qos));
        record.put("content_filtered_readers", true);
        record.put("sample_values_captured", false);
        emit(record, true);
    }

    private void pollParticipants(DomainParticipant participant) {
        InstanceHandleSeq handles = new InstanceHandleSeq();
        try {
            participant.get_discovered_participants(handles);
        } catch (Throwable t) {
            snapshot.addWarning("Could not list discovered participants: " + t);
            return;
        }
        for (int i = 0; i < handles.size(); i++) {
            InstanceHandle_t handle = (InstanceHandle_t) handles.get(i);
            ParticipantBuiltinTopicData data = new ParticipantBuiltinTopicData();
            try {
                participant.get_discovered_participant_data(data, handle);
            } catch (Throwable t) {
                snapshot.addWarning("Could not read discovered participant data: " + t);
                continue;
            }
            Map<String, Object> record = QosFormatter.participant(data);
            record.put("type", "participant");
            record.put("source", "discovery");
            String guid = (String) record.get("guid");
            if (guid != null && snapshot.addParticipant(record)) {
                Object name = record.get("name");
                if (name != null) {
                    participantNames.put(guid, String.valueOf(name));
                }
                emit(record);
            }
        }
    }

    private void pollTopicHandles(DomainParticipant participant) {
        InstanceHandleSeq handles = new InstanceHandleSeq();
        try {
            participant.get_discovered_topics(handles);
        } catch (Throwable t) {
            snapshot.addWarning("Could not list discovered topics: " + t);
            return;
        }
        snapshot.setDiscoveredTopicHandles(handles.size());
        if (handles.size() > 0 && !topicDataWarningAdded) {
            topicDataWarningAdded = true;
            snapshot.addWarning("RTI reported " + handles.size()
                    + " discovered topic handle(s), but TopicBuiltinTopicData is not "
                    + "available for secure discovered topics in this runtime. Topic names "
                    + "are derived from matched UMF endpoints and the configured UMF probes.");
        }
    }

    private void addMissingEndpointParticipants() {
        for (String guid : snapshot.missingEndpointParticipantGuids()) {
            Map<String, Object> record = new LinkedHashMap<>();
            record.put("type", "participant");
            record.put("guid", guid);
            record.put("name", null);
            record.put("domain_id", domain);
            record.put("source", "endpoint-discovery");
            record.put("note", "Observed through matched UMF endpoints; "
                    + "participant built-in data was not available from discovery.");
            if (snapshot.addParticipant(record)) {
                emit(record);
            }
        }
    }

    private void addConfiguredTopics() {
        for (EndpointProbe.Spec spec : EndpointProbe.DEFAULT_SPECS) {
            if (snapshot.hasTopic(spec.topicName, spec.typeNameHint)) {
                continue;
            }
            Map<String, Object> record = new LinkedHashMap<>();
            record.put("type", "topic");
            record.put("name", spec.topicName);
            record.put("type_name", spec.typeNameHint);
            record.put("observed", false);
            record.put("source", "platform-probe");
            if (snapshot.addTopic(record)) {
                emit(record);
            }
        }
    }

    private void emitSummary(Instant startedAt, long startedNanos, int probeCount) {
        long elapsedNanos = System.nanoTime() - startedNanos;
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("type", "summary");
        summary.put("collector_version", COLLECTOR_VERSION);
        summary.put("rti_version", rtiVersion());
        summary.put("domain", domain);
        summary.put("duration_seconds", durationSeconds);
        summary.put("duration_actual_seconds", elapsedNanos / 1_000_000_000.0);
        summary.put("qos_profile", qosProfile);
        summary.put("qos_file", qosFile);
        summary.put("peer", peer);
        summary.put("started_at_utc", startedAt.toString());
        summary.put("finished_at_utc", Instant.now().toString());
        summary.put("probe_count", probeCount);
        summary.put("counts", snapshot.counts());
        summary.put("warnings", snapshot.warnings());
        summary.put("content_filtered_readers", true);
        summary.put("sample_values_captured", false);
        summary.put("records_emitted", emittedRecords);
        emit(summary, true);
    }

    private void emit(Map<String, Object> record) {
        emit(record, false);
    }

    private void emit(Map<String, Object> record, boolean force) {
        if (!force && emittedRecords >= maxRecords) {
            if (!recordLimitWarned) {
                recordLimitWarned = true;
                snapshot.addWarning("Record limit (" + maxRecords
                        + ") reached; later discovery records were not emitted.");
            }
            return;
        }
        out.println(Json.write(record));
        out.flush();
        emittedRecords++;
    }

    private static String rtiVersion() {
        try {
            com.rti.ndds.config.LibraryVersion_t version =
                    Version.get_instance().get_core_version();
            return version.major + "." + version.minor + "." + (int) version.release
                    + "." + version.build;
        } catch (Throwable t) {
            return "unknown";
        }
    }

    private static String[] splitProfile(String profile) {
        if (profile == null || profile.isBlank()) {
            return new String[]{"AxoneNetQoSLibrary", "umfgeneral_qos"};
        }
        int separator = profile.indexOf("::");
        if (separator < 0) {
            return new String[]{"AxoneNetQoSLibrary", profile};
        }
        return new String[]{profile.substring(0, separator), profile.substring(separator + 2)};
    }

    private static String messageOf(Throwable t) {
        String message = t.getMessage();
        return message == null || message.isBlank() ? t.getClass().getSimpleName() : message;
    }

    private static String hintFor(Throwable t) {
        String text = String.valueOf(t.getMessage()).toLowerCase();
        if (text.contains("security") || text.contains("not allowed") || text.contains("denied")) {
            return "The platform SDDS identity is not permitted on this domain. "
                    + "The commissioning identity in this lab allows domains 2 and 32; "
                    + "use domain 32 or provision a dedicated UMF RTI identity for other domains.";
        }
        if (text.contains("error creating entity") || text.contains("create participant")
                || text.contains("create_participant")) {
            return "The RTI participant could not be created. The lab commissioning "
                    + "identity permits only domains 2 and 32; other domains need a "
                    + "dedicated UMF RTI identity. Also verify NDDS_QOS_PROFILES and "
                    + "that the SDDS certificate/key files are readable. See the "
                    + "collector stderr for 'participant not allowed' or QoS details.";
        }
        if (text.contains("qos") || text.contains("profile")) {
            return "Verify NDDS_QOS_PROFILES, --qos-file, and --qos-profile. "
                    + "The platform QoS file must be mounted at /opt/axone-tools/qos/CommissioningQoS.xml.";
        }
        return "Inspect the collector stderr/raw log for the RTI diagnostic message.";
    }

    private static Map<String, Object> errorRecord(String message) {
        Map<String, Object> error = new LinkedHashMap<>();
        error.put("type", "error");
        error.put("message", message);
        error.put("timestamp_utc", Instant.now().toString());
        return error;
    }

    private static void sleep(long millis) {
        if (millis <= 0) {
            return;
        }
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static final class Options {
        int domain = DEFAULT_DOMAIN;
        int duration = DEFAULT_DURATION;
        String qosFile = "/opt/axone-tools/qos/CommissioningQoS.xml";
        String qosProfile = "AxoneNetQoSLibrary::umfgeneral_qos";
        String peer = null;
        int maxRecords = MAX_RECORDS_DEFAULT;
        boolean noProbes = false;
        boolean verbose = false;

        static Options parse(String[] args) {
            Options options = new Options();
            for (int i = 0; i < args.length; i++) {
                String arg = args[i];
                switch (arg) {
                    case "--domain":
                        options.domain = intValue(args, ++i, arg);
                        break;
                    case "--duration":
                        options.duration = intValue(args, ++i, arg);
                        break;
                    case "--qos-file":
                        options.qosFile = stringValue(args, ++i, arg);
                        break;
                    case "--qos-profile":
                        options.qosProfile = stringValue(args, ++i, arg);
                        break;
                    case "--peer":
                        options.peer = stringValue(args, ++i, arg);
                        break;
                    case "--max-records":
                        options.maxRecords = intValue(args, ++i, arg);
                        break;
                    case "--no-probes":
                        options.noProbes = true;
                        break;
                    case "--verbose":
                        options.verbose = true;
                        break;
                    case "--help":
                    case "-h":
                        printUsage();
                        System.exit(0);
                        break;
                    default:
                        throw new IllegalArgumentException("unknown argument: " + arg);
                }
            }
            if (options.domain < 0 || options.domain > 100) {
                throw new IllegalArgumentException("--domain must be between 0 and 100");
            }
            if (options.duration < 1 || options.duration > 3600) {
                throw new IllegalArgumentException("--duration must be between 1 and 3600 seconds");
            }
            if (options.maxRecords < 1) {
                throw new IllegalArgumentException("--max-records must be positive");
            }
            return options;
        }

        private static int intValue(String[] args, int index, String name) {
            return Integer.parseInt(stringValue(args, index, name));
        }

        private static String stringValue(String[] args, int index, String name) {
            if (index >= args.length) {
                throw new IllegalArgumentException("missing value for " + name);
            }
            return args[index];
        }

        private static void printUsage() {
            System.out.println("Usage: java -cp <collector.jar>:<platform-app.jar> "
                    + "com.gehc.iomt.umfrti.UmfRtiCollector [options]");
            System.out.println("  --domain N          UMF domain id (default " + DEFAULT_DOMAIN + ")");
            System.out.println("  --duration N        Capture duration in seconds (default " + DEFAULT_DURATION + ")");
            System.out.println("  --qos-file PATH     QoS XML path (default /opt/axone-tools/qos/CommissioningQoS.xml)");
            System.out.println("  --qos-profile NAME  QoS profile (default AxoneNetQoSLibrary::umfgeneral_qos)");
            System.out.println("  --peer URI          Optional additional discovery peer");
            System.out.println("  --max-records N     Maximum NDJSON records (default " + MAX_RECORDS_DEFAULT + ")");
            System.out.println("  --no-probes         Skip local UMF endpoint probes");
            System.out.println("  --verbose           Enable RTI remote-status logging");
        }
    }
}
