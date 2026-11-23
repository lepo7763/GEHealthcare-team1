import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildAxoneLogParams } from '../src/lib/logExport.js';
import { summarizeAxone, toAxoneQuery } from '../src/pages/diagnostics/axoneParams.js';

// Axone filters for the diagnostic package (GET /api/logs/zip?services=axone-logs).
const filters = {
  scope: 'device',
  deviceuuid: 'd4e5f6a7-1234-5678-9abc-def012345678',
  eventCategory: '',
  startTimestamp: '2024-01-15T09:00',
  endTimestamp: '2024-01-15T09:45',
};

test('normalizes local timestamps without converting the selected time', () => {
  const params = buildAxoneLogParams(filters);
  assert.equal(params.get('axone_scope'), 'device');
  assert.equal(params.get('axone_start_timestamp'), '2024-01-15T09:00:00.000');
  assert.equal(params.get('axone_end_timestamp'), '2024-01-15T09:45:00.000');
  assert.equal(params.get('axone_device_uuid'), filters.deviceuuid);
  assert.equal(params.has('axone_event_category'), false);
});

test('preserves fractional seconds and sends category zero', () => {
  const params = buildAxoneLogParams({
    ...filters,
    startTimestamp: '2024-01-15T09:00:01.12',
    eventCategory: '0',
  });
  assert.equal(params.get('axone_start_timestamp'), '2024-01-15T09:00:01.120');
  assert.equal(params.get('axone_event_category'), '0');
});

test('all-device requests omit a previously entered device UUID', () => {
  const params = buildAxoneLogParams({ ...filters, scope: 'all', eventCategory: '3' });
  assert.equal(params.get('axone_scope'), 'all');
  assert.equal(params.has('axone_device_uuid'), false);
  assert.equal(params.get('axone_event_category'), '3');
});

test('trims the device UUID and normalizes the category code', () => {
  const params = buildAxoneLogParams({
    ...filters,
    deviceuuid: `  ${filters.deviceuuid}  `,
    eventCategory: ' +07 ',
  });
  assert.equal(params.get('axone_device_uuid'), filters.deviceuuid);
  assert.equal(params.get('axone_event_category'), '7');
});

test('accepts the seven-day device limit, including a daylight saving transition', () => {
  const params = buildAxoneLogParams({
    ...filters,
    startTimestamp: '2024-03-08T09:00',
    endTimestamp: '2024-03-15T09:00',
  });
  assert.equal(params.get('axone_end_timestamp'), '2024-03-15T09:00:00.000');
});

test('accepts a full hour for all devices within the same clock hour', () => {
  const params = buildAxoneLogParams({
    ...filters,
    scope: 'all',
    startTimestamp: '2024-01-15T09:00',
    endTimestamp: '2024-01-15T09:59:59.999',
  });
  assert.equal(params.get('axone_end_timestamp'), '2024-01-15T09:59:59.999');
});

for (const [name, changes, message] of [
  ['invalid scope', { scope: 'pod' }, /valid device scope/],
  ['missing UUID', { deviceuuid: '' }, /valid device UUID/],
  ['malformed UUID', { deviceuuid: 'pod-name' }, /valid device UUID/],
  ['missing start', { startTimestamp: '' }, /valid start/],
  ['invalid calendar date', { startTimestamp: '2024-02-30T09:00' }, /valid start/],
  ['timezone suffix', { startTimestamp: '2024-01-15T09:00:00Z' }, /valid start/],
  ['missing end', { endTimestamp: '' }, /valid end/],
  ['equal timestamps', { endTimestamp: filters.startTimestamp }, /after start/],
  ['reversed timestamps', { endTimestamp: '2024-01-15T08:59' }, /after start/],
  ['over seven days', { endTimestamp: '2024-01-22T09:00:00.001' }, /7 days/],
  ['crossing an hour for all devices', { scope: 'all', endTimestamp: '2024-01-15T10:00' }, /same start and end hour/],
  ['same hour on different days', { scope: 'all', endTimestamp: '2024-01-16T09:00' }, /1 hour/],
  ['named category', { eventCategory: 'Security' }, /whole-number/],
  ['fractional category', { eventCategory: '1.5' }, /whole-number/],
]) {
  test(`rejects ${name}`, () => {
    assert.throws(() => buildAxoneLogParams({ ...filters, ...changes }), message);
  });
}

// The Configure-step form stores a calendar date and a separate time string.
const formValue = {
  scope: 'device',
  deviceuuid: filters.deviceuuid,
  eventCategory: '',
  start: { date: new Date(2024, 0, 15), time: '9:00' },
  end: { date: new Date(2024, 0, 15), time: '09:45:30.5' },
};

test('builds the query from the date picker form value', () => {
  const params = toAxoneQuery(formValue);
  assert.equal(params.get('axone_start_timestamp'), '2024-01-15T09:00:00.000');
  assert.equal(params.get('axone_end_timestamp'), '2024-01-15T09:45:30.500');
});

test('reports an incomplete form with a user-facing message', () => {
  assert.throws(
    () => toAxoneQuery({ ...formValue, end: { date: undefined, time: '' } }),
    /valid end/,
  );
});

test('summarizes the form for the Review step', () => {
  assert.equal(
    summarizeAxone(formValue),
    `One device ${filters.deviceuuid} · Jan 15, 2024 09:00:00 → Jan 15, 2024 09:45:30 · All events · CSV`,
  );
  assert.match(
    summarizeAxone({ ...formValue, scope: 'all', eventCategory: '4' }),
    /^All devices · .* · Event category 4 · CSV$/,
  );
});
