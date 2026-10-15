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
    name: 'Cluster Container Logs',
    format: 'ZIP',
    size: 'Variable',
    status: 'Ready',
    description: 'Full container logs across all Kubernetes namespaces.',
  },
];

const DiagnosticPackages = () => {
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

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
            <h3 id="export-logs-title" className="card-title">Export cluster logs</h3>
            <p className="card-subtitle">
              Download the cluster's container logs as a ZIP archive from the backend.
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
              Collecting logs from cluster. This may take a moment...
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

      <section className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">Available Diagnostic Definitions</h3>
            <p className="card-subtitle">Predefined log bundles and capture definitions</p>
          </div>
        </div>
        <ul className="check-list">
          {PACKAGES.map((pkg) => (
            <li key={pkg.id}>
              <div>
                <div className="check-title">{pkg.name} ({pkg.format})</div>
                <div className="check-detail">{pkg.description}</div>
              </div>
              <span className="badge badge-success">{pkg.status}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
};

export default DiagnosticPackages;