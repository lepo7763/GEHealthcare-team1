// Parameters for the UMF RTI tool (see backend UmfRtiParams).

export const UMF_DURATION_MIN = 10;
export const UMF_DURATION_MAX = 600;

export const DEFAULT_UMF_PARAMS = {
  domainId: 13,
  durationSeconds: '60',
};

// Used if GET /api/umf-rti/domains can't be reached.
export const FALLBACK_UMF_DOMAINS = [
  { domain: 13, label: 'Viewer — live vitals (viewpod)' },
  { domain: 12, label: 'Source — from Hub (sourcepod)' },
  { domain: 7, label: 'Logger' },
];

// Converts the UMF RTI form value into /api/logs/zip query params. Throws an
// Error with a user-facing message when invalid.
export const toUmfQuery = (value) => {
  const raw = String(value.durationSeconds ?? '').trim();
  const duration = Number(raw);
  if (
    raw === '' ||
    !Number.isInteger(duration) ||
    duration < UMF_DURATION_MIN ||
    duration > UMF_DURATION_MAX
  ) {
    throw new Error(
      `Enter a capture duration between ${UMF_DURATION_MIN} and ${UMF_DURATION_MAX} seconds.`,
    );
  }
  return new URLSearchParams({
    umf_domain_id: String(value.domainId),
    umf_duration_seconds: String(duration),
  });
};

// One-line summary for the Review step.
export const summarizeUmf = (value) =>
  `Domain ${value.domainId} · ${String(value.durationSeconds).trim() || '—'} seconds`;
