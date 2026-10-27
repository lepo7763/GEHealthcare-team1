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
  const umfSelected = selected.includes('umf-rti');
  const domainValid = validateDomain(umfDomain);
  const durationValid = validateDuration(umfDuration);
  const umfOptionsValid = !umfSelected || (domainValid && durationValid);

  return (
    <section className="section-narrow">
      <div className="card">
        <h3 className="card-title">Collection services</h3>
        <p className="card-subtitle">
          Select and configure the services to include in this diagnostic session.
        </p>

        <ul className="service-list">
          {SERVICES.map((service) => {
            const isSelected = selected.includes(service.id);
            return (
              <li key={service.id}>
                <button
                  type="button"
                  className={`service-option ${isSelected ? 'selected' : ''}`}
                  aria-pressed={isSelected}
                  onClick={() => onToggleService(service.id)}
                >
                  <div>
                    <div className="check-title">{service.name}</div>
                    <div className="check-detail">{service.description}</div>
                  </div>
                  <span className="service-check" aria-hidden="true">
                    {isSelected ? '✓' : ''}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        {umfSelected && (
          <div className="service-options" aria-label="UMF RTI options">
            <h4 className="service-options-title">UMF RTI options</h4>
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
          </div>
        )}

        <div className="action-row">
          <button className="btn btn-secondary" onClick={onBack}>
            Back
          </button>
          <button
            className="btn btn-primary"
            onClick={onContinue}
            disabled={selected.length === 0 || !umfOptionsValid}
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
