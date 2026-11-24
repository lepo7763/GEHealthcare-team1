import { useState } from 'react';
import { SERVICE_STATUS_LABEL, STATUS_LABEL } from './constants';
import AnalysisReport from '../logAnalysis/AnalysisReport';
import { analyzeZip } from '../logAnalysis/analyzeZip';
import { formatBytes } from './coreDumps';

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

  // Save the package through the browser's "Save as" dialog so the user picks the
  // folder (e.g. a USB drive) every time. Uses the File System Access API
  // (Chrome/Edge, secure context only: https or localhost) and streams the response
  // straight to the chosen file, so large packages never sit in memory.
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [savedTo, setSavedTo] = useState('');

  const canPickLocation = typeof window.showSaveFilePicker === 'function';

  // The plain browser download (default Downloads folder, or the browser's own
  // "ask where to save" dialog if that setting is on). Always the fallback.
  const plainDownload = () => {
    const a = document.createElement('a');
    a.href = download.url;
    a.download = download.filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const saveDownload = async () => {
    setSaveError('');
    setSavedTo('');
    if (!canPickLocation) {
      plainDownload();
      return;
    }

    let handle;
    try {
      handle = await window.showSaveFilePicker({
        suggestedName: download.filename,
        types: [{ description: 'Zip archive', accept: { 'application/zip': ['.zip'] } }],
      });
    } catch (err) {
      if (err.name === 'AbortError') return; // user cancelled the dialog
      // Picker blocked (e.g. permissions policy): don't leave the user with nothing.
      console.warn('Save dialog unavailable, using a normal download.', err);
      plainDownload();
      return;
    }

    setIsSaving(true);
    let writable;
    try {
      const res = await fetch(download.url);
      if (!res.ok || !res.body) throw new Error(`Download failed (${res.status}).`);
      writable = await handle.createWritable();
      // Write chunk by chunk and close explicitly. Chrome writes to a temporary
      // "<name>.crswap" file and only puts the real file in place on close().
      const reader = res.body.getReader();
      let written = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        await writable.write(value);
        written += value.byteLength;
      }
      await writable.close();
      writable = null;

      // Confirm the file really landed with all its bytes.
      const saved = await handle.getFile();
      if (saved.size !== written || (download.sizeBytes && written !== download.sizeBytes)) {
        throw new Error(
          `Saved file is incomplete (${formatBytes(saved.size)} of ${formatBytes(download.sizeBytes || written)}).`,
        );
      }
      setSavedTo(`${handle.name} (${formatBytes(saved.size)})`);
    } catch (err) {
      try {
        await writable?.abort();
      } catch {
        /* already closed/aborted */
      }
      console.error('Saving to the chosen location failed.', err);
      setSaveError(
        `${err.message || 'Saving the package failed.'} Use "Save to Downloads folder" instead.`,
      );
    } finally {
      setIsSaving(false);
    }
  };

  const services = collect?.services || [];
  const collectStatus = collect?.status || 'idle';
  const collectFailed =
    collectError || (collectStatus === 'error' ? collect?.message || 'Collection failed.' : '');
  const serviceErrors = services.filter((service) => service.status === 'error').length;
  const totalErrors = services.reduce((sum, service) => sum + (service.errors || 0), 0);
  const allDone = collectStatus === 'done';

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
              <button
                type="button"
                className="btn btn-primary"
                onClick={saveDownload}
                disabled={isSaving}
                aria-busy={isSaving}
              >
                {isSaving
                  ? 'Saving…'
                  : `Download diagnostic package (${formatBytes(download.sizeBytes)})`}
              </button>
              {canPickLocation && (
                <a className="btn btn-secondary" href={download.url} download={download.filename}>
                  Save to Downloads folder
                </a>
              )}
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

          {savedTo && (
            <div className="alert alert-success" role="status">
              <strong>Package saved</strong>
              <span>Saved as {savedTo}.</span>
            </div>
          )}

          {saveError && (
            <div className="alert alert-error" role="alert">
              <strong>Save failed</strong>
              <span>{saveError}</span>
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
        </div>
      </div>
    </section>
    {report && <AnalysisReport report={report} />}
    </>
  );
};

export default Step4Collect;
