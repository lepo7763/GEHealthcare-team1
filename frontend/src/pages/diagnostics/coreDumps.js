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

export const EMPTY_CUSTOM_RANGE = { start: '', end: '', startTime: '00:00', endTime: '23:59' };

// 'YYYY-MM-DD' + 'HH:MM' in the browser's local time -> Date (null if incomplete/invalid).
const localDate = (date, time) => {
  if (!date || !/^\d{2}:\d{2}$/.test(time || '')) return null;
  const d = new Date(`${date}T${time}:00`);
  return Number.isNaN(d.getTime()) ? null : d;
};

// A custom range is usable once both dates and both times are set and start <= end.
export const customRangeBounds = (range) => {
  const start = localDate(range?.start, range?.startTime);
  const end = localDate(range?.end, range?.endTime);
  if (!start || !end || start > end) return null;
  return { start, end };
};

export const isCustomRangeValid = (range) => customRangeBounds(range) !== null;

export const sinceIso = (hours, now = Date.now(), customRange = null) => {
  if (hours === CUSTOM_RANGE) return customRangeBounds(customRange)?.start.toISOString() ?? null;
  return hours ? new Date(now - Number(hours) * 3600 * 1000).toISOString() : null;
};

export const untilIso = (hours, customRange = null) =>
  hours === CUSTOM_RANGE ? (customRangeBounds(customRange)?.end.toISOString() ?? null) : null;

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
  const until = untilIso(sinceHours, customRange);
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
    return customRangeBounds(r)
      ? `${r.start} ${r.startTime} – ${r.end} ${r.endTime}`
      : 'Custom range (choose dates and times)';
  }
  return CORE_SINCE_OPTIONS.find((o) => o.value === String(sinceHours ?? ''))?.label || 'Any time';
};
