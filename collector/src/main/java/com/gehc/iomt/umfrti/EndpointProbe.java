package com.gehc.iomt.umfrti;

import com.rti.dds.domain.DomainParticipant;
import com.rti.dds.domain.DomainParticipantFactory;
import com.rti.dds.domain.builtin.ParticipantBuiltinTopicData;
import com.rti.dds.infrastructure.InstanceHandleSeq;
import com.rti.dds.infrastructure.InstanceHandle_t;
import com.rti.dds.infrastructure.StatusKind;
import com.rti.dds.publication.DataWriter;
import com.rti.dds.publication.DataWriterQos;
import com.rti.dds.publication.builtin.PublicationBuiltinTopicData;
import com.rti.dds.subscription.DataReader;
import com.rti.dds.subscription.DataReaderQos;
import com.rti.dds.subscription.builtin.SubscriptionBuiltinTopicData;
import com.rti.dds.topic.ContentFilteredTopic;
import com.rti.dds.topic.Topic;
import com.rti.dds.topic.TypeSupport;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

/**
 * Creates short-lived local UMF endpoints only to make RTI report matched
 * remote endpoints.
 *
 * <p>DDS only exposes publication/subscription built-in data for endpoints
 * that have a local match.  We therefore create a reader (with an always-false
 * content filter so no user samples are delivered) or a writer (never written
 * to) for the platform's allowed UMF topics and then read the matched
 * publication/subscription data.  No sample values are ever read.</p>
 */
final class EndpointProbe {

    static final class Spec {
        final String topicName;
        final String typeSupportClass;
        final String typeNameHint;
        final String qosProfile;
        final boolean reader;
        final boolean writer;

        Spec(String topicName, String typeSupportClass, String typeNameHint,
                String qosProfile, boolean reader, boolean writer) {
            this.topicName = topicName;
            this.typeSupportClass = typeSupportClass;
            this.typeNameHint = typeNameHint;
            this.qosProfile = qosProfile;
            this.reader = reader;
            this.writer = writer;
        }
    }

    /** Topics and profiles the platform identity is allowed to read/write on domain 32. */
    static final Spec[] DEFAULT_SPECS = new Spec[]{
            new Spec("umf_cfg",
                    "com.ge.umf.umf_cfg.S35c_sapphireTypeSupport",
                    "umf_cfg::S35c_sapphire", "umfcfgnrt_qos", true, false),
            new Spec("umfcmd_req",
                    "com.ge.umf.umfcmd_req.S35c_sapphireTypeSupport",
                    "umfcmd_req::S35c_sapphire", "umfcfgnrt_qos", true, true),
            new Spec("umfcmd_resp",
                    "com.ge.umf.umfcmd_resp.S35c_sapphireTypeSupport",
                    "umfcmd_resp::S35c_sapphire", "umfcfgnrt_qos", true, true),
            new Spec("umf_cfg_state",
                    "com.ge.umf.umf_cfg_state.S35c_sapphireTypeSupport",
                    "umf_cfg_state::S35c_sapphire", "umfcfgnrt_state_qos", false, true),
    };

    private final Spec spec;
    private final String typeName;
    private final DataReader reader;
    private final DataWriter writer;
    private final boolean filtered;

    private EndpointProbe(Spec spec, String typeName, DataReader reader,
            DataWriter writer, boolean filtered) {
        this.spec = spec;
        this.typeName = typeName;
        this.reader = reader;
        this.writer = writer;
        this.filtered = filtered;
    }

    String topicName() {
        return spec.topicName;
    }

    String typeName() {
        return typeName;
    }

    static List<EndpointProbe> createAll(DomainParticipant participant,
            DomainParticipantFactory factory, String library, String collectorName,
            List<String> warnings) {
        List<EndpointProbe> probes = new ArrayList<>();
        Map<String, Topic> topics = new HashMap<>();
        Map<String, String> typeNames = new HashMap<>();
        boolean missingTypeClasses = false;
        for (Spec spec : DEFAULT_SPECS) {
            try {
                Topic topic = getOrCreateTopic(participant, topics, typeNames, spec);
                DataReader reader = null;
                DataWriter writer = null;
                boolean filtered = false;
                if (spec.reader) {
                    DataReaderQos qos = new DataReaderQos();
                    factory.get_datareader_qos_from_profile(qos, library, spec.qosProfile);
                    qos.subscription_name.name = collectorName + "-" + spec.topicName;
                    ContentFilteredTopic cft = null;
                    try {
                        cft = participant.create_contentfilteredtopic(
                                spec.topicName + "_iomt_probe", topic, "1 = 0", null);
                        filtered = true;
                    } catch (Throwable t) {
                        warnings.add("Could not create an always-false content filter for "
                                + spec.topicName + " (" + t.getMessage()
                                + "); the probe reader may receive user samples in its cache, "
                                + "but sample values are never read or written.");
                    }
                    reader = participant.create_datareader(
                            cft != null ? cft : topic, qos, null, StatusKind.STATUS_MASK_NONE);
                    if (reader == null) {
                        warnings.add("Could not create UMF RTI probe reader for " + spec.topicName + ".");
                    }
                }
                if (spec.writer) {
                    DataWriterQos qos = new DataWriterQos();
                    factory.get_datawriter_qos_from_profile(qos, library, spec.qosProfile);
                    qos.publication_name.name = collectorName + "-" + spec.topicName;
                    writer = participant.create_datawriter(
                            topic, qos, null, StatusKind.STATUS_MASK_NONE);
                    if (writer == null) {
                        warnings.add("Could not create UMF RTI probe writer for " + spec.topicName + ".");
                    }
                }
                if (reader != null || writer != null) {
                    probes.add(new EndpointProbe(spec, typeNames.get(spec.topicName), reader, writer, filtered));
                }
            } catch (Throwable t) {
                if (t instanceof ClassNotFoundException) {
                    if (!missingTypeClasses) {
                        missingTypeClasses = true;
                        warnings.add("The platform UMF generated type classes are not "
                                + "available on the Java classpath; endpoint discovery "
                                + "is disabled. Ensure the platform app JAR is included "
                                + "by the Job command.");
                    }
                } else {
                    warnings.add("UMF RTI probe for " + spec.topicName + " was skipped: " + t);
                }
            }
        }
        return probes;
    }

    private static Topic getOrCreateTopic(DomainParticipant participant,
            Map<String, Topic> topics, Map<String, String> typeNames, Spec spec) throws Exception {
        Topic existing = topics.get(spec.topicName);
        if (existing != null) {
            return existing;
        }
        Class<?> typeSupportClass = Class.forName(spec.typeSupportClass);
        String typeName = (String) typeSupportClass.getMethod("get_type_name").invoke(null);
        TypeSupport typeSupport = (TypeSupport) typeSupportClass.getMethod("get_instance").invoke(null);
        try {
            participant.register_type(typeName, typeSupport, null);
        } catch (Throwable t) {
            // Already registered by an earlier probe is harmless.
            if (!String.valueOf(t.getMessage()).toLowerCase().contains("already")) {
                throw t;
            }
        }
        Topic topic = participant.create_topic(spec.topicName, typeName,
                DomainParticipant.TOPIC_QOS_DEFAULT, null, StatusKind.STATUS_MASK_NONE);
        if (topic == null) {
            throw new IllegalStateException("create_topic returned null for " + spec.topicName);
        }
        topics.put(spec.topicName, topic);
        typeNames.put(spec.topicName, typeName);
        return topic;
    }

    void collect(DiscoverySnapshot snapshot, Map<String, String> participantNames,
            Consumer<Map<String, Object>> emit) {
        if (reader != null) {
            collectReaders(snapshot, participantNames, emit);
        }
        if (writer != null) {
            collectWriters(snapshot, participantNames, emit);
        }
    }

    private void collectReaders(DiscoverySnapshot snapshot,
            Map<String, String> participantNames, Consumer<Map<String, Object>> emit) {
        InstanceHandleSeq handles = new InstanceHandleSeq();
        try {
            reader.get_matched_publications(handles);
        } catch (Throwable t) {
            snapshot.addWarning("Could not read matched writers for " + spec.topicName + ": " + t);
            return;
        }
        for (int i = 0; i < handles.size(); i++) {
            InstanceHandle_t handle = (InstanceHandle_t) handles.get(i);
            PublicationBuiltinTopicData data = new PublicationBuiltinTopicData();
            try {
                reader.get_matched_publication_data(data, handle);
            } catch (Throwable t) {
                snapshot.addWarning("Could not read matched writer data for " + spec.topicName + ": " + t);
                continue;
            }
            Map<String, Object> record = endpointRecord("writer", data, handle, participantNames);
            record.put("source", "matched-publication");
            record.put("probe", spec.topicName + ":reader");
            if (snapshot.addWriter(record)) {
                emit.accept(record);
                addTopic(snapshot, data.topic_name, data.type_name, emit);
            }
        }
    }

    private void collectWriters(DiscoverySnapshot snapshot,
            Map<String, String> participantNames, Consumer<Map<String, Object>> emit) {
        InstanceHandleSeq handles = new InstanceHandleSeq();
        try {
            writer.get_matched_subscriptions(handles);
        } catch (Throwable t) {
            snapshot.addWarning("Could not read matched readers for " + spec.topicName + ": " + t);
            return;
        }
        for (int i = 0; i < handles.size(); i++) {
            InstanceHandle_t handle = (InstanceHandle_t) handles.get(i);
            SubscriptionBuiltinTopicData data = new SubscriptionBuiltinTopicData();
            try {
                writer.get_matched_subscription_data(data, handle);
            } catch (Throwable t) {
                snapshot.addWarning("Could not read matched reader data for " + spec.topicName + ": " + t);
                continue;
            }
            Map<String, Object> record = endpointRecord("reader", data, handle, participantNames);
            record.put("source", "matched-subscription");
            record.put("probe", spec.topicName + ":writer");
            if (snapshot.addReader(record)) {
                emit.accept(record);
                addTopic(snapshot, data.topic_name, data.type_name, emit);
            }
        }
    }

    private Map<String, Object> endpointRecord(String type, Object data,
            InstanceHandle_t handle, Map<String, String> participantNames) {
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("type", type);
        boolean alive = true;
        String topicName;
        String typeName;
        String guid;
        String participantGuid;
        Map<String, Object> qos;
        if (data instanceof PublicationBuiltinTopicData) {
            PublicationBuiltinTopicData publication = (PublicationBuiltinTopicData) data;
            topicName = publication.topic_name;
            typeName = publication.type_name;
            guid = QosFormatter.guid(publication.key);
            participantGuid = QosFormatter.guid(publication.participant_key);
            qos = QosFormatter.writer(publication);
            try {
                alive = reader.is_matched_publication_alive(handle);
            } catch (Throwable ignored) {
                // Liveness is best effort; a matched endpoint is alive unless told otherwise.
            }
        } else {
            SubscriptionBuiltinTopicData subscription = (SubscriptionBuiltinTopicData) data;
            topicName = subscription.topic_name;
            typeName = subscription.type_name;
            guid = QosFormatter.guid(subscription.key);
            participantGuid = QosFormatter.guid(subscription.participant_key);
            qos = QosFormatter.reader(subscription);
            try {
                alive = writer.is_matched_subscription_active(handle);
            } catch (Throwable ignored) {
                // Liveness is best effort.
            }
        }
        record.put("topic", topicName);
        record.put("type_name", typeName);
        record.put("guid", guid);
        record.put("participant_guid", participantGuid);
        record.put("participant_name", participantNames.get(participantGuid));
        record.put("liveness", alive ? "alive" : "not_alive");
        record.put("qos", qos);
        record.put("content_filtered", filtered);
        return record;
    }

    private void addTopic(DiscoverySnapshot snapshot, String topicName,
            String typeName, Consumer<Map<String, Object>> emit) {
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("type", "topic");
        record.put("name", topicName);
        record.put("type_name", typeName);
        record.put("observed", true);
        record.put("source", "endpoint-discovery");
        if (snapshot.addTopic(record)) {
            emit.accept(record);
        }
    }
}
