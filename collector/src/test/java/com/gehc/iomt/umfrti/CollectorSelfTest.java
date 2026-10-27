package com.gehc.iomt.umfrti;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Dependency-free self-tests run by collector/build.sh. */
public final class CollectorSelfTest {

    private static int checks;

    public static void main(String[] args) {
        testJsonEscaping();
        testJsonContainers();
        testSnapshotDedupesParticipantsAndEndpoints();
        testSnapshotDedupesTopics();
        testSummaryCounts();
        System.out.println("CollectorSelfTest OK (" + checks + " checks)");
    }

    private static void testJsonEscaping() {
        check("\"a\\\"b\"".equals(Json.quote("a\"b")), "quote escapes double quotes");
        check("\"a\\\\b\"".equals(Json.quote("a\\b")), "quote escapes backslashes");
        check("\"a\\nb\"".equals(Json.quote("a\nb")), "quote escapes newlines");
        check("\"a\\tb\"".equals(Json.quote("a\tb")), "quote escapes tabs");
        check("\"\\u0001\"".equals(Json.quote("\u0001")), "quote escapes control characters");
        check("null".equals(Json.quote(null)), "quote renders null");
    }

    private static void testJsonContainers() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("type", "summary");
        map.put("count", 2);
        map.put("ok", true);
        map.put("items", List.of("a", "b"));
        check("{\"type\":\"summary\",\"count\":2,\"ok\":true,\"items\":[\"a\",\"b\"]}"
                .equals(Json.write(map)), "map/list rendering keeps insertion order");
        check("[1,2,3]".equals(Json.write(new int[]{1, 2, 3})), "int array rendering");
    }

    private static void testSnapshotDedupesParticipantsAndEndpoints() {
        DiscoverySnapshot snapshot = new DiscoverySnapshot();
        check(snapshot.addParticipant(record("participant", "guid-p1")), "first participant accepted");
        check(!snapshot.addParticipant(record("participant", "guid-p1")), "duplicate participant ignored");
        check(snapshot.addWriter(record("writer", "guid-w1")), "first writer accepted");
        check(!snapshot.addWriter(record("writer", "guid-w1")), "duplicate writer ignored");
        check(snapshot.addReader(record("reader", "guid-r1")), "first reader accepted");
        check(!snapshot.addReader(record("reader", "guid-r1")), "duplicate reader ignored");
    }

    private static void testSnapshotDedupesTopics() {
        DiscoverySnapshot snapshot = new DiscoverySnapshot();
        Map<String, Object> topic = new LinkedHashMap<>();
        topic.put("type", "topic");
        topic.put("name", "umf_cfg");
        topic.put("type_name", "umf_cfg::S35c_sapphire");
        check(snapshot.addTopic(topic), "first topic accepted");
        check(!snapshot.addTopic(topic), "duplicate topic ignored");
        check(snapshot.hasTopic("umf_cfg", "umf_cfg::S35c_sapphire"), "topic lookup by name/type");
        check(!snapshot.hasTopic("umf_cfg", "other::Type"), "topic lookup distinguishes type");
    }

    private static void testSummaryCounts() {
        DiscoverySnapshot snapshot = new DiscoverySnapshot();
        snapshot.addParticipant(record("participant", "p1"));
        snapshot.addParticipant(record("participant", "p2"));
        snapshot.addWriter(record("writer", "w1"));
        snapshot.addReader(record("reader", "r1"));
        snapshot.addTopic(topicRecord("umfcmd_req", "umfcmd_req::S35c_sapphire"));
        snapshot.setDiscoveredTopicHandles(13);
        snapshot.addWarning("warning one");
        snapshot.addWarning("warning one");
        snapshot.addWarning("warning two");

        Map<String, Object> counts = snapshot.counts();
        check(Integer.valueOf(2).equals(counts.get("participants")), "summary participant count");
        check(Integer.valueOf(1).equals(counts.get("topics")), "summary topic count");
        check(Integer.valueOf(1).equals(counts.get("writers")), "summary writer count");
        check(Integer.valueOf(1).equals(counts.get("readers")), "summary reader count");
        check(Integer.valueOf(13).equals(counts.get("discovered_topic_handles")), "topic handle count");
        check(snapshot.warnings().size() == 2, "warnings are de-duplicated");
        check(new ArrayList<>(snapshot.warnings()).equals(List.of("warning one", "warning two")),
                "warning order is preserved");
    }

    private static Map<String, Object> record(String type, String guid) {
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("type", type);
        record.put("guid", guid);
        return record;
    }

    private static Map<String, Object> topicRecord(String name, String typeName) {
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("type", "topic");
        record.put("name", name);
        record.put("type_name", typeName);
        return record;
    }

    private static void check(boolean condition, String description) {
        checks++;
        if (!condition) {
            throw new AssertionError("FAILED: " + description);
        }
    }
}
