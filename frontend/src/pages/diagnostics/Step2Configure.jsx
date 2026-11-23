import { useState } from 'react';
import { SERVICES } from './constants';
import AxoneLogSettings from './AxoneLogSettings';
import { summarizeAxone, toAxoneQuery } from './axoneParams';
import TimeRangeSettings from './TimeRangeSettings';
import { CORE_SINCE_OPTIONS, describeCoreFilters } from './coreDumps';
import { PROM_SINCE_OPTIONS, describePromFilters } from './prometheus';
import { isTimeRangeValid } from './timeRange';
import CmsSettings from './cmsSettings';
import { summarizeCms, toCmsQuery } from './cmsParams';

// Must match the backend's UmfRtiParams.umf_duration_seconds bounds.
const MIN_DURATION = 10;
const MAX_DURATION = 600;
const NETSHOOT_MIN_DURATION = 1;

const validateDuration = (value, minDuration = MIN_DURATION) => {
  const text = String(value ?? '').trim();
  const number = Number(text);
  return (
    text !== '' && Number.isInteger(number) && number >= minDuration && number <= MAX_DURATION
  );
};

// Validation message for the Axone settings, or null when they're complete.
const axoneIssue = (value) => {
  try {
    toAxoneQuery(value);
    return null;
  } catch (e) {
    return e.message;
  }
};

const Step2Configure = ({
  selected,
  onToggleService,
  umfDomain,
  setUmfDomain,
  umfDuration,
  setUmfDuration,
  umfDomainOptions,
  netshootDuration,
  setNetshootDuration,
  axoneParams,
  setAxoneParams,
  cmsParams,
  setCmsParams,
  coreSinceHours,
  setCoreSinceHours,
  coreCustomRange,
  setCoreCustomRange,
  promSinceHours,
  setPromSinceHours,
  promCustomRange,
  setPromCustomRange,
  onBack,
  onContinue,
}) => {
  const domainOption = umfDomainOptions.find((option) => option.domain === Number(umfDomain));
  const domainValid = Boolean(domainOption);
  const durationValid = validateDuration(umfDuration);
  const netshootDurationValid = validateDuration(netshootDuration, NETSHOOT_MIN_DURATION);
  const axoneError = axoneIssue(axoneParams);
  const promFilters = { sinceHours: promSinceHours, customRange: promCustomRange };
  const promValid = isTimeRangeValid(promFilters);
  const cmsError = (() => {
    try {
      toCmsQuery(cmsParams);
      return null;
    } catch (e) {
      return e.message;
    }
  })();

  // Settings for each service that has any, keyed by service id. To give a new service
  // (e.g. Netshoot) its own settings, add an entry here: whether its values are valid,
  // a one-line summary shown while collapsed, and the fields shown while expanded.
  const settingsPanels = {
    'umf-rti': {
      isValid: domainValid && durationValid,
      summary: `Domain ${umfDomain}${domainOption ? ` · ${domainOption.label}` : ''} · ${String(umfDuration).trim() || '—'} s`,
      fields: (
        <>
          <div className="form-row">
            <label className="field grow">
              <span>Domain</span>
              <select
                value={umfDomain}
                onChange={(e) => setUmfDomain(Number(e.target.value))}
                aria-invalid={!domainValid}
              >
                {umfDomainOptions.map((option) => (
                  <option key={option.domain} value={option.domain}>
                    {option.domain} · {option.label}
                  </option>
                ))}
              </select>
              <small>The DDS domain to record.</small>
              {!domainValid && <small className="field-error">Choose a domain.</small>}
            </label>
            <label className="field grow">
              <span>Capture duration (seconds)</span>
              <input
                type="number"
                min={MIN_DURATION}
                max={MAX_DURATION}
                step="1"
                value={umfDuration}
                onChange={(e) => setUmfDuration(e.target.value)}
                aria-invalid={!durationValid}
              />
              <small>
                Between {MIN_DURATION} and {MAX_DURATION} seconds.
              </small>
              {!durationValid && (
                <small className="field-error">
                  Enter a whole number from {MIN_DURATION} to {MAX_DURATION}.
                </small>
              )}
            </label>
          </div>
        </>
      ),
    },
    'netshoot': {
      isValid: netshootDurationValid,
      summary: `${String(netshootDuration).trim() || '—'} s`,
      fields: (
        <div className="form-row">
          <label className="field grow">
            <span>Capture duration (seconds)</span>
            <input
              type="number"
              min={NETSHOOT_MIN_DURATION}
              max={MAX_DURATION}
              step="1"
              value={netshootDuration}
              onChange={(e) => setNetshootDuration(e.target.value)}
              aria-invalid={!netshootDurationValid}
            />
            <small>
              Between {NETSHOOT_MIN_DURATION} and {MAX_DURATION} seconds.
            </small>
            {!netshootDurationValid && (
              <small className="field-error">
                Enter a whole number from 1 to 600.
              </small>
            )}
          </label>
        </div>
      ),
    },
    'axone-logs': {
      isValid: !axoneError,
      summary: summarizeAxone(axoneParams),
      fields: (
        <AxoneLogSettings value={axoneParams} onChange={setAxoneParams} issue={axoneError} />
      ),
    },
    cms: {
      isValid: !cmsError,
      summary: summarizeCms(cmsParams),
      fields: (
        <CmsSettings
          value={cmsParams}
          onChange={setCmsParams}
          issue={cmsError}
        />
      ),
    },
    'core-dumps': {
      isValid: isTimeRangeValid({ sinceHours: coreSinceHours, customRange: coreCustomRange }),
      summary: describeCoreFilters({ sinceHours: coreSinceHours, customRange: coreCustomRange }),
      fields: (
        <TimeRangeSettings
          label="Dumped since"
          hint="Based on the crash time recorded in each core's filename."
          options={CORE_SINCE_OPTIONS}
          sinceHours={coreSinceHours}
          setSinceHours={setCoreSinceHours}
          customRange={coreCustomRange}
          setCustomRange={setCoreCustomRange}
        />
      ),
    },
    prometheus: {
      isValid: promValid,
      summary: describePromFilters(promFilters),
      fields: (
        <TimeRangeSettings
          label="Data from"
          hint="Prometheus stores data in blocks of 2 hours or more, so whole blocks overlapping this window are exported."
          options={PROM_SINCE_OPTIONS}
          sinceHours={promSinceHours}
          setSinceHours={setPromSinceHours}
          customRange={promCustomRange}
          setCustomRange={setPromCustomRange}
        />
      ),
    },

  };

  // Only one service's settings are open at a time, so the boxes don't stack up.
  // Start with the first selected service whose settings still need fixing, if any.
  const [expandedId, setExpandedId] = useState(
    () => selected.find((id) => settingsPanels[id] && !settingsPanels[id].isValid) ?? null,
  );

  const toggleService = (id) => {
    const wasSelected = selected.includes(id);
    onToggleService(id);
    if (!wasSelected && settingsPanels[id]) {
      // Just picked a service that needs settings: open them (closes any other).
      setExpandedId(id);
    } else if (wasSelected && expandedId === id) {
      setExpandedId(null);
    }
  };

  const allSettingsValid = selected.every((id) => !settingsPanels[id] || settingsPanels[id].isValid);

  return (
    <section className="section-narrow">
      <div className="card">
        <h3 className="card-title">Collection services</h3>
        <p className="card-subtitle">
          Select and configure the services to include in this diagnostic session.
        </p>

        <ul className="service-list service-list-stacked">
          {SERVICES.map((service) => {
            const isSelected = selected.includes(service.id);
            const panel = isSelected ? settingsPanels[service.id] : null;
            const isExpanded = panel && expandedId === service.id;
            const panelId = `settings-${service.id}`;

            return (
              <li key={service.id} className={panel ? 'has-settings' : ''}>
                <button
                  type="button"
                  className={`service-option ${isSelected ? 'selected' : ''}`}
                  aria-pressed={isSelected}
                  onClick={() => toggleService(service.id)}
                >
                  <div>
                    <div className="check-title">{service.name}</div>
                    <div className="check-detail">{service.description}</div>
                  </div>
                  <span className="service-check" aria-hidden="true">
                    {isSelected ? '✓' : ''}
                  </span>
                </button>

                {panel && (
                  <button
                    type="button"
                    className={`service-settings-summary ${panel.isValid ? '' : 'invalid'}`}
                    aria-expanded={!!isExpanded}
                    aria-controls={panelId}
                    disabled={isExpanded && !panel.isValid}
                    onClick={() => setExpandedId(isExpanded ? null : service.id)}
                  >
                    <span>
                      {panel.isValid ? panel.summary : 'Settings need attention'}
                    </span>
                    <span className="service-settings-edit">
                      Edit settings {isExpanded ? '▴' : '▾'}
                    </span>
                  </button>
                )}

                {isExpanded && (
                  <div
                    id={panelId}
                    className="service-options"
                    role="region"
                    aria-label={`${service.name} settings`}
                  >
                    {panel.fields}
                  </div>
                )}
              </li>
            );
          })}
        </ul>

        <div className="action-row">
          <button className="btn btn-secondary" onClick={onBack}>
            Back
          </button>
          <button
            className="btn btn-primary"
            onClick={onContinue}
            disabled={selected.length === 0 || !allSettingsValid}
          >
            Continue to review
          </button>
        </div>

        {/* Always rendered (visibility-toggled) so showing the hint doesn't
            change the page height and jolt the layout/scrollbar. */}
        <p
          className="future-note future-note-error"
          style={{ visibility: selected.length === 0 ? 'visible' : 'hidden' }}
        >
          Select at least one service to continue.
        </p>
      </div>
    </section>
  );
};

export default Step2Configure;