import { useEffect, useState } from 'react';
import { FALLBACK_UMF_DOMAINS, UMF_DURATION_MAX, UMF_DURATION_MIN } from './umfParams';

// Controlled form for the UMF RTI tool parameters (domain + capture duration).
const UmfRtiParamsForm = ({ value, onChange }) => {
  const [domains, setDomains] = useState(FALLBACK_UMF_DOMAINS);
  const set = (patch) => onChange({ ...value, ...patch });

  useEffect(() => {
    let cancelled = false;
    fetch('/api/umf-rti/domains')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && Array.isArray(data) && data.length > 0) setDomains(data);
      })
      .catch(() => {
        /* keep the fallback list */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <fieldset className="log-export-fields log-export-form">
      <legend className="log-export-legend">UMF RTI capture</legend>
      <div className="log-export-grid">
        <label className="field">
          <span>Domain</span>
          <select
            value={value.domainId}
            onChange={(event) => set({ domainId: Number(event.target.value) })}
          >
            {domains.map((option) => (
              <option key={option.domain} value={option.domain}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Duration (seconds)</span>
          <input
            type="number"
            step="1"
            min={UMF_DURATION_MIN}
            max={UMF_DURATION_MAX}
            value={value.durationSeconds}
            onChange={(event) => set({ durationSeconds: event.target.value })}
            required
          />
          <small>
            {UMF_DURATION_MIN}–{UMF_DURATION_MAX} seconds.
          </small>
        </label>
      </div>
    </fieldset>
  );
};

export default UmfRtiParamsForm;
