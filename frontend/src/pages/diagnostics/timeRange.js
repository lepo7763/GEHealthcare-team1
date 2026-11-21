// Time-window helpers shared by the services that collect "data from a time range"
// (Core Dumps, Prometheus). A window is { sinceHours, customRange }: sinceHours is a
// preset ('' = any time, '24' = last 24 hours, ...) or CUSTOM_RANGE.

export const CUSTOM_RANGE = 'custom';

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

// Label for a window, using the service's own preset list.
export const describeTimeRange = (options, { sinceHours, customRange }) => {
  if (sinceHours === CUSTOM_RANGE) {
    const r = customRange || EMPTY_CUSTOM_RANGE;
    const endText = r.endNow && r.end === dateKey() ? 'now' : r.endTime;
    return customRangeBounds(r)
      ? `${r.start} ${r.startTime} – ${r.end} ${endText}`
      : 'Custom range (choose dates and times)';
  }
  return options.find((o) => o.value === String(sinceHours ?? ''))?.label || 'Any time';
};

export const isTimeRangeValid = ({ sinceHours, customRange }) =>
  sinceHours !== CUSTOM_RANGE || isCustomRangeValid(customRange);
