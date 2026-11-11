import { SERVICES } from './constants';

const Step2Configure = ({ selected, onToggleService, onBack, onContinue }) => {
  return (
    <section className="section-narrow">
      <div className="card">
        <h3 className="card-title">Collection services</h3>
        <p className="card-subtitle">
          Select the services to include in this diagnostic session.
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

        {/* TODO(frontend): UMF-RTI configuration UI goes here when umf-rti is
            selected — domain dropdown (from GET /api/umf-rti/domains, default 13)
            + duration. See src/pages/diagnostics/UMF_RTI_TODO.md. Until then the
            capture uses the backend defaults (domain 13, 60s). */}

        <div className="action-row">
          <button className="btn btn-secondary" onClick={onBack}>
            Back
          </button>
          <button
            className="btn btn-primary"
            onClick={onContinue}
            disabled={selected.length === 0}
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
