// Helpers for the Prometheus Database service (Configure + Review steps).
import { CUSTOM_RANGE, describeTimeRange } from './timeRange.js';

// The database can be many GB, so the presets are short and there is no default
// "everything" — it's offered last.
export const PROM_SINCE_OPTIONS = [
  { value: '6', label: 'Last 6 hours' },
  { value: '24', label: 'Last 24 hours' },
  { value: '168', label: 'Last 7 days' },
  { value: '720', label: 'Last 30 days' },
  { value: CUSTOM_RANGE, label: 'Custom' },
  { value: '', label: 'Entire database' },
];

export const DEFAULT_PROM_SINCE = '24';

export const describePromFilters = (filters) => describeTimeRange(PROM_SINCE_OPTIONS, filters);
