import { useState } from 'react';
import { SERVICES } from './constants';
import {
  NETSHOOT_DEFAULT_SCOPE,
  NETSHOOT_MAX_DURATION,
  NETSHOOT_MIN_DURATION,
  NETSHOOT_SCOPES,
  NETSHOOT_SCOPE_TEXT,
} from './netshootApi';

// Must match the backend's UmfRtiParams.umf_duration_seconds bounds.
const MIN_DURATION = 10;
const MAX_DURATION = 600;

const validateDuration = (value, min = MIN_DURATION, max = MAX_DURATION) => {
  const text = String(value ?? '').trim();
  const number = Number(text);
  return text !== '' && Number.isInteger(number) && number >= min && number <= max;
};

const Step2Configure = ({
  selected,
  onToggleService,
  umfDomain,
  setUmfDomain,
  umfDuration,
  setUmfDuration,
  umfDomainOptions,
  netshootScope,
  setNetshootScope,
  netshootDuration,
  setNetshootDuration,
  onBack,
  onContinue,
}) => {
  const domainOption = umfDomainOptions.find((option) => option.domain === Number(umfDomain));
  const domainValid = Boolean(domainOption);
  const durationValid = validateDuration(umfDuration);

  const netshootScopeValid = Boolean(NETSHOOT_SCOPE_TEXT[netshootScope]);
  const netshootDurationValid = validateDuration(
    netshootDuration,
    NETSHOOT_MIN_DURATION,
    NETSHOOT_MAX_DURATION,
  );

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
    netshoot: {
      isValid: netshootScopeValid && netshootDurationValid,
      summary: `${NETSHOOT_SCOPE_TEXT[netshootScope] || '—'} · ${String(netshootDuration).trim() || '—'} s`,
      fields: (
        <>
          <fieldset className="scope-field">
            <legend>Capture scope</legend>
            <div className="scope-options" role="radiogroup">
              {NETSHOOT_SCOPES.map((option) => (
                <label
                  key={option.value}
                  className={`scope-option ${netshootScope === option.value ? 'selected' : ''}`}
                >
                  <input
                    type="radio"
                    name="netshoot-scope"
                    value={option.value}
                    checked={netshootScope === option.value}
                    onChange={() => setNetshootScope(option.value)}
                  />
                  <span>
                    <strong>{option.label}</strong>
                    {option.detail && ` — ${option.detail}`}
                    {option.value === NETSHOOT_DEFAULT_SCOPE && ' (default)'}
                  </span>
                </label>
              ))}
            </div>
            <small>
              Pod traffic covers every running pod on each node; host traffic covers the
              node&apos;s own network interfaces.
            </small>
          </fieldset>
          <div className="form-row">
            <label className="field grow">
              <span>Capture duration (seconds)</span>
              <input
                type="number"
                min={NETSHOOT_MIN_DURATION}
                max={NETSHOOT_MAX_DURATION}
                step="1"
                value={netshootDuration}
                onChange={(e) => setNetshootDuration(e.target.value)}
                aria-invalid={!netshootDurationValid}
              />
              <small>
                Between {NETSHOOT_MIN_DURATION} and {NETSHOOT_MAX_DURATION} seconds.
              </small>
              {!netshootDurationValid && (
                <small className="field-error">
                  Enter a whole number from {NETSHOOT_MIN_DURATION} to {NETSHOOT_MAX_DURATION}.
                </small>
              )}
            </label>
          </div>
        </>
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

                {panel && !isExpanded && (
                  <button
                    type="button"
                    className={`service-settings-summary ${panel.isValid ? '' : 'invalid'}`}
                    aria-expanded="false"
                    aria-controls={panelId}
                    onClick={() => setExpandedId(service.id)}
                  >
                    <span>
                      {panel.isValid ? panel.summary : 'Settings need attention'}
                    </span>
                    <span className="service-settings-edit">Edit settings ▾</span>
                  </button>
                )}

                {isExpanded && (
                  <div
                    id={panelId}
                    className="service-options"
                    role="region"
                    aria-label={`${service.name} settings`}
                  >
                    <h4 className="service-options-title">{service.name} settings</h4>
                    {panel.fields}
                    <div className="action-row">
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => setExpandedId(null)}
                        disabled={!panel.isValid}
                      >
                        Done
                      </button>
                    </div>
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
