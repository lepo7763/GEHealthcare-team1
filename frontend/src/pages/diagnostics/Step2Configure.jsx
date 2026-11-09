import { useState } from 'react';
import { SERVICES } from './constants';

const validateDomain = (value) => {
  const text = String(value ?? '').trim();
  const number = Number(text);
  return text !== '' && Number.isInteger(number) && number >= 0 && number <= 100;
};

const validateDuration = (value) => {
  const text = String(value ?? '').trim();
  const number = Number(text);
  return text !== '' && Number.isInteger(number) && number >= 30 && number <= 600;
};

const Step2Configure = ({
  selected,
  onToggleService,
  umfDomain,
  setUmfDomain,
  umfDuration,
  setUmfDuration,
  onBack,
  onContinue,
}) => {
  const domainValid = validateDomain(umfDomain);
  const durationValid = validateDuration(umfDuration);

  // Settings for each service that has any, keyed by service id. To give a new service
  // (e.g. Wireshark) its own settings, add an entry here: whether its values are valid,
  // a one-line summary shown while collapsed, and the fields shown while expanded.
  const settingsPanels = {
    'umf-rti': {
      isValid: domainValid && durationValid,
      summary: `Domain ${String(umfDomain).trim() || '—'} · ${String(umfDuration).trim() || '—'} s`,
      fields: (
        <>
          <div className="form-row">
            <label className="field grow">
              <span>Domain ID</span>
              <input
                type="number"
                min="0"
                max="100"
                step="1"
                value={umfDomain}
                onChange={(e) => setUmfDomain(e.target.value)}
                aria-invalid={!domainValid}
              />
              <small>
                Domain 32 is the live UMF domain in this lab. Domain 12 requires a
                dedicated identity permitted on that domain.
              </small>
              {!domainValid && (
                <small className="field-error">Enter a whole number from 0 to 100.</small>
              )}
            </label>
            <label className="field grow">
              <span>Capture duration (seconds)</span>
              <input
                type="number"
                min="30"
                max="600"
                step="1"
                value={umfDuration}
                onChange={(e) => setUmfDuration(e.target.value)}
                aria-invalid={!durationValid}
              />
              <small>Between 30 and 600 seconds.</small>
              {!durationValid && (
                <small className="field-error">Enter a whole number from 30 to 600.</small>
              )}
            </label>
          </div>
          <p className="future-note">
            UMF RTI captures discovery and QoS metadata only. No sample values or
            patient data are read.
          </p>
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
