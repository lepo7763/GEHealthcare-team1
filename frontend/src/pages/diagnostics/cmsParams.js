import { format } from 'date-fns';
import { toLocalDateTime } from '../../lib/dateTime.js';
import { normalizeTime } from '../../lib/time.js';

export const DEFAULT_CMS_PARAMS = {
    start: { date: undefined, time: '' },
    end: { date: undefined, time: '' },
};

// The CMS form explicitly asks for UTC.
// Preserve the selected calendar date and clock time as UTC,
// without applying the browser's local timezone.
const parseCmsTime = (value, label) => {
    const time = normalizeTime(value.time);
    const timestamp = toLocalDateTime(value.date, time);

    const pattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}$/;

    if (!pattern.test(timestamp)) {
        throw new Error(`Enter a valid CMS ${label} date and time in UTC.`);
    }

    // Verify that the calendar date is real, not something like February 30.
    const parsed = new Date(`${timestamp}Z`);

    if (
        !Number.isFinite(parsed.getTime()) ||
        parsed.toISOString() !== `${timestamp}Z`
    ) {
        throw new Error(`Enter a valid CMS ${label} date and time.`);
    }

    return {
        timestamp,
        milliseconds: parsed.getTime(),
    };
};

// Builds the parameters accepted by the backend collection endpoint.
export const toCmsQuery = (value) => {
    const start = parseCmsTime(value.start, 'start');
    const end = parseCmsTime(value.end, 'end');

    if (end.milliseconds <= start.milliseconds) {
        throw new Error('CMS end time must be after start time.');
    }

    return new URLSearchParams({
        cms_start_datetime: start.timestamp,
        cms_end_datetime: end.timestamp,
    });
};

const formatPoint = (value) => {
    if (!value.date) return 'Not set';

    const time = normalizeTime(value.time);

    return `${format(value.date, 'MMM d, yyyy')} ${time || '(time required)'}`;
};

export const summarizeCms = (value) =>
    `${formatPoint(value.start)} → ${formatPoint(value.end)} UTC`;