// Parameters for the Core Dumps tool (see backend CoreDumpParams).
import {
  CORE_DEFAULT_MB,
  CORE_MAX_MB,
  CORE_MIN_MB,
  describeCoreFilters,
  sinceIso,
  validateCoreMaxMb,
} from './coreDumps';

export const DEFAULT_CORE_PARAMS = {
  sinceHours: '',
  processes: [],
  maxMb: CORE_DEFAULT_MB,
};

// Converts the Core Dumps form value into /api/logs/zip query params. Throws an
// Error with a user-facing message when invalid.
export const toCoreQuery = (value) => {
  if (!validateCoreMaxMb(value.maxMb)) {
    throw new Error(`Enter a size cap between ${CORE_MIN_MB} and ${CORE_MAX_MB} MB.`);
  }
  const query = new URLSearchParams();
  const since = sinceIso(value.sinceHours);
  if (since) query.set('core_since', since);
  (value.processes || []).forEach((name) => query.append('core_process', name));
  query.set('core_max_mb', String(value.maxMb).trim());
  return query;
};

// One-line summary for the Review step.
export const summarizeCore = (value) => describeCoreFilters(value);
