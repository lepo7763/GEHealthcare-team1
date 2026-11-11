const Step3Review = ({
  result,
  selectedServices,
  umfDomain,
  umfDuration,
  onEditConnection,
  onEditServices,
  onBack,
  onStart,
}) => {
  const serviceSummary =
    selectedServices.length > 0
      ? selectedServices.map((service) => service.name).join(', ')
      : 'None selected';
  const umfSelected = selectedServices.some((service) => service.id === 'umf-rti');

  return (
    <section className="section-narrow">
      <div className="card">
        <h3 className="card-title">Review &amp; deploy</h3>
        <p className="card-subtitle">
          Confirm the details below, then go back to any step to make changes.
        </p>

        <ul className="check-list">
          <li>
            <div>
              <div className="check-title">Platform connection</div>
              {result && (
                <div className="check-detail">
                  {result.host}:{result.port}
                </div>
              )}
            </div>
            <button className="link-btn" onClick={onEditConnection}>
              Edit
            </button>
          </li>
          <li>
            <div>
              <div className="check-title">Collection services</div>
              <div className="check-detail">{serviceSummary}</div>
            </div>
            <button className="link-btn" onClick={onEditServices}>
              Edit
            </button>
          </li>
          {umfSelected && (
            <li>
              <div>
                <div className="check-title">UMF RTI capture</div>
                <div className="check-detail">
                  Domain {umfDomain} · {String(umfDuration).trim()} s
                </div>
                <div className="check-detail">
                  Captures live RTI telemetry in a short-lived Kubernetes Job (deleted
                  afterwards) and bundles it into the diagnostic zip.
                </div>
              </div>
            </li>
          )}
        </ul>

        <div className="action-row">
          <button className="btn btn-secondary" onClick={onBack}>
            Back
          </button>
          <button className="btn btn-primary" onClick={onStart}>
            Start collection
          </button>
        </div>
      </div>
    </section>
  );
};

export default Step3Review;