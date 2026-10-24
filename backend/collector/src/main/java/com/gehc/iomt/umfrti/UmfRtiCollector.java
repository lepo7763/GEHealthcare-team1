package com.gehc.iomt.umfrti;

import com.rti.dds.domain.DomainParticipant;
import com.rti.dds.domain.DomainParticipantFactory;
import com.rti.dds.domain.DomainParticipantFactoryQos;
import com.rti.dds.domain.builtin.ParticipantBuiltinTopicData;
import com.rti.dds.infrastructure.InstanceHandleSeq;
import com.rti.dds.infrastructure.InstanceHandle_t;
import com.rti.dds.infrastructure.ResourceLimitsQosPolicy;
import com.rti.dds.infrastructure.StatusKind;
import com.rti.dds.publication.builtin.PublicationBuiltinTopicData;
import com.rti.dds.publication.builtin.PublicationBuiltinTopicDataDataReader;
import com.rti.dds.publication.builtin.PublicationBuiltinTopicDataSeq;
import com.rti.dds.publication.builtin.PublicationBuiltinTopicDataTypeSupport;
import com.rti.dds.subscription.InstanceStateKind;
import com.rti.dds.subscription.SampleInfo;
import com.rti.dds.subscription.SampleInfoSeq;
import com.rti.dds.subscription.SampleStateKind;
import com.rti.dds.subscription.ViewStateKind;
import com.rti.dds.subscription.builtin.SubscriptionBuiltinTopicData;
import com.rti.dds.subscription.builtin.SubscriptionBuiltinTopicDataDataReader;
import com.rti.dds.subscription.builtin.SubscriptionBuiltinTopicDataSeq;
import com.rti.dds.subscription.builtin.SubscriptionBuiltinTopicDataTypeSupport;
import com.rti.dds.topic.builtin.TopicBuiltinTopicData;

import java.time.Instant;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/**
 * Headless UMF RTI discovery collector.
 *
 * Joins the target DDS domain using the platform's QoS profile and SDDS security
 * artifacts, polls built-in discovery tables every 1 second for the requested
 * duration, and emits one NDJSON line per newly discovered entity (participant,
 * topic, writer, reader) followed by a final summary record.
 *
 * PHI Safety:
 * This collector ONLY inspects DDS discovery metadata (builtin topics). It never
 * creates Subscribers/DataReaders for user topics and never reads patient payload data.
 */
public final class UmfRtiCollector {

    private static final String COLLECTOR_VERSION = "1.0.0";

    public static void main(String[] args) {
        int domainId = 12;
        int durationSeconds = 120;
        String qosFile = "/opt/axone-tools/qos/CommissioningQoS.xml";
        String qosProfile = "AxoneNetQoSLibrary::umfgeneral_qos";

        // 1. Parse CLI arguments
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--domain":
                    domainId = Integer.parseInt(args[++i]);
                    break;
                case "--duration":
                    durationSeconds = Integer.parseInt(args[++i]);
                    break;
                case "--qos-file":
                    qosFile = args[++i];
                    break;
                case "--qos-profile":
                    qosProfile = args[++i];
                    break;
                default:
                    break;
            }
        }

        // Split "AxoneNetQoSLibrary::umfgeneral_qos" into library + profile name
        String qosLibrary = "AxoneNetQoSLibrary";
        String qosProfileName = qosProfile;
        int sepIdx = qosProfile.indexOf("::");
        if (sepIdx >= 0) {
            qosLibrary = qosProfile.substring(0, sepIdx);
            qosProfileName = qosProfile.substring(sepIdx + 2);
        }

        DomainParticipant participant = null;
        try {
            // 2. Register the QoS XML file with DomainParticipantFactory.
            // In RTI's Java API, DomainParticipantFactoryQos.profile.url_profile holds
            // the list of XML files to load (alongside the NDDS_QOS_PROFILES env var).
            DomainParticipantFactory factory = DomainParticipantFactory.get_instance();
            if (qosFile != null && !qosFile.isBlank()) {
                String qosUri = qosFile.startsWith("file://") ? qosFile : "file://" + qosFile;
                DomainParticipantFactoryQos factoryQos = new DomainParticipantFactoryQos();
                factory.get_qos(factoryQos);
                if (!factoryQos.profile.url_profile.contains(qosUri)) {
                    factoryQos.profile.url_profile.add(qosUri);
                    factory.set_qos(factoryQos);
                }
            }

            // 3. Create the DomainParticipant using the loaded library + profile.
            // This triggers the DDS Security handshake (using SDDS_HOME env vars)
            // and begins peer discovery with NDDS_DISCOVERY_PEERS (axone-router-1).
            participant = factory.create_participant_with_profile(
                domainId,
                qosLibrary,
                qosProfileName,
                null, // No listener needed; we poll periodically
                StatusKind.STATUS_MASK_NONE
            );

            if (participant == null) {
                emitError("Failed to create DDS DomainParticipant for domain " + domainId);
                System.exit(1);
            }

            // Track seen GUIDs so we only emit each discovered entity once per session
            Set<String> seenParticipants = new HashSet<>();
            Set<String> seenTopics = new HashSet<>();
            Set<String> seenWriters = new HashSet<>();
            Set<String> seenReaders = new HashSet<>();

            long startNanos = System.nanoTime();
            long durationNanos = durationSeconds * 1_000_000_000L;

            // 4. Poll discovery tables every 1 second until duration elapses
            while (true) {
                pollParticipants(participant, domainId, seenParticipants);
                pollTopics(participant, domainId, seenTopics);
                pollWriters(participant, domainId, seenWriters);
                pollReaders(participant, domainId, seenReaders);

                if (System.nanoTime() - startNanos >= durationNanos) {
                    break;
                }
                Thread.sleep(1000L);
            }

            // 5. Emit final summary record
            Map<String, Object> summary = new LinkedHashMap<>();
            summary.put("type", "summary");
            summary.put("timestamp", Instant.now().toString());
            summary.put("domain_id", domainId);
            summary.put("duration_seconds", durationSeconds);
            summary.put("qos_profile", qosLibrary + "::" + qosProfileName);
            summary.put("collector_version", COLLECTOR_VERSION);
            summary.put("participants_count", seenParticipants.size());
            summary.put("topics_count", seenTopics.size());
            summary.put("writers_count", seenWriters.size());
            summary.put("readers_count", seenReaders.size());
            emitLine(Json.object(summary));

        } catch (Throwable t) {
            emitError(t.getClass().getName() + ": " + t.getMessage());
            System.exit(1);
        } finally {
            // 6. Cleanly shut down DDS entities so the router knows we left
            if (participant != null) {
                try {
                    participant.delete_contained_entities();
                    DomainParticipantFactory.get_instance().delete_participant(participant);
                } catch (Throwable ignored) {
                }
            }
        }
    }

    private static void pollParticipants(
        DomainParticipant participant, int domainId, Set<String> seen
    ) {
        InstanceHandleSeq handles = new InstanceHandleSeq();
        try {
            participant.get_discovered_participants(handles);
            for (int i = 0; i < handles.size(); i++) {
                InstanceHandle_t handle = (InstanceHandle_t) handles.get(i);
                ParticipantBuiltinTopicData data = new ParticipantBuiltinTopicData();
                try {
                    participant.get_discovered_participant_data(data, handle);
                    String guid = formatKey(data.key.value, handle);
                    if (seen.add(guid)) {
                        Map<String, Object> rec = new LinkedHashMap<>();
                        rec.put("type", "participant");
                        rec.put("timestamp", Instant.now().toString());
                        rec.put("domain_id", domainId);
                        rec.put("guid", guid);
                        rec.put(
                            "name",
                            data.participant_name != null && data.participant_name.name != null
                                ? data.participant_name.name
                                : ""
                        );
                        rec.put("liveness", true);
                        rec.put("qos", data.toString());
                        emitLine(Json.object(rec));
                    }
                } catch (Exception ignored) {
                    // Entity may have disappeared between get_discovered_* and get_data
                }
            }
        } catch (Exception ignored) {
            // Builtin discovery reader may not be enabled or supported for this entity type
        }
    }

    private static void pollTopics(
        DomainParticipant participant, int domainId, Set<String> seen
    ) {
        InstanceHandleSeq handles = new InstanceHandleSeq();
        try {
            participant.get_discovered_topics(handles);
            for (int i = 0; i < handles.size(); i++) {
                InstanceHandle_t handle = (InstanceHandle_t) handles.get(i);
                TopicBuiltinTopicData data = new TopicBuiltinTopicData();
                try {
                    participant.get_discovered_topic_data(data, handle);
                    String guid = formatKey(data.key.value, handle);
                    if (seen.add(guid)) {
                        Map<String, Object> rec = new LinkedHashMap<>();
                        rec.put("type", "topic");
                        rec.put("timestamp", Instant.now().toString());
                        rec.put("domain_id", domainId);
                        rec.put("guid", guid);
                        rec.put("name", data.name != null ? data.name : "");
                        rec.put("type_name", data.type_name != null ? data.type_name : "");
                        rec.put("liveness", true);
                        rec.put("qos", data.toString());
                        emitLine(Json.object(rec));
                    }
                } catch (Exception ignored) {
                }
            }
        } catch (Exception ignored) {
        }
    }

    private static void pollWriters(
        DomainParticipant participant, int domainId, Set<String> seen
    ) {
        try {
            PublicationBuiltinTopicDataDataReader reader =
                (PublicationBuiltinTopicDataDataReader)
                    participant.get_builtin_subscriber().lookup_datareader(
                        PublicationBuiltinTopicDataTypeSupport.PUBLICATION_TOPIC_NAME
                    );
            if (reader == null) {
                return;
            }
            PublicationBuiltinTopicDataSeq dataSeq = new PublicationBuiltinTopicDataSeq();
            SampleInfoSeq infoSeq = new SampleInfoSeq();
            try {
                reader.read(
                    dataSeq,
                    infoSeq,
                    ResourceLimitsQosPolicy.LENGTH_UNLIMITED,
                    SampleStateKind.ANY_SAMPLE_STATE,
                    ViewStateKind.ANY_VIEW_STATE,
                    InstanceStateKind.ANY_INSTANCE_STATE
                );
                for (int i = 0; i < dataSeq.size(); i++) {
                    SampleInfo info = (SampleInfo) infoSeq.get(i);
                    if (!info.valid_data) {
                        continue;
                    }
                    PublicationBuiltinTopicData data =
                        (PublicationBuiltinTopicData) dataSeq.get(i);
                    String guid = formatKey(data.key.value, info.instance_handle);
                    if (seen.add(guid)) {
                        boolean alive =
                            info.instance_state == InstanceStateKind.ALIVE_INSTANCE_STATE;
                        Map<String, Object> rec = new LinkedHashMap<>();
                        rec.put("type", "writer");
                        rec.put("timestamp", Instant.now().toString());
                        rec.put("domain_id", domainId);
                        rec.put("guid", guid);
                        rec.put("topic", data.topic_name != null ? data.topic_name : "");
                        rec.put("type_name", data.type_name != null ? data.type_name : "");
                        rec.put("liveness", alive);
                        rec.put("qos", data.toString());
                        emitLine(Json.object(rec));
                    }
                }
            } finally {
                reader.return_loan(dataSeq, infoSeq);
            }
        } catch (Exception ignored) {
        }
    }

    private static void pollReaders(
        DomainParticipant participant, int domainId, Set<String> seen
    ) {
        try {
            SubscriptionBuiltinTopicDataDataReader reader =
                (SubscriptionBuiltinTopicDataDataReader)
                    participant.get_builtin_subscriber().lookup_datareader(
                        SubscriptionBuiltinTopicDataTypeSupport.SUBSCRIPTION_TOPIC_NAME
                    );
            if (reader == null) {
                return;
            }
            SubscriptionBuiltinTopicDataSeq dataSeq = new SubscriptionBuiltinTopicDataSeq();
            SampleInfoSeq infoSeq = new SampleInfoSeq();
            try {
                reader.read(
                    dataSeq,
                    infoSeq,
                    ResourceLimitsQosPolicy.LENGTH_UNLIMITED,
                    SampleStateKind.ANY_SAMPLE_STATE,
                    ViewStateKind.ANY_VIEW_STATE,
                    InstanceStateKind.ANY_INSTANCE_STATE
                );
                for (int i = 0; i < dataSeq.size(); i++) {
                    SampleInfo info = (SampleInfo) infoSeq.get(i);
                    if (!info.valid_data) {
                        continue;
                    }
                    SubscriptionBuiltinTopicData data =
                        (SubscriptionBuiltinTopicData) dataSeq.get(i);
                    String guid = formatKey(data.key.value, info.instance_handle);
                    if (seen.add(guid)) {
                        boolean alive =
                            info.instance_state == InstanceStateKind.ALIVE_INSTANCE_STATE;
                        Map<String, Object> rec = new LinkedHashMap<>();
                        rec.put("type", "reader");
                        rec.put("timestamp", Instant.now().toString());
                        rec.put("domain_id", domainId);
                        rec.put("guid", guid);
                        rec.put("topic", data.topic_name != null ? data.topic_name : "");
                        rec.put("type_name", data.type_name != null ? data.type_name : "");
                        rec.put("liveness", alive);
                        rec.put("qos", data.toString());
                        emitLine(Json.object(rec));
                    }
                }
            } finally {
                reader.return_loan(dataSeq, infoSeq);
            }
        } catch (Exception ignored) {
        }
    }

    /**
     * Formats an RTI BuiltinTopicKey_t int[] array into a readable hex GUID string.
     */
    private static String formatKey(int[] keyVal, InstanceHandle_t fallbackHandle) {
        if (keyVal != null && keyVal.length > 0) {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < keyVal.length; i++) {
                if (i > 0) {
                    sb.append('-');
                }
                sb.append(String.format("%08x", keyVal[i]));
            }
            return sb.toString();
        }
        return fallbackHandle != null ? fallbackHandle.toString() : Arrays.toString(keyVal);
    }

    private static void emitError(String message) {
        Map<String, Object> err = new LinkedHashMap<>();
        err.put("type", "error");
        err.put("timestamp", Instant.now().toString());
        err.put("message", message != null ? message : "Unknown error");
        emitLine(Json.object(err));
    }

    private static void emitLine(String jsonLine) {
        System.out.println(jsonLine);
        System.out.flush();
    }
}