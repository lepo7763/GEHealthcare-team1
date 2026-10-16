import { useState } from 'react';
import { STATUS_LABEL } from './constants';
import AnalysisReport from '../logAnalysis/AnalysisReport';
import { analyzeZip } from '../logAnalysis/analyzeZip';

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

  return (
    <>
    <section className="section-narrow">
      <div className="card">
        <h3 className="card-title">Collect</h3>
        <p className="card-subtitle">
          Collecting logs from the selected services. This can take a while on large clusters.
        </p>

        <div className="collect-panel">
          {collectFailed && (
            <div className="alert alert-error">
              <strong>Collection failed</strong>
              <span>{collectFailed}</span>
            </div>
          )}

          {!collectFailed && collectStatus === 'done' && (
            <div className="alert alert-success">
              <strong>Collection complete</strong>
              <span>
                {containersDone} of {containersTotal} containers collected
                {collectErrors > 0
                  ? ` · ${collectErrors} error${collectErrors === 1 ? '' : 's'}`
                  : ''}
                .
              </span>
            </div>
          )}

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
          )}

          {download && (
            <div className="action-row">
              <a className="btn btn-primary" href={download.url} download={download.filename}>
                Download logs
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
        </div>
      </div>
    </section>
    {report && <AnalysisReport report={report} />}
    </>
  );
};

export default Step4Collect;
