package com.gehc.iomt.umfrti;

import java.util.Map;

/**
 * Minimal, zero-dependency JSON serializer for emitting single-line NDJSON records.
 *
 * Why we write this instead of using Jackson/Gson:
 * Our collector JAR is mounted into the Pod via a Kubernetes Secret (which has a 1 MiB limit).
 * Avoiding third-party libraries keeps the compiled JAR under ~15 KB and ensures every record
 * (even multi-line RTI QoS dumps) is escaped onto a single NDJSON line.
 */
public final class Json {

    private Json() {}

    /**
     * Escapes a string according to RFC 8259 so that newlines, tabs, quotes,
     * and control characters in RTI QoS strings never break single-line NDJSON.
     */
    public static String quote(String value) {
        if (value == null) {
            return "null";
        }
        StringBuilder sb = new StringBuilder(value.length() + 16);
        sb.append('"');
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"':
                    sb.append("\\\"");
                    break;
                case '\\':
                    sb.append("\\\\");
                    break;
                case '\b':
                    sb.append("\\b");
                    break;
                case '\f':
                    sb.append("\\f");
                    break;
                case '\n':
                    sb.append("\\n");
                    break;
                case '\r':
                    sb.append("\\r");
                    break;
                case '\t':
                    sb.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        sb.append('"');
        return sb.toString();
    }

    /**
     * Serializes a flat Map of key-value pairs into a single-line JSON object.
     * Supports String, Number, Boolean, and null values.
     */
    public static String object(Map<String, Object> fields) {
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> entry : fields.entrySet()) {
            if (!first) {
                sb.append(',');
            }
            first = false;
            sb.append(quote(entry.getKey())).append(':');
            Object val = entry.getValue();
            if (val == null) {
                sb.append("null");
            } else if (val instanceof Number || val instanceof Boolean) {
                sb.append(val.toString());
            } else {
                sb.append(quote(val.toString()));
            }
        }
        sb.append('}');
        return sb.toString();
    }
}