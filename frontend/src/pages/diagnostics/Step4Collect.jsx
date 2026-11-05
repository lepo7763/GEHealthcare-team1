<<<<<<< HEAD
import { STATUS_LABEL } from './constants';

const Step4Collect = ({ collect, collectError, download, onBack }) => {
  const collectServices = collect?.services || [];
  const containersTotal = collectServices.reduce((sum, s) => sum + (s.containers_total || 0), 0);
  const containersDone = collectServices.reduce((sum, s) => sum + (s.containers_done || 0), 0);
  const collectErrors = collectServices.reduce((sum, s) => sum + (s.errors || 0), 0);
  const currentPod = collectServices.find((s) => s.current)?.current;
  const collectStatus = collect?.status || 'idle';
  const isDeterminate = collectStatus === 'collecting' && containersTotal > 0;
  const percent = containersTotal > 0 ? Math.round((containersDone / containersTotal) * 100) : 0;
  const collectFailed =
    collectError || (collectStatus === 'error' ? collect?.message || 'Collection failed.' : '');
  const statusLabel =
    collectStatus === 'collecting'
      ? `${containersDone} of ${containersTotal} containers (${percent}%)`
      : STATUS_LABEL[collectStatus] || 'Working…';
=======
import { SERVICE_STATUS_LABEL, STATUS_LABEL } from './constants';

const ServiceProgressCard = ({ service }) => {
  const status = service.status || 'pending';
  const total = Number(service.total) || 0;
  const completed = Number(service.completed) || 0;
  const unit = service.unit || 'items';
  const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  const isPending = status === 'pending';
  const isDone = status === 'done';
  // A pending service hasn't started yet: render an empty (light purple) track
  // so it reads as 0% instead of inheriting the fill's full width.
  const displayPercent = isDone ? 100 : isPending ? 0 : percent;
  const isIndeterminate = status === 'collecting' && total === 0;
  const showPercent = isPending || isDone || total > 0;

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
        {showPercent && (
          <span className="service-progress-percent">{displayPercent}%</span>
        )}
      </div>

      <div
        className={isIndeterminate ? 'progress progress-indeterminate' : 'progress'}
        role="progressbar"
        aria-label={`${service.label} progress`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={isIndeterminate ? undefined : displayPercent}
      >
        <div
          className="progress-fill"
          style={isIndeterminate ? undefined : { width: `${displayPercent}%` }}
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
>>>>>>> 330af8665a8b336209bb6982de5a0421e7099edf

  return (
    <section className="section-narrow">
      <div className="card">
        <h3 className="card-title">Collect</h3>
        <p className="card-subtitle">
<<<<<<< HEAD
          Collecting logs from the selected services. This can take a while on large clusters.
        </p>

        <div className="collect-panel">
          {collectFailed && (
            <div className="alert alert-error">
=======
          Collecting from the selected services. Each service reports its own progress
          and units.
        </p>

        <div
          className="collect-panel"
          aria-busy={collectStatus === 'collecting' || collectStatus === 'packaging'}
        >
          {collectFailed && (
            <div className="alert alert-error" role="alert">
>>>>>>> 330af8665a8b336209bb6982de5a0421e7099edf
              <strong>Collection failed</strong>
              <span>{collectFailed}</span>
            </div>
          )}

<<<<<<< HEAD
          {!collectFailed && collectStatus === 'done' && (
            <div className="alert alert-success">
              <strong>Collection complete</strong>
              <span>
                {containersDone} of {containersTotal} containers collected
                {collectErrors > 0
                  ? ` · ${collectErrors} error${collectErrors === 1 ? '' : 's'}`
=======
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
>>>>>>> 330af8665a8b336209bb6982de5a0421e7099edf
                  : ''}
                .
              </span>
            </div>
          )}

<<<<<<< HEAD
          {!collectFailed && collectStatus !== 'done' && (
            <>
              <div
                className={`progress ${isDeterminate ? '' : 'progress-indeterminate'}`}
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={isDeterminate ? percent : undefined}
              >
                <div
                  className="progress-fill"
                  style={isDeterminate ? { width: `${percent}%` } : undefined}
                />
              </div>
              <p className="collect-meta">{statusLabel}</p>
              {currentPod && (
                <p className="collect-meta">
                  Current: <span className="mono">{currentPod}</span>
                </p>
              )}
            </>
=======
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
>>>>>>> 330af8665a8b336209bb6982de5a0421e7099edf
          )}

          {download && (
            <div className="action-row">
              <a className="btn btn-primary" href={download.url} download={download.filename}>
<<<<<<< HEAD
                Download logs
=======
                Download diagnostic package
>>>>>>> 330af8665a8b336209bb6982de5a0421e7099edf
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
