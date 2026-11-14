// Helpers for the Core Dumps service (Configure + Review steps).
// The estimate mirrors the backend's select_files(): filter by time and
// process, then fill the size cap newest-first, skipping cores that don't fit.

// Must match the backend's CoreDumpParams.max_mb bounds.
export const CORE_MIN_MB = 1;
export const CORE_MAX_MB = 4096;
export const CORE_DEFAULT_MB = '500';

export const CORE_SINCE_OPTIONS = [
  { value: '', label: 'Any time' },
  { value: '24', label: 'Last 24 hours' },
  { value: '168', label: 'Last 7 days' },
  { value: '720', label: 'Last 30 days' },
];

export const validateCoreMaxMb = (value) => {
  const text = String(value ?? '').trim();
  const number = Number(text);
  return text !== '' && Number.isInteger(number) && number >= CORE_MIN_MB && number <= CORE_MAX_MB;
};

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

const processOf = (file) => file.process || '(unrecognized name)';

// [{ process, count, bytes, latest, signals: ['SIGABRT', ...] }] by count desc.
export const groupByProcess = (files) => {
  const groups = new Map();
  for (const file of files || []) {
    const key = processOf(file);
    const group = groups.get(key) || { process: key, count: 0, bytes: 0, latest: null, signals: new Set() };
    group.count += 1;
    group.bytes += file.size_bytes;
    if (!group.latest || file.time_utc > group.latest) group.latest = file.time_utc;
    if (file.signal_name) group.signals.add(file.signal_name);
    groups.set(key, group);
  }
  return [...groups.values()]
    .map((g) => ({ ...g, signals: [...g.signals].sort() }))
    .sort((a, b) => b.count - a.count || a.process.localeCompare(b.process));
};

export const estimateSelection = (files, { sinceHours, processes, maxMb }, now = Date.now()) => {
  const since = sinceIso(sinceHours, now);
  const wanted = new Set(processes || []);
  const budget = (Number(maxMb) || 0) * 1024 * 1024;
  const sorted = [...(files || [])].sort((a, b) => (a.time_utc < b.time_utc ? 1 : -1));
  let bytes = 0;
  let count = 0;
  let skipped = 0;
  for (const file of sorted) {
    if (since && new Date(file.time_utc) < new Date(since)) continue;
    if (wanted.size && !wanted.has(file.process)) continue;
    if (bytes + file.size_bytes > budget) {
      skipped += 1;
      continue;
    }
    bytes += file.size_bytes;
    count += 1;
  }
  return { count, bytes, skipped };
};

export const formatTime = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
};

export const describeCoreFilters = ({ sinceHours, processes, maxMb }) => {
  const since = CORE_SINCE_OPTIONS.find((o) => o.value === String(sinceHours ?? ''))?.label || 'Any time';
  const procs = processes?.length ? processes.join(', ') : 'all processes';
  return `${since} · ${procs} · up to ${String(maxMb).trim() || '—'} MB`;
};
