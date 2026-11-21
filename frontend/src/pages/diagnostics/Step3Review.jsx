import { describeCoreFilters, estimateSelection, formatBytes } from './coreDumps';
import { describePromFilters } from './prometheus';

const Step3Review = ({
  result,
  selectedServices,
  umfDomain,
  umfDuration,
  coreFilters,
  corePreview,
  promFilters,
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
  const coreSelected = selectedServices.some((service) => service.id === 'core-dumps');
  const coreEstimate = corePreview?.data
    ? estimateSelection(corePreview.data.files, coreFilters)
    : null;
  const promSelected = selectedServices.some((service) => service.id === 'prometheus');

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
          {coreSelected && (
            <li>
              <div>
                <div className="check-title">Core dumps</div>
                <div className="check-detail">{describeCoreFilters(coreFilters)}</div>
                {coreEstimate && (
                  <div className="check-detail">
                    About {coreEstimate.count} core{coreEstimate.count === 1 ? '' : 's'} ·{' '}
                    {formatBytes(coreEstimate.bytes)}
                  </div>
                )}
                <div className="check-detail">
                  Read from the node by a short-lived, read-only Kubernetes Job (deleted
                  afterwards). Cores can contain process memory, including patient data —
                  handle the package accordingly.
                </div>
              </div>
            </li>
          )}
          {promSelected && (
            <li>
              <div>
                <div className="check-title">Prometheus database</div>
                <div className="check-detail">{describePromFilters(promFilters)}</div>
                <div className="check-detail">
                  Whole TSDB blocks overlapping the window are copied from the node by a
                  short-lived, read-only Kubernetes Job (deleted afterwards). Large windows
                  can take a while and produce a multi-GB package.
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