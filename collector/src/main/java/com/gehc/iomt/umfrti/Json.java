package com.gehc.iomt.umfrti;

import java.util.Iterator;
import java.util.Map;

/**
 * Tiny dependency-free JSON writer for the collector's newline-delimited output.
 *
 * <p>Only the value types the collector emits are supported: null, strings,
 * booleans, numbers, maps with string keys, iterables and primitive int arrays.
 * Maps keep their insertion order so the output is stable and easy to diff.</p>
 */
final class Json {

    private Json() {
    }

    static String quote(String value) {
        if (value == null) {
            return "null";
        }
        StringBuilder out = new StringBuilder(value.length() + 16);
        out.append('"');
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"':
                    out.append("\\\"");
                    break;
                case '\\':
                    out.append("\\\\");
                    break;
                case '\b':
                    out.append("\\b");
                    break;
                case '\f':
                    out.append("\\f");
                    break;
                case '\n':
                    out.append("\\n");
                    break;
                case '\r':
                    out.append("\\r");
                    break;
                case '\t':
                    out.append("\\t");
                    break;
                default:
                    if (c < 0x20 || c == 0x7f) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
            }
        }
        out.append('"');
        return out.toString();
    }

    static String write(Object value) {
        StringBuilder out = new StringBuilder(256);
        append(out, value);
        return out.toString();
    }

    private static void append(StringBuilder out, Object value) {
        if (value == null) {
            out.append("null");
        } else if (value instanceof String) {
            out.append(quote((String) value));
        } else if (value instanceof Boolean || value instanceof Byte
                || value instanceof Short || value instanceof Integer
                || value instanceof Long || value instanceof Float
                || value instanceof Double) {
            out.append(value);
        } else if (value instanceof Map<?, ?>) {
            appendMap(out, (Map<?, ?>) value);
        } else if (value instanceof Iterable<?>) {
            appendIterable(out, (Iterable<?>) value);
        } else if (value instanceof int[]) {
            appendIntArray(out, (int[]) value);
        } else if (value instanceof Object[]) {
            appendObjectArray(out, (Object[]) value);
        } else {
            out.append(quote(value.toString()));
        }
    }

    private static void appendMap(StringBuilder out, Map<?, ?> map) {
        out.append('{');
        Iterator<? extends Map.Entry<?, ?>> it = map.entrySet().iterator();
        boolean first = true;
        while (it.hasNext()) {
            Map.Entry<?, ?> entry = it.next();
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append(quote(String.valueOf(entry.getKey())));
            out.append(':');
            append(out, entry.getValue());
        }
        out.append('}');
    }

    private static void appendIterable(StringBuilder out, Iterable<?> values) {
        out.append('[');
        Iterator<?> it = values.iterator();
        boolean first = true;
        while (it.hasNext()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            append(out, it.next());
        }
        out.append(']');
    }

    private static void appendIntArray(StringBuilder out, int[] values) {
        out.append('[');
        for (int i = 0; i < values.length; i++) {
            if (i > 0) {
                out.append(',');
            }
            out.append(values[i]);
        }
        out.append(']');
    }

    private static void appendObjectArray(StringBuilder out, Object[] values) {
        out.append('[');
        for (int i = 0; i < values.length; i++) {
            if (i > 0) {
                out.append(',');
            }
            append(out, values[i]);
        }
        out.append(']');
    }
}
