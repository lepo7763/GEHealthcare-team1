package com.gehc.iomt.umfrti;

import com.rti.dds.domain.DomainParticipantQos;
import com.rti.dds.domain.builtin.ParticipantBuiltinTopicData;
import com.rti.dds.infrastructure.Duration_t;
import com.rti.dds.infrastructure.PartitionQosPolicy;
import com.rti.dds.infrastructure.PropertyQosPolicy;
import com.rti.dds.infrastructure.Property_t;
import com.rti.dds.infrastructure.StringSeq;
import com.rti.dds.publication.builtin.PublicationBuiltinTopicData;
import com.rti.dds.subscription.builtin.SubscriptionBuiltinTopicData;
import com.rti.dds.topic.BuiltinTopicKey_t;
import com.rti.dds.infrastructure.GUID_t;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Converts RTI discovery/QoS structures into JSON-friendly maps. */
final class QosFormatter {

    private QosFormatter() {
    }

    static String guid(BuiltinTopicKey_t key) {
        if (key == null) {
            return null;
        }
        GUID_t guid = new GUID_t();
        key.to_guid(guid);
        if (guid.value == null) {
            return null;
        }
        StringBuilder out = new StringBuilder(guid.value.length * 2);
        for (byte b : guid.value) {
            out.append(String.format("%02x", b & 0xff));
        }
        return out.toString();
    }

    static List<Integer> vendorId(com.rti.dds.infrastructure.VendorId_t vendor) {
        List<Integer> out = new ArrayList<>();
        if (vendor != null && vendor.vendorId != null) {
            for (byte b : vendor.vendorId) {
                out.add(b & 0xff);
            }
        }
        return out;
    }

    static Map<String, Object> participant(ParticipantBuiltinTopicData data) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("guid", guid(data.key));
        out.put("name", data.participant_name == null ? null : data.participant_name.name);
        out.put("domain_id", data.domain_id);
        out.put("lease_duration", duration(data.lease_duration));
        out.put("rtps_protocol_version", version(data.rtps_protocol_version));
        out.put("vendor_id", vendorId(data.rtps_vendor_id));
        out.put("product_version", productVersion(data.product_version));
        out.put("metatraffic_unicast_locator_count",
                data.metatraffic_unicast_locators == null ? 0 : data.metatraffic_unicast_locators.size());
        out.put("default_unicast_locator_count",
                data.default_unicast_locators == null ? 0 : data.default_unicast_locators.size());
        out.put("participant_name", data.participant_name == null ? null : data.participant_name.name);
        out.put("security", true);
        return out;
    }

    static Map<String, Object> writer(PublicationBuiltinTopicData data) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("reliability", String.valueOf(data.reliability.kind));
        out.put("reliability_max_blocking_time", duration(data.reliability.max_blocking_time));
        out.put("reliability_acknowledgment_kind", String.valueOf(data.reliability.acknowledgment_kind));
        out.put("durability", String.valueOf(data.durability.kind));
        out.put("durability_writer_depth", data.durability.writer_depth);
        out.put("deadline_period", duration(data.deadline.period));
        out.put("latency_budget", duration(data.latency_budget.duration));
        out.put("liveliness", String.valueOf(data.liveliness.kind));
        out.put("liveliness_lease_duration", duration(data.liveliness.lease_duration));
        out.put("lifespan", duration(data.lifespan.duration));
        out.put("ownership", String.valueOf(data.ownership.kind));
        out.put("ownership_strength", data.ownership_strength.value);
        out.put("destination_order", String.valueOf(data.destination_order.kind));
        out.put("presentation_access_scope", String.valueOf(data.presentation.access_scope));
        out.put("presentation_coherent_access", data.presentation.coherent_access);
        out.put("presentation_ordered_access", data.presentation.ordered_access);
        out.put("partition", partition(data.partition));
        out.put("publication_name", data.publication_name == null ? null : data.publication_name.name);
        out.put("is_incompatible", data.is_incompatible);
        out.put("max_sample_serialized_size", data.max_sample_serialized_size);
        out.put("send_queue_size", data.send_queue_size);
        out.put("disable_positive_acks", data.disable_positive_acks);
        out.put("type_code_available", data.type_code != null);
        out.put("property_names", propertyNames(data.property));
        out.put("user_data_bytes", data.user_data == null ? 0 : data.user_data.value.size());
        out.put("topic_data_bytes", data.topic_data == null ? 0 : data.topic_data.value.size());
        out.put("group_data_bytes", data.group_data == null ? 0 : data.group_data.value.size());
        out.put("rtps_protocol_version", version(data.rtps_protocol_version));
        out.put("vendor_id", vendorId(data.rtps_vendor_id));
        out.put("product_version", productVersion(data.product_version));
        return out;
    }

    static Map<String, Object> reader(SubscriptionBuiltinTopicData data) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("reliability", String.valueOf(data.reliability.kind));
        out.put("reliability_max_blocking_time", duration(data.reliability.max_blocking_time));
        out.put("reliability_acknowledgment_kind", String.valueOf(data.reliability.acknowledgment_kind));
        out.put("durability", String.valueOf(data.durability.kind));
        out.put("deadline_period", duration(data.deadline.period));
        out.put("latency_budget", duration(data.latency_budget.duration));
        out.put("liveliness", String.valueOf(data.liveliness.kind));
        out.put("liveliness_lease_duration", duration(data.liveliness.lease_duration));
        out.put("ownership", String.valueOf(data.ownership.kind));
        out.put("destination_order", String.valueOf(data.destination_order.kind));
        out.put("time_based_filter", duration(data.time_based_filter.minimum_separation));
        out.put("presentation_access_scope", String.valueOf(data.presentation.access_scope));
        out.put("presentation_coherent_access", data.presentation.coherent_access);
        out.put("presentation_ordered_access", data.presentation.ordered_access);
        out.put("partition", partition(data.partition));
        out.put("subscription_name", data.subscription_name == null ? null : data.subscription_name.name);
        out.put("is_incompatible", data.is_incompatible);
        out.put("receive_queue_size", data.receive_queue_size);
        out.put("expects_inline_qos", data.expects_inline_qos);
        out.put("disable_positive_acks", data.disable_positive_acks);
        out.put("type_consistency", String.valueOf(data.type_consistency.kind));
        out.put("type_code_available", data.type_code != null);
        out.put("property_names", propertyNames(data.property));
        out.put("user_data_bytes", data.user_data == null ? 0 : data.user_data.value.size());
        out.put("topic_data_bytes", data.topic_data == null ? 0 : data.topic_data.value.size());
        out.put("group_data_bytes", data.group_data == null ? 0 : data.group_data.value.size());
        out.put("rtps_protocol_version", version(data.rtps_protocol_version));
        out.put("vendor_id", vendorId(data.rtps_vendor_id));
        out.put("product_version", productVersion(data.product_version));
        return out;
    }

    static Map<String, Object> localParticipant(DomainParticipantQos qos) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("participant_name", qos.participant_name == null ? null : qos.participant_name.name);
        out.put("transport_builtin_mask", qos.transport_builtin == null ? null : qos.transport_builtin.mask);
        out.put("discovery_initial_peers", stringList(qos.discovery == null ? null : qos.discovery.initial_peers));
        out.put("discovery_multicast_receive_addresses",
                stringList(qos.discovery == null ? null : qos.discovery.multicast_receive_addresses));
        out.put("accept_unknown_peers", qos.discovery == null ? null : qos.discovery.accept_unknown_peers);
        out.put("type_code_max_serialized_length", qos.resource_limits.type_code_max_serialized_length);
        out.put("type_object_max_serialized_length", qos.resource_limits.type_object_max_serialized_length);
        out.put("property_names", propertyNames(qos.property));
        return out;
    }

    private static Map<String, Object> version(com.rti.dds.infrastructure.ProtocolVersion_t version) {
        if (version == null) {
            return null;
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("major", version.major);
        out.put("minor", version.minor);
        return out;
    }

    private static Map<String, Object> productVersion(com.rti.dds.infrastructure.ProductVersion_t version) {
        if (version == null) {
            return null;
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("major", (int) version.major);
        out.put("minor", (int) version.minor);
        out.put("release", (int) version.release);
        out.put("revision", (int) version.revision);
        return out;
    }

    private static String duration(Duration_t duration) {
        if (duration == null) {
            return null;
        }
        if (duration.is_infinite()) {
            return "infinite";
        }
        if (duration.is_zero()) {
            return "0s";
        }
        return duration.sec + "." + String.format("%09d", duration.nanosec) + "s";
    }

    private static List<String> partition(PartitionQosPolicy policy) {
        return stringList(policy == null ? null : policy.name);
    }

    private static List<String> stringList(StringSeq seq) {
        List<String> out = new ArrayList<>();
        if (seq != null) {
            for (int i = 0; i < seq.size(); i++) {
                out.add((String) seq.get(i));
            }
        }
        return out;
    }

    private static List<String> propertyNames(PropertyQosPolicy policy) {
        List<String> out = new ArrayList<>();
        if (policy != null && policy.value != null) {
            for (int i = 0; i < policy.value.size(); i++) {
                Property_t property = (Property_t) policy.value.get(i);
                if (property != null && property.name != null) {
                    out.add(property.name);
                }
            }
        }
        return out;
    }
}
