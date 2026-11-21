import test from 'node:test';
import assert from 'node:assert/strict';
import {
  describeCoreFilters,
  estimateSelection,
  formatBytes,
  sinceIso,
} from './coreDumps.js';

const MB = 1024 * 1024;
const file = (process, iso, size, signal = 'SIGABRT') => ({
  process,
  time_utc: iso,
  size_bytes: size,
  signal_name: signal,
});

const FILES = [
  file('xGate', '2026-11-12T22:06:36Z', MB / 2),
  file('systemd-journal', '2026-11-10T10:00:00Z', MB),
  file('xGate', '2026-11-01T00:00:00Z', MB / 2, 'SIGSEGV'),
  file(null, '2026-11-11T00:00:00Z', 10),
];

test('estimate has no size cap: every matching core counts', () => {
  const est = estimateSelection(FILES, { sinceHours: '' });
  assert.deepEqual(est, { count: 4, bytes: 2 * MB + 10 });
});

test('estimate applies the since filter', () => {
  const now = Date.parse('2026-11-13T00:00:00Z');
  const est = estimateSelection(FILES, { sinceHours: '168' }, now);
  assert.deepEqual(est, { count: 3, bytes: 1.5 * MB + 10 });
});

test('sinceIso is null for "any time"', () => {
  assert.equal(sinceIso(''), null);
  assert.equal(sinceIso('24', Date.parse('2026-11-13T00:00:00Z')), '2026-11-12T00:00:00.000Z');
});

test('formatting helpers', () => {
  assert.equal(formatBytes(512), '512 B');
  assert.equal(formatBytes(509 * MB), '509 MB');
  assert.equal(formatBytes(1.5 * MB), '1.5 MB');
  assert.equal(
    describeCoreFilters({ sinceHours: '24' }),
    'Last 24 hours',
  );
});

test('custom range filters by start and end', () => {
  const customRange = { start: '2026-11-10', end: '2026-11-12', startTime: '00:00', endTime: '23:59' };
  const est = estimateSelection(FILES, { sinceHours: 'custom', customRange });
  // 11-10 10:00Z and 11-11 00:00Z fall inside (timezone-dependent edges aside); 11-01 does not.
  assert.ok(est.count >= 2 && est.count <= 3);
  assert.equal(sinceIso('custom', Date.now(), { ...customRange, end: '' }), null);
  assert.equal(
    describeCoreFilters({ sinceHours: 'custom', customRange }),
    '2026-11-10 00:00 – 2026-11-12 23:59',
  );
});

test('future times are rejected; "current time" end resolves to now', async () => {
  const { customRangeError, dateKey } = await import('./coreDumps.js');
  const now = Date.parse('2026-11-14T12:00:00');
  const today = dateKey(now);
  const range = { start: today, end: today, startTime: '09:00', endTime: '23:59', endNow: false };
  assert.match(customRangeError(range, now), /future/);
  assert.equal(customRangeError({ ...range, endNow: true }, now), '');
  assert.equal(customRangeError({ ...range, endTime: '11:00' }, now), '');
  assert.match(customRangeError({ ...range, startTime: '13:00', endTime: '11:00' }, now), /future/);
});
