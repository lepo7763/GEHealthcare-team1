import { useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { RUNNING_STATUSES, SERVICE_STATUS_LABEL, STATUS_LABEL } from './constants';
import AnalysisReport from '../logAnalysis/AnalysisReport';
import { analyzeZip } from '../logAnalysis/analyzeZip';

const ServiceProgressCard = ({ service }) => {
  const status = service.status || 'pending';
  const total = Number(service.total) || 0;
  const completed = Number(service.completed) || 0;
  const unit = service.unit || 'items';
  const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  // Pending and skipped services never started: render an empty track so they
  // read as 0% instead of inheriting the fill's full width.
  const notStarted = status === 'pending' || status === 'skipped';
  const isDone = status === 'done';
  const displayPercent = isDone ? 100 : notStarted ? 0 : percent;
  const isIndeterminate = status === 'collecting' && total === 0;
  const showPercent = status === 'pending' || isDone || (total > 0 && status !== 'skipped');

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

// Asks before stopping a run, since cancelling discards unfinished work.
const CancelDialog = ({ onConfirm, onClose, error, isSubmitting }) => (
  <Dialog open onOpenChange={(open) => !open && !isSubmitting && onClose()}>
    <DialogContent>
      <DialogTitle>Cancel this collection?</DialogTitle>
      <DialogDescription>
        Running tools stop at their next safe point and are removed from the cluster.
        Results from services that already finished are kept and packaged for download.
      </DialogDescription>

      {error && (
        <div className="alert alert-error dialog-alert" role="alert">
          <strong>Could not cancel</strong>
          <span>{error}</span>
        </div>
      )}

      <div className="action-row dialog-actions">
        <button type="button" className="btn btn-secondary" onClick={onClose} disabled={isSubmitting}>
          Keep collecting
        </button>
        <button
          type="button"
          className="btn btn-danger"
          onClick={onConfirm}
          disabled={isSubmitting}
          aria-busy={isSubmitting}
        >
          {isSubmitting ? 'Cancelling…' : 'Cancel collection'}
        </button>
      </div>
    </DialogContent>
  </Dialog>
);

const Step4Collect = ({ collect, collectError, download, onCancel, onBack }) => {
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const [cancelError, setCancelError] = useState('');
  const [isSubmittingCancel, setIsSubmittingCancel] = useState(false);

  const confirmCancel = async () => {
    setIsSubmittingCancel(true);
    setCancelError('');
    const error = await onCancel();
    setIsSubmittingCancel(false);
    if (error) {
      setCancelError(error);
    } else {
      setConfirmingCancel(false);
    }
  };

  // Analysis of the zip that was just collected (POST /api/analysis/zip)
  const [report, setReport] = useState(null);
  const [analyzeError, setAnalyzeError] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const analyzeDownload = async () => {
    setIsAnalyzing(true);
    setAnalyzeError('');
    setReport(null);
    try {
      // download.url is a blob: URL for the zip already in the browser, so this doesn't refetch from the cluster
      const blob = await fetch(download.url).then((res) => res.blob());
      setReport(await analyzeZip(blob, download.filename));
    } catch (err) {
      setAnalyzeError(err.message);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const services = collect?.services || [];
  const collectStatus = collect?.status || 'idle';
  const collectFailed =
    collectError || (collectStatus === 'error' ? collect?.message || 'Collection failed.' : '');
  const serviceErrors = services.filter((service) => service.status === 'error').length;
  const totalErrors = services.reduce((sum, service) => sum + (service.errors || 0), 0);
  const allDone = collectStatus === 'done';
  const wasCancelled = collectStatus === 'cancelled';
  const isRunning = RUNNING_STATUSES.includes(collectStatus) && !download;
  const cancelRequested = Boolean(collect?.cancel_requested) && isRunning;
  const keptServices = services.filter((service) => service.status === 'done').length;

  return (
    <>
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

          {!collectFailed && wasCancelled && (
            <div className="alert alert-warning" role="status">
              <strong>Collection cancelled</strong>
              <span>
                {keptServices > 0
                  ? `Results from ${keptServices} finished service${keptServices === 1 ? '' : 's'} were packaged. `
                  : 'No service finished, so the package contains only partial results and the manifest. '}
                Tools started by this collection were stopped and removed from the cluster.
              </span>
            </div>
          )}

          {cancelRequested && (
            <div className="alert alert-warning" role="status">
              <strong>Cancelling…</strong>
              <span>
                Waiting for the current step to stop safely and removing deployed tools. This
                can take a few seconds.
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
                {wasCancelled ? 'Download partial package' : 'Download diagnostic package'}
              </a>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={analyzeDownload}
                disabled={isAnalyzing}
                aria-busy={isAnalyzing}
              >
                {isAnalyzing ? 'Analyzing…' : 'Analyze logs'}
              </button>
            </div>
          )}

          {analyzeError && (
            <div className="alert alert-error" role="alert">
              <strong>Analysis failed</strong>
              <span>{analyzeError}</span>
            </div>
          )}
        </div>

        <div className="action-row">
          <button className="btn btn-secondary" onClick={onBack}>
            Back
          </button>
          {isRunning && (
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => {
                setCancelError('');
                setConfirmingCancel(true);
              }}
              disabled={cancelRequested}
            >
              {cancelRequested ? 'Cancelling…' : 'Cancel collection'}
            </button>
          )}
        </div>
      </div>
    </section>
    {confirmingCancel && (
      <CancelDialog
        onConfirm={confirmCancel}
        onClose={() => setConfirmingCancel(false)}
        error={cancelError}
        isSubmitting={isSubmittingCancel}
      />
    )}
    {report && <AnalysisReport report={report} />}
    </>
  );
};

export default Step4Collect;
