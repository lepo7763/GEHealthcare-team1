import test from 'node:test';
import assert from 'node:assert/strict';
import {
  describeCoreFilters,
  estimateSelection,
  formatBytes,
  groupByProcess,
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

test('groups by process, most cores first, unrecognized names labelled', () => {
  const groups = groupByProcess(FILES);
  assert.equal(groups[0].process, 'xGate');
  assert.equal(groups[0].count, 2);
  assert.deepEqual(groups[0].signals, ['SIGABRT', 'SIGSEGV']);
  assert.equal(groups[0].latest, '2026-11-12T22:06:36Z');
  assert.ok(groups.some((g) => g.process === '(unrecognized name)'));
});

test('estimate has no size cap: every matching core counts', () => {
  const est = estimateSelection(FILES, { sinceHours: '', processes: [] });
  assert.deepEqual(est, { count: 4, bytes: 2 * MB + 10 });
});

test('estimate applies since and process filters', () => {
  const now = Date.parse('2026-11-13T00:00:00Z');
  const est = estimateSelection(
    FILES,
    { sinceHours: '168', processes: ['xGate'] },
    now,
  );
  assert.deepEqual(est, { count: 1, bytes: MB / 2 });
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
    describeCoreFilters({ sinceHours: '24', processes: ['xGate'] }),
    'Last 24 hours · xGate',
  );
});
