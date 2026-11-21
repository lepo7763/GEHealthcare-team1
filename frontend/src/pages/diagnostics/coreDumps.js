// Helpers for the Core Dumps service (Configure + Review steps).
// The estimate mirrors the backend's select_files(): filter by time. There is no size cap; every matching core is collected.

export const CORE_SINCE_OPTIONS = [
  { value: '', label: 'Any time' },
  { value: '24', label: 'Last 24 hours' },
  { value: '168', label: 'Last 7 days' },
  { value: '720', label: 'Last 30 days' },
];

export const sinceIso = (hours, now = Date.now()) =>
  hours ? new Date(now - Number(hours) * 3600 * 1000).toISOString() : null;

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

export const estimateSelection = (files, { sinceHours }, now = Date.now()) => {
  const since = sinceIso(sinceHours, now);
  let bytes = 0;
  let count = 0;
  for (const file of files || []) {
    if (since && new Date(file.time_utc) < new Date(since)) continue;
    bytes += file.size_bytes;
    count += 1;
  }
  return { count, bytes };
};

export const describeCoreFilters = ({ sinceHours }) =>
  CORE_SINCE_OPTIONS.find((o) => o.value === String(sinceHours ?? ''))?.label || 'Any time';
