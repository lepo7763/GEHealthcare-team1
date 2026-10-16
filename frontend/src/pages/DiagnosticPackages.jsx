import { useState } from 'react';
import './pages.css';

// # GEHealthcare-team1
// The color requirements:
// - "Compassion Purple" (Pantone 267 C, RGB 96/34/166, CMYK 81/99/0/0)
// - "White" (RGB 255/255/255, CMYK 0/0/0/0)
// - "Cool Gray" (Pantone Cool Gray 1 C, RGB 228/228/228, CMYK 0/0/0/10)
// Font requirement: "Inter" system-ui, Avenir, Helvetica, Arial, sans-serif

const PACKAGES = [
  {
    id: 'PKG-20261015-01',
    name: 'Portrait Mobile Diagnostics',
    format: 'ZIP',
    size: '2.4 MB',
    status: 'Ready',
    description: 'System logs, network summary, configuration snapshot, and health metrics.',
    createdAt: '2026-10-15T19:42:00Z',
    environment: {
      name: 'Env1',
      host: '192.168.0.4',
      context: 'portrait-mobile-prod',
      platformVersion: '3.4.2',
      systemVersion: 'Ubuntu 22.04 LTS',
    },
    artifacts: [
      {
        id: 'system-log',
        name: 'system.log',
        type: 'System log',
        collectedAt: '2026-10-15T19:34:12Z',
        size: '84 KB',
        preview: '[DEMO] 19:34:12 INFO System services initialized.\n[DEMO] 19:35:03 INFO Resource checks completed successfully.',
      },
      {
        id: 'application-log',
        name: 'application.log',
        type: 'Application log',
        collectedAt: '2026-10-15T19:35:45Z',
        size: '126 KB',
        preview: '[DEMO] 19:35:45 INFO Application service is responding.\n[DEMO] 19:36:10 WARN Example warning for interface demonstration.',
      },
      {
        id: 'network-summary',
        name: 'network-summary.txt',
        type: 'Network summary',
        collectedAt: '2026-10-15T19:37:00Z',
        size: '18 KB',
        preview: '[DEMO] Network summary only. No live packet capture is included.',
      },
      {
        id: 'configuration',
        name: 'configuration-snapshot.txt',
        type: 'Configuration snapshot',
        collectedAt: '2026-10-15T19:38:00Z',
        size: '12 KB',
        preview: '[DEMO] Configuration snapshot only. No live system configuration is included.',
      },
      {
        id: 'health-metrics',
        name: 'health-metrics.txt',
        type: 'Health metrics',
        collectedAt: '2026-10-15T19:40:00Z',
        size: '9 KB',
        preview: '[DEMO] Health metrics summary. No live metrics are included.',
      },
    ],
  },
  {
    id: 'PKG-20261014-02',
    name: 'Service Log Review',
    format: 'ZIP',
    size: '1.1 MB',
    status: 'Ready',
    description: 'Sample service and application log collection.',
    createdAt: '2026-10-14T16:18:00Z',
    environment: {
      name: 'Env2',
      host: '10.120.44.10',
      context: 'icu-cluster-primary',
      platformVersion: '3.4.0',
      systemVersion: 'Ubuntu 22.04 LTS',
    },
    artifacts: [
      {
        id: 'service-log',
        name: 'service.log',
        type: 'Service log',
        collectedAt: '2026-10-14T16:10:20Z',
        size: '96 KB',
        preview: '[DEMO] 16:10:20 INFO Service started.\n[DEMO] 16:11:05 INFO Health check passed.',
      },
      {
        id: 'application-log',
        name: 'application.log',
        type: 'Application log',
        collectedAt: '2026-10-14T16:12:00Z',
        size: '210 KB',
        preview: '[DEMO] Example application log. No live data is included.',
      },
    ],
  },
];

const DiagnosticPackages = () => {
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [selectedPackageId, setSelectedPackageId] = useState(PACKAGES[0].id);
  const [selectedArtifactId, setSelectedArtifactId] = useState(PACKAGES[0].artifacts[0].id);
  const [isPackageDownloading, setIsPackageDownloading] = useState(false);
  const [packageDownloadError, setPackageDownloadError] = useState('');
  const [packageDownloadSuccess, setPackageDownloadSuccess] = useState('');

  const selectedPackage = PACKAGES.find((pkg) => pkg.id === selectedPackageId) || PACKAGES[0];
  const selectedArtifact = selectedPackage.artifacts.find(
    (artifact) => artifact.id === selectedArtifactId
  ) || selectedPackage.artifacts[0];

  const exportLogs = async () => {
    setIsExporting(true);
    setError('');
    setSuccess('');

    try {
      const response = await fetch('/api/logs/zip');

      if (!response.ok) {
        const details = await response.json().catch(() => ({}));
        throw new Error(details.detail || 'Could not export logs. Check that the backend is running.');
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const filename = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]
        || 'k8s_cluster_logs.zip';
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setSuccess(`Export completed: ${filename} downloaded.`);
    } catch (error) {
      setError(error instanceof TypeError
        ? 'Could not reach the backend. Make sure it is running and try again.'
        : error.message);
    } finally {
      setIsExporting(false);
    }
  };

  const selectPackage = (pkg) => {
    setSelectedPackageId(pkg.id);
    setSelectedArtifactId(pkg.artifacts[0].id);
    setPackageDownloadError('');
    setPackageDownloadSuccess('');
  };

  const downloadPackage = async () => {
    setIsPackageDownloading(true);
    setPackageDownloadError('');
    setPackageDownloadSuccess('');

    try {
      const response = await fetch('/api/logs/demo.zip');
      if (!response.ok) {
        const details = await response.json().catch(() => ({}));
        throw new Error(details.detail || 'Could not download the package.');
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const filename = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]
        || `${selectedPackage.id.toLowerCase()}-diagnostic-package.zip`;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setPackageDownloadSuccess(`Downloaded ${filename}. This archive contains simulated package data.`);
    } catch (downloadError) {
      setPackageDownloadError(downloadError instanceof TypeError
        ? 'Could not reach the backend. Make sure it is running and try again.'
        : downloadError.message);
    } finally {
      setIsPackageDownloading(false);
    }
  };

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <span className="page-eyebrow">Diagnostic Artifacts</span>
          <h2 className="page-title">Diagnostic Packages</h2>
          <p className="page-subtitle">
            Generate, export, and download comprehensive diagnostic bundles and container logs.
          </p>
        </div>
      </section>

      <section className="card" aria-labelledby="export-logs-title">
        <div className="card-header">
          <div>
            <h3 id="export-logs-title" className="card-title">Export system logs</h3>
            <p className="card-subtitle">
              Download the environment's container logs as a ZIP archive from the backend.
            </p>
          </div>
          <span className="badge badge-purple">ZIP Archive</span>
        </div>

        <div className="action-row" style={{ marginTop: 'var(--eds-spacing-md)' }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={exportLogs}
            disabled={isExporting}
            aria-busy={isExporting}
          >
            {isExporting ? 'Exporting...' : 'Export logs ZIP'}
          </button>
          {isExporting && (
            <span className="mono" role="status" style={{ marginLeft: 'var(--eds-spacing-sm)' }}>
              Collecting system logs. This may take a moment...
            </span>
          )}
        </div>

        {success && (
          <div className="alert alert-success" role="alert">
            <strong>Success</strong>
            <span>{success}</span>
          </div>
        )}

        {error && (
          <div className="alert alert-warning" role="alert">
            <strong>Export Warning</strong>
            <span>{error}</span>
          </div>
        )}
      </section>

      <div className="alert alert-warning" role="note">
        <strong>Sample package history:</strong>
        <span>Package records and artifact previews below are demonstration data, not saved results from live diagnostic sessions.</span>
      </div>

      <section className="two-col" aria-label="Diagnostic package history and details">
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Previously Generated Packages</h3>
              <p className="card-subtitle">Select a package to inspect its details and artifacts.</p>
            </div>
            <span className="badge badge-purple">{PACKAGES.length} packages</span>
          </div>
          <ul className="check-list">
            {PACKAGES.map((pkg) => (
              <li key={pkg.id} style={{ alignItems: 'flex-start', borderTop: '1px solid var(--eds-color-gray-100)', padding: '12px 0' }}>
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => selectPackage(pkg)}
                  aria-pressed={selectedPackage.id === pkg.id}
                  style={{ textAlign: 'left', whiteSpace: 'normal' }}
                >
                  <span className="check-title">{pkg.name}</span>
                  <span className="check-detail" style={{ display: 'block' }}>{pkg.id} · {pkg.format} · {pkg.size}</span>
                  <span className="check-detail" style={{ display: 'block' }}>{new Date(pkg.createdAt).toLocaleString()}</span>
                </button>
                <span className="badge badge-warning">Sample</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Package Details</h3>
              <p className="card-subtitle">{selectedPackage.description}</p>
            </div>
            <span className="badge badge-purple">{selectedPackage.id}</span>
          </div>

          <dl className="summary-list">
            <div><dt>Environment</dt><dd>{selectedPackage.environment.name}</dd></div>
            <div><dt>Host</dt><dd className="mono">{selectedPackage.environment.host}</dd></div>
            <div><dt>Context</dt><dd>{selectedPackage.environment.context}</dd></div>
            <div><dt>Platform version</dt><dd>{selectedPackage.environment.platformVersion}</dd></div>
            <div><dt>System version</dt><dd>{selectedPackage.environment.systemVersion}</dd></div>
            <div><dt>Generated</dt><dd>{new Date(selectedPackage.createdAt).toLocaleString()}</dd></div>
            <div><dt>Artifacts</dt><dd>{selectedPackage.artifacts.length}</dd></div>
          </dl>

          <div className="action-row" style={{ marginBottom: 'var(--eds-spacing-md)' }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={downloadPackage}
              disabled={isPackageDownloading}
              aria-busy={isPackageDownloading}
            >
              {isPackageDownloading ? 'Preparing package...' : 'Download Complete Package'}
            </button>
          </div>

          {packageDownloadSuccess && (
            <div className="alert alert-success" role="status">
              <strong>Download Started</strong>
              <span>{packageDownloadSuccess}</span>
            </div>
          )}
          {packageDownloadError && (
            <div className="alert alert-warning" role="alert">
              <strong>Download Error</strong>
              <span>{packageDownloadError}</span>
            </div>
          )}

          <h4 className="card-title" style={{ fontSize: '1rem', marginTop: 'var(--eds-spacing-md)' }}>
            Analysis Artifacts &amp; Logs
          </h4>
          <ul className="check-list">
            {selectedPackage.artifacts.map((artifact) => (
              <li key={artifact.id} style={{ borderTop: '1px solid var(--eds-color-gray-100)', padding: '8px 0' }}>
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => setSelectedArtifactId(artifact.id)}
                  aria-pressed={selectedArtifact.id === artifact.id}
                  style={{ textAlign: 'left', whiteSpace: 'normal' }}
                >
                  <span className="check-title">{artifact.name}</span>
                  <span className="check-detail" style={{ display: 'block' }}>
                    {artifact.type} · {artifact.size} · {new Date(artifact.collectedAt).toLocaleString()}
                  </span>
                </button>
                <span className={`badge ${selectedArtifact.id === artifact.id ? 'badge-purple' : 'badge-warning'}`}>
                  {selectedArtifact.id === artifact.id ? 'Selected' : 'Sample'}
                </span>
              </li>
            ))}
          </ul>
          <div className="card card-tinted" style={{ marginTop: 'var(--eds-spacing-md)' }}>
            <div className="check-title">{selectedArtifact.name}</div>
            <div className="check-detail">{selectedArtifact.type} · Collected {new Date(selectedArtifact.collectedAt).toLocaleString()}</div>
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 'var(--eds-font-size-xs)', marginBottom: 0 }}>
              {selectedArtifact.preview}
            </pre>
          </div>
        </div>
      </section>
    </div>
  );
};

export default DiagnosticPackages;