import assert from 'node:assert/strict';
import { test } from 'node:test';
import { normalizeTime } from '../src/lib/time.js';

test('normalizes existing minute and second precision time values', () => {
  assert.equal(normalizeTime('09:45'), '09:45:00.000');
  assert.equal(normalizeTime('09:45:12'), '09:45:12.000');
});

test('preserves the meaning of fractional seconds', () => {
  assert.equal(normalizeTime('09:45:12.1'), '09:45:12.100');
  assert.equal(normalizeTime('09:45:12.12'), '09:45:12.120');
  assert.equal(normalizeTime('09:45:12.123'), '09:45:12.123');
  assert.equal(normalizeTime('09:45:12.001'), '09:45:12.001');
});

test('normalizes valid single-digit drafts and an optional blank fraction', () => {
  assert.equal(normalizeTime('9:4:2.000'), '09:04:02.000');
  assert.equal(normalizeTime('09:45:12.'), '09:45:12.000');
});

test('accepts both ends of the 24-hour time range', () => {
  assert.equal(normalizeTime('00:00:00.000'), '00:00:00.000');
  assert.equal(normalizeTime('23:59:59.999'), '23:59:59.999');
});

test('rejects incomplete selections, invalid ranges, and timezone suffixes', () => {
  for (const value of ['', undefined, ':30:00.000', '09::00.000', '09:30:.000', '24:00', '12:60', '12:00:60', '12:00:00.1234', '12:00Z', '12:00 PM']) {
    assert.equal(normalizeTime(value), '', String(value));
  }
});
