import { SERVICE_STATUS_LABEL, STATUS_LABEL } from './constants';

const ServiceProgressCard = ({ service }) => {
  const status = service.status || 'pending';
  const total = Number(service.total) || 0;
  const completed = Number(service.completed) || 0;
  const unit = service.unit || 'items';
  const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  const displayPercent = status === 'done' ? 100 : percent;
  const isDeterminate = total > 0;
  const isRunning = status === 'collecting';
  const progressClass = isDeterminate ? '' : isRunning ? 'progress-indeterminate' : '';

  return (
    <div className={`service-progress-card service-progress-${status}`}>
      <div className="service-progress-head">
        <div>
          <div className="check-title">{service.label}</div>
          <div className="check-detail">
            {SERVICE_STATUS_LABEL[status] || status}
            {total > 0 ? ` · ${completed} of ${total} ${unit}` : ''}
          </div>
        </div>
        {total > 0 && (
          <span className="service-progress-percent">{displayPercent}%</span>
        )}
      </div>

      <div
        className={`progress ${progressClass}`}
        role="progressbar"
        aria-label={`${service.label} progress`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={isDeterminate ? displayPercent : undefined}
      >
        <div
          className="progress-fill"
          style={isDeterminate ? { width: `${displayPercent}%` } : undefined}
        />
      </div>

      {service.current && (
        <p className="collect-meta">
          Current: <span className="mono">{service.current}</span>
        </p>
      )}
      {service.error && <p className="collect-meta collect-error">{service.error}</p>}
      {service.errors > 0 && (
        <p className="collect-meta">
          {service.errors} error{service.errors === 1 ? '' : 's'}
        </p>
      )}
    </div>
  );
};

const Step4Collect = ({ collect, collectError, download, onBack }) => {
  const services = collect?.services || [];
  const collectStatus = collect?.status || 'idle';
  const collectFailed =
    collectError || (collectStatus === 'error' ? collect?.message || 'Collection failed.' : '');
  const serviceErrors = services.filter((service) => service.status === 'error').length;
  const totalErrors = services.reduce((sum, service) => sum + (service.errors || 0), 0);
  const allDone = collectStatus === 'done';

  return (
    <section className="section-narrow">
      <div className="card">
        <h3 className="card-title">Collect</h3>
        <p className="card-subtitle">
          Collecting from the selected services. Each service reports its own progress
          and units.
        </p>

        <div
          className="collect-panel"
          aria-busy={collectStatus === 'collecting' || collectStatus === 'packaging'}
        >
          {collectFailed && (
            <div className="alert alert-error" role="alert">
              <strong>Collection failed</strong>
              <span>{collectFailed}</span>
            </div>
          )}

          {!collectFailed && allDone && (
            <div
              className={`alert ${serviceErrors ? 'alert-warning' : 'alert-success'}`}
              role="status"
            >
              <strong>
                {serviceErrors ? 'Collection completed with errors' : 'Collection complete'}
              </strong>
              <span>
                {serviceErrors > 0
                  ? `${serviceErrors} service${serviceErrors === 1 ? '' : 's'} failed`
                  : 'All selected services finished'}
                {totalErrors > 0
                  ? ` · ${totalErrors} error${totalErrors === 1 ? '' : 's'} reported`
                  : ''}
                .
              </span>
            </div>
          )}

          {services.length > 0 ? (
            <div className="service-progress-list">
              {services.map((service) => (
                <ServiceProgressCard key={service.id} service={service} />
              ))}
            </div>
          ) : (
            !collectFailed &&
            !allDone && (
              <>
                <div
                  className="progress progress-indeterminate"
                  role="progressbar"
                  aria-label="Starting collection"
                >
                  <div className="progress-fill" />
                </div>
                <p className="collect-meta">
                  {STATUS_LABEL[collectStatus] || 'Starting collection…'}
                </p>
              </>
            )
          )}

          {download && (
            <div className="action-row">
              <a className="btn btn-primary" href={download.url} download={download.filename}>
                Download diagnostic package
              </a>
            </div>
          )}
        </div>

        <div className="action-row">
          <button className="btn btn-secondary" onClick={onBack}>
            Back
          </button>
        </div>
      </div>
    </section>
  );
};

export default Step4Collect;
