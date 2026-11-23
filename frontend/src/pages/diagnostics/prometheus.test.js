import test from 'node:test';
import assert from 'node:assert/strict';
import { describePromFilters } from './prometheus.js';

test('labels', () => {
  assert.equal(describePromFilters({ sinceHours: '' }), 'Entire database');
  assert.equal(describePromFilters({ sinceHours: '24' }), 'Last 24 hours');
});
