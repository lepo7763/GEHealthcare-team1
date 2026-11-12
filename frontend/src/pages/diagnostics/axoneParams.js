import { format } from 'date-fns';
import { toLocalDateTime } from '../../lib/dateTime';
import { normalizeTime } from '../../lib/time';
import { buildAxoneLogParams } from '../../lib/logExport';

export const DEFAULT_AXONE_PARAMS = {
  scope: 'device',
  deviceuuid: '',
  eventCategory: '',
  start: { date: undefined, time: '' },
  end: { date: undefined, time: '' },
};

// Converts the Axone form value into the /api/logs/zip query params. Throws an
// Error with a user-facing message when the parameters are incomplete or invalid.
export const toAxoneQuery = (value) =>
  buildAxoneLogParams({
    scope: value.scope,
    deviceuuid: value.deviceuuid,
    eventCategory: value.eventCategory,
    startTimestamp: toLocalDateTime(value.start.date, normalizeTime(value.start.time)),
    endTimestamp: toLocalDateTime(value.end.date, normalizeTime(value.end.time)),
  });

const formatPoint = ({ date, time }) => {
  if (!date) return 'not set';
  const t = normalizeTime(time);
  return `${format(date, 'MMM d, yyyy')} ${t ? t.slice(0, 8) : '(no time)'}`;
};

// One-line summary for the Review step.
export const summarizeAxone = (value) =>
  [
    value.scope === 'device' ? `One device ${value.deviceuuid.trim() || '(no UUID)'}` : 'All devices',
    `${formatPoint(value.start)} → ${formatPoint(value.end)}`,
    value.eventCategory.trim() === '' ? 'All events' : `Event category ${value.eventCategory.trim()}`,
    'CSV',
  ].join(' · ');
