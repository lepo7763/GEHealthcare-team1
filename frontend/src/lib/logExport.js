const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function localTimestamp(value, label) {
  const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?$/.exec(value);
  if (!match) throw new Error(`Enter a valid ${label} date and time.`);

  const timestamp = `${match[1]}:${match[2] || '00'}.${(match[3] || '').padEnd(3, '0')}`;
  // Use UTC only for calendar arithmetic, so browser time zones and DST cannot
  // change the selected interval. The API receives the original local time.
  const milliseconds = Date.parse(`${timestamp}Z`);
  if (!Number.isFinite(milliseconds) || new Date(milliseconds).toISOString() !== `${timestamp}Z`) {
    throw new Error(`Enter a valid ${label} date and time.`);
  }
  return { timestamp, milliseconds };
}


export function buildAxoneLogParams({ scope, deviceuuid, eventCategory, startTimestamp, endTimestamp }) {
  if (!['device', 'all'].includes(scope)) {
    throw new Error('Choose a valid device scope.');
  }

  const start = localTimestamp(startTimestamp, 'start');
  const end = localTimestamp(endTimestamp, 'end');
  const duration = end.milliseconds - start.milliseconds;
  if (duration <= 0) throw new Error('End time must be after start time.');
  if (scope === 'device' && duration > 7 * 24 * 60 * 60 * 1000) {
    throw new Error('For one device, choose a time range of 7 days or less.');
  }
  if (scope === 'all' && (duration > 60 * 60 * 1000 || start.timestamp.slice(11, 13) !== end.timestamp.slice(11, 13))) {
    throw new Error('For all devices, choose a range of 1 hour or less with the same start and end hour.');
  }

  const params = new URLSearchParams({
    axone_scope: scope,
    axone_start_timestamp: start.timestamp,
    axone_end_timestamp: end.timestamp,
  });
  if (scope === 'device') {
    const uuid = (deviceuuid || '').trim();
    if (!UUID_PATTERN.test(uuid)) throw new Error('Enter a valid device UUID.');
    params.set('axone_device_uuid', uuid);
  }

  const category = (eventCategory || '').trim();
  if (category !== '') {
    if (!/^[+-]?\d+$/.test(category) || !Number.isSafeInteger(Number(category))) {
      throw new Error('Enter a whole-number event category code, or leave it blank for all events.');
    }
    params.set('axone_event_category', String(Number(category)));
  }
  return params;
}
