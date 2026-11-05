import assert from 'node:assert/strict';
import { test, mock } from 'node:test';
import { buildLogExportQuery, downloadLogs } from '../src/lib/logExport.js';

const filters = {
  scope: 'device',
  format: 'csv',
  deviceuuid: 'd4e5f6a7-1234-5678-9abc-def012345678',
  eventCategory: '',
  startTimestamp: '2024-01-15T09:00',
  endTimestamp: '2024-01-15T09:45',
};

test('normalizes browser datetime values without converting the selected local time', () => {
  const params = buildLogExportQuery(filters);
  assert.equal(params.get('startTimestamp'), '2024-01-15T09:00:00.000');
  assert.equal(params.get('endTimestamp'), '2024-01-15T09:45:00.000');
  assert.equal(params.get('deviceuuid'), filters.deviceuuid);
  assert.equal(params.has('eventCategory'), false);
});

test('preserves fractional seconds and sends category zero', () => {
  const params = buildLogExportQuery({ ...filters, startTimestamp: '2024-01-15T09:00:01.12', eventCategory: '0' });
  assert.equal(params.get('startTimestamp'), '2024-01-15T09:00:01.120');
  assert.equal(params.get('eventCategory'), '0');
});

test('all-device JSON requests omit a previously entered device UUID', () => {
  const params = buildLogExportQuery({ ...filters, scope: 'all', format: 'json', eventCategory: '3' });
  assert.equal(params.has('deviceuuid'), false);
  assert.equal(params.get('scope'), 'all');
  assert.equal(params.get('format'), 'json');
  assert.equal(params.get('eventCategory'), '3');
});

test('accepts the seven-day device limit, including a daylight saving transition', () => {
  const params = buildLogExportQuery({ ...filters, startTimestamp: '2024-03-08T09:00', endTimestamp: '2024-03-15T09:00' });
  assert.equal(params.get('endTimestamp'), '2024-03-15T09:00:00.000');
});

for (const [name, changes, message] of [
  ['missing UUID', { deviceuuid: '' }, /valid device UUID/],
  ['malformed UUID', { deviceuuid: 'pod-name' }, /valid device UUID/],
  ['missing start', { startTimestamp: '' }, /valid start/],
  ['invalid calendar date', { startTimestamp: '2024-02-30T09:00' }, /valid start/],
  ['timezone suffix', { startTimestamp: '2024-01-15T09:00:00Z' }, /valid start/],
  ['equal timestamps', { endTimestamp: filters.startTimestamp }, /after start/],
  ['reversed timestamps', { endTimestamp: '2024-01-15T08:59' }, /after start/],
  ['over seven days', { endTimestamp: '2024-01-22T09:00:00.001' }, /7 days/],
  ['crossing an hour for all devices', { scope: 'all', endTimestamp: '2024-01-15T10:00' }, /same start and end hour/],
  ['same hour on different days', { scope: 'all', endTimestamp: '2024-01-16T09:00' }, /1 hour/],
  ['named category', { eventCategory: 'Security' }, /whole-number/],
  ['fractional category', { eventCategory: '1.5' }, /whole-number/],
]) {
  test(`rejects ${name}`, () => {
    assert.throws(() => buildLogExportQuery({ ...filters, ...changes }), message);
  });
}

for (const [name, body, message] of [
  ['backend detail', { detail: 'Log service is unreachable.' }, /Log service is unreachable/],
  ['upstream array', ['Invalid timestamp Format', 'Unknown category'], /Invalid timestamp Format Unknown category/],
  ['FastAPI validation', { detail: [{ msg: 'Field required' }] }, /Field required/],
  ['non-JSON error', null, /Could not export logs/],
]) {
  test(`shows a useful download error for ${name}`, async () => {
    mock.method(globalThis, 'fetch', async () => new Response(body === null ? '<html>Error</html>' : JSON.stringify(body), { status: 400 }));
    try {
      await assert.rejects(downloadLogs('/api/logs/export', 'logs.csv'), message);
    } finally {
      mock.restoreAll();
    }
  });
}
