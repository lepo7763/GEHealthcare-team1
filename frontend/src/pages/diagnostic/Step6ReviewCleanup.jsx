import { useState } from 'react';
import '../pages.css';

const Step6ReviewCleanup = ({ sessionData, onRestart, onNavigateOverview }) => {
  const [isExporting, setIsExporting] = useState(false);
  const [downloadSuccess, setDownloadSuccess] = useState('');
  const [downloadError, setDownloadError] = useState('');

  const packageMeta = sessionData.packageMeta || {
    id: 'DEMO-SESSION',
  };

  const handleDownload = async () => {
    setIsExporting(true);
    setDownloadError('');
    setDownloadSuccess('');

    try {
      const response = await fetch('/api/logs/demo.zip');

      if (!response.ok) {
        const details = await response.json().catch(() => ({}));
        throw new Error(details.detail || 'Could not download the simulated logs ZIP.');
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const filename = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]
        || 'demo_diagnostic_logs.zip';
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setDownloadSuccess(`Simulated logs ZIP downloaded: ${filename}.`);
    } catch (error) {
      setDownloadError(error instanceof TypeError
        ? 'Could not reach the backend to create the simulated logs ZIP. Make sure it is running and try again.'
        : error.message);
    } finally {
      setIsExporting(false);
    }
  };

  const handleCleanup = () => {
    window.alert('Resource cleanup is not available yet.');
  };

  return (
    <div className="step-content-pane">
      <div className="card-header" style={{ marginBottom: 'var(--eds-spacing-md)' }}>
        <div>
          <h3 className="card-title">6. Review &amp; Cleanup</h3>
          <p className="card-subtitle">
            Download collected system logs and review sample findings. Resource cleanup is not available yet.
          </p>
        </div>
        <span className="badge badge-warning">Step 6 of 6</span>
      </div>
      <div className="alert alert-warning" role="note">
        <strong>Package and cleanup details (Sample):</strong>
        <span>The downloadable ZIP contains simulated logs and sample diagnostics, not live system results.</span>
      </div>
      <div className="alert alert-warning" role="note">
        <strong>Download location:</strong>
        <span>
          Files are saved to your browser&apos;s default Downloads folder. To change the folder,
          update your browser&apos;s download settings; this app cannot set a local folder directly.
        </span>
      </div>

      <div className="two-col">
        {/* DOWNLOAD PACKAGE CARD */}
        <div className="card">
          <div className="card-header">
            <div>
              <h4 className="card-title" style={{ fontSize: '1.1rem' }}>Download Diagnostic Package</h4>
              <p className="card-subtitle">Download a ZIP archive with sample logs and diagnostic text files.</p>
            </div>
            <span className="badge badge-purple">{packageMeta.id}</span>
          </div>

          <div style={{ marginTop: 'var(--eds-spacing-md)' }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleDownload}
              disabled={isExporting}
              aria-busy={isExporting}
              style={{ fontSize: 'var(--eds-font-size-md)', padding: '0 24px', height: '46px' }}
            >
              {isExporting ? 'Preparing ZIP...' : 'Download Mock Logs ZIP'}
            </button>
          </div>

          {downloadSuccess && (
            <div className="alert alert-success" style={{ marginTop: '14px', marginBottom: 0 }}>
              <strong>Download Started:</strong>
              <span>{downloadSuccess}</span>
            </div>
          )}

          {downloadError && (
            <div className="alert alert-warning" style={{ marginTop: '14px', marginBottom: 0 }}>
              <strong>Notice:</strong>
              <span>{downloadError}</span>
            </div>
          )}

          <div style={{ borderTop: '1px solid var(--eds-color-gray-100)', marginTop: 'var(--eds-spacing-lg)', paddingTop: 'var(--eds-spacing-md)' }}>
            <span className="page-eyebrow">Session Findings (Sample)</span>
            <ul className="check-list" style={{ marginTop: '8px' }}>
              <li>
                <div>
                  <div className="check-title">System Health &amp; Service Availability</div>
                  <div className="check-detail">All 18 core services operating normally with zero container restarts.</div>
                </div>
                <span className="badge badge-success">Nominal</span>
              </li>
              <li>
                <div>
                  <div className="check-title">Clock Variance Advisory</div>
                  <div className="check-detail">Virtual Hub Self recorded +2.8s clock drift. Review NTP synchronization.</div>
                </div>
                <span className="badge badge-warning">Advisory</span>
              </li>
            </ul>
          </div>
        </div>

        {/* ENVIRONMENT TEARDOWN & CLEANUP */}
        <aside className="card card-tinted">
          <div className="card-header">
            <div>
              <h4 className="card-title" style={{ fontSize: '1rem' }}>Resource Teardown</h4>
              <p className="card-subtitle">Requirement: Leave customer environment in pristine state</p>
            </div>
            <span className="badge badge-warning">Not available</span>
          </div>

          <p className="card-subtitle" style={{ marginTop: '8px' }}>
            Resource cleanup (Sample). No resources are removed by this action yet.
          </p>

          <div style={{ marginTop: '12px' }}>
            <button
              type="button"
              className="btn btn-secondary btn-block"
              onClick={handleCleanup}
            >
              Clean Up Deployed Resources
            </button>
          </div>
        </aside>
      </div>

      {/* FINALIZE AND RETURN BUTTONS */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'var(--eds-spacing-xl)' }}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onRestart}
        >
          Start New Diagnostic Session
        </button>

        <button
          type="button"
          className="btn btn-primary"
          onClick={onNavigateOverview}
        >
          Return to Operations Overview &rarr;
        </button>
      </div>
    </div>
  );
};

export default Step6ReviewCleanup;
