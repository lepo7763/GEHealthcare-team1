export function normalizeTime(value) {
  if (typeof value !== 'string') return '';
  const match = /^(\d{1,2}):(\d{1,2})(?::(\d{1,2})(?:\.(\d{0,3}))?)?$/.exec(value);
  if (!match) return '';

  const [, hours, minutes, seconds = '00', fraction = ''] = match;
  if (Number(hours) > 23 || Number(minutes) > 59 || Number(seconds) > 59) return '';
  return `${hours.padStart(2, '0')}:${minutes.padStart(2, '0')}:${seconds.padStart(2, '0')}.${fraction.padEnd(3, '0')}`;
}
