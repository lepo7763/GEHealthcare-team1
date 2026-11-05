package com.gehc.iomt.umfrti;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * De-duplicates discovery records by GUID (participants/endpoints) or by
 * topic+type (topics) and keeps the warning list used by the summary record.
 */
final class DiscoverySnapshot {

    private final Map<String, Map<String, Object>> participants = new LinkedHashMap<>();
    private final Map<String, Map<String, Object>> topics = new LinkedHashMap<>();
    private final Map<String, Map<String, Object>> writers = new LinkedHashMap<>();
    private final Map<String, Map<String, Object>> readers = new LinkedHashMap<>();
    private final List<String> warnings = new ArrayList<>();
    private final Set<String> endpointParticipantGuids = new LinkedHashSet<>();
    private int discoveredTopicHandles;

    boolean addParticipant(Map<String, Object> record) {
        String guid = (String) record.get("guid");
        return guid != null && participants.putIfAbsent(guid, record) == null;
    }

    boolean addTopic(Map<String, Object> record) {
        String name = (String) record.get("name");
        String typeName = (String) record.get("type_name");
        String key = (name == null ? "" : name) + "\u0000" + (typeName == null ? "" : typeName);
        return topics.putIfAbsent(key, record) == null;
    }

    boolean hasTopic(String name, String typeName) {
        String key = (name == null ? "" : name) + "\u0000" + (typeName == null ? "" : typeName);
        return topics.containsKey(key);
    }

    boolean addWriter(Map<String, Object> record) {
        noteEndpointParticipant((String) record.get("participant_guid"));
        String guid = (String) record.get("guid");
        return guid != null && writers.putIfAbsent(guid, record) == null;
    }

    boolean addReader(Map<String, Object> record) {
        noteEndpointParticipant((String) record.get("participant_guid"));
        String guid = (String) record.get("guid");
        return guid != null && readers.putIfAbsent(guid, record) == null;
    }

    boolean hasParticipant(String guid) {
        return guid != null && participants.containsKey(guid);
    }

    void noteEndpointParticipant(String guid) {
        if (guid != null) {
            endpointParticipantGuids.add(guid);
        }
    }

    Set<String> missingEndpointParticipantGuids() {
        Set<String> missing = new LinkedHashSet<>(endpointParticipantGuids);
        missing.removeAll(participants.keySet());
        return missing;
    }

    void addWarning(String warning) {
        if (warning != null && !warning.isBlank() && !warnings.contains(warning)) {
            warnings.add(warning);
        }
    }

    Map<String, Object> counts() {
        Map<String, Object> counts = new LinkedHashMap<>();
        counts.put("participants", participants.size());
        counts.put("topics", topics.size());
        counts.put("writers", writers.size());
        counts.put("readers", readers.size());
        counts.put("discovered_topic_handles", discoveredTopicHandles);
        return counts;
    }

    List<String> warnings() {
        return warnings;
    }

    void setDiscoveredTopicHandles(int discoveredTopicHandles) {
        this.discoveredTopicHandles = discoveredTopicHandles;
    }
}
