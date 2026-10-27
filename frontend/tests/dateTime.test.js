import assert from 'node:assert/strict';
import { test } from 'node:test';
import { toLocalDateTime } from '../src/lib/dateTime.js';

test('serializes the calendar day with the chosen local time', () => {
  const date = new Date(2024, 0, 15, 23, 59);
  assert.equal(toLocalDateTime(date, '09:45'), '2024-01-15T09:45');
});

test('retains seconds and millisecond precision for the export API', () => {
  assert.equal(toLocalDateTime(new Date(2024, 0, 15), '09:45:12.123'), '2024-01-15T09:45:12.123');
});

test('preserves the selected wall-clock time during a browser DST gap', () => {
  assert.equal(toLocalDateTime(new Date(2024, 2, 10, 12), '02:30:00'), '2024-03-10T02:30:00');
});

test('leaves incomplete or invalid selections for required-field validation', () => {
  assert.equal(toLocalDateTime(undefined, '09:45'), '');
  assert.equal(toLocalDateTime(new Date(2024, 0, 15), ''), '');
  assert.equal(toLocalDateTime(new Date('invalid'), '09:45'), '');
});

test('keeps independently selected start and end dates and times', () => {
  const start = { date: new Date(2024, 0, 15), time: '23:59:59.999' };
  const end = { date: new Date(2024, 0, 16), time: '00:00:00.001' };
  assert.equal(toLocalDateTime(start.date, start.time), '2024-01-15T23:59:59.999');
  assert.equal(toLocalDateTime(end.date, end.time), '2024-01-16T00:00:00.001');
});
