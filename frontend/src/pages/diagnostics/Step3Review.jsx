<<<<<<< HEAD
const Step3Review = ({ result, selectedServices, onEditConnection, onEditServices, onBack, onStart }) => {
=======
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
      ? selectedServices
          .map((service) =>
            service.id === 'umf-rti'
              ? `UMF RTI — domain ${String(umfDomain).trim()}, ${String(umfDuration).trim()} s`
              : service.name,
          )
          .join(', ')
      : 'None selected';
  const umfSelected = selectedServices.some((service) => service.id === 'umf-rti');
  const domainIsTwelve = umfSelected && Number(umfDomain) === 12;

>>>>>>> 330af8665a8b336209bb6982de5a0421e7099edf
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
<<<<<<< HEAD
                  {result.recorded
                    ? 'Previously collected Kubernetes PCAPs (offline demo)'
                    : `${result.host}:${result.port}`}
=======
                  {result.host}:{result.port}
>>>>>>> 330af8665a8b336209bb6982de5a0421e7099edf
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
<<<<<<< HEAD
              <div className="check-detail">
                {selectedServices.length > 0
                  ? selectedServices.map((service) => service.name).join(', ')
                  : 'None selected'}
              </div>
=======
              <div className="check-detail">{serviceSummary}</div>
>>>>>>> 330af8665a8b336209bb6982de5a0421e7099edf
            </div>
            <button className="link-btn" onClick={onEditServices}>
              Edit
            </button>
          </li>
<<<<<<< HEAD
        </ul>

=======
          {umfSelected && (
            <li>
              <div>
                <div className="check-title">UMF RTI capture</div>
                <div className="check-detail">
                  Discovery and QoS only; no sample values are read. The capture runs
                  in a short-lived Kubernetes Job and is deleted afterwards.
                </div>
              </div>
            </li>
          )}
        </ul>

        {domainIsTwelve && (
          <div className="alert alert-warning">
            <strong>Domain 12 may be denied by RTI security</strong>
            <span>
              The commissioning identity in this lab is permitted on domains 2 and 32.
              Domain 12 needs a dedicated UMF RTI identity; otherwise the capture will
              fail with an actionable security error.
            </span>
          </div>
        )}

>>>>>>> 330af8665a8b336209bb6982de5a0421e7099edf
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
