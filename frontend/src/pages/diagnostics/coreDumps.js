// Helpers for the Core Dumps service (Configure + Review steps).
// The estimate mirrors the backend's select_files(): filter by time. There is no size cap; every matching core is collected.

export const CUSTOM_RANGE = 'custom';

export const CORE_SINCE_OPTIONS = [
  { value: '', label: 'Any time' },
  { value: '24', label: 'Last 24 hours' },
  { value: '168', label: 'Last 7 days' },
  { value: '720', label: 'Last 30 days' },
  { value: CUSTOM_RANGE, label: 'Custom' },
];

// endNow: when the end date is today, use the current time instead of endTime.
export const EMPTY_CUSTOM_RANGE = {
  start: '',
  end: '',
  startTime: '00:00',
  endTime: '23:59',
  endNow: false,
};

const pad = (n) => String(n).padStart(2, '0');

// 'YYYY-MM-DD' for a moment, in the browser's local time.
export const dateKey = (now = Date.now()) => {
  const d = new Date(now);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

// 'YYYY-MM-DD' + 'HH:MM' in the browser's local time -> Date (null if incomplete/invalid).
const localDate = (date, time) => {
  if (!date || !/^\d{2}:\d{2}$/.test(time || '')) return null;
  const d = new Date(`${date}T${time}:00`);
  return Number.isNaN(d.getTime()) ? null : d;
};

// Resolved start/end of a custom range, or null while incomplete. "Current time"
// on an end date of today resolves to `now`.
const resolveRange = (range, now) => {
  const start = localDate(range?.start, range?.startTime);
  const endNow = Boolean(range?.endNow) && range?.end === dateKey(now);
  const end = endNow ? new Date(now) : localDate(range?.end, range?.endTime);
  return start && end ? { start, end } : null;
};

// Why a custom range can't be used, or '' when it is fine (or still incomplete).
export const customRangeError = (range, now = Date.now()) => {
  const r = resolveRange(range, now);
  if (!r) return '';
  if (r.start > now || r.end > now) {
    return 'You cannot use a future time to collect logs. Choose a time that has already passed.';
  }
  if (r.start > r.end) return 'The start must be before the end.';
  return '';
};

// A custom range is usable once both dates and both times are set, start <= end, nothing in the future.
export const customRangeBounds = (range, now = Date.now()) =>
  customRangeError(range, now) ? null : resolveRange(range, now);

export const isCustomRangeValid = (range, now = Date.now()) =>
  customRangeBounds(range, now) !== null;

export const sinceIso = (hours, now = Date.now(), customRange = null) => {
  if (hours === CUSTOM_RANGE) {
    return customRangeBounds(customRange, now)?.start.toISOString() ?? null;
  }
  return hours ? new Date(now - Number(hours) * 3600 * 1000).toISOString() : null;
};

export const untilIso = (hours, customRange = null, now = Date.now()) =>
  hours === CUSTOM_RANGE ? (customRangeBounds(customRange, now)?.end.toISOString() ?? null) : null;

export const formatBytes = (bytes) => {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = n / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${units[i]}`;
};

export const estimateSelection = (files, { sinceHours, customRange }, now = Date.now()) => {
  const since = sinceIso(sinceHours, now, customRange);
  const until = untilIso(sinceHours, customRange, now);
  let bytes = 0;
  let count = 0;
  for (const file of files || []) {
    if (since && new Date(file.time_utc) < new Date(since)) continue;
    if (until && new Date(file.time_utc) > new Date(until)) continue;
    bytes += file.size_bytes;
    count += 1;
  }
  return { count, bytes };
};

export const describeCoreFilters = ({ sinceHours, customRange }) => {
  if (sinceHours === CUSTOM_RANGE) {
    const r = customRange || EMPTY_CUSTOM_RANGE;
    const endText = r.endNow && r.end === dateKey() ? 'now' : r.endTime;
    return customRangeBounds(r)
      ? `${r.start} ${r.startTime} – ${r.end} ${endText}`
      : 'Custom range (choose dates and times)';
  }
  return CORE_SINCE_OPTIONS.find((o) => o.value === String(sinceHours ?? ''))?.label || 'Any time';
};
