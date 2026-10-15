import { useState } from 'react';
import './pages.css';

const Sessions = () => {
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState('');

  const exportLogs = async () => {
    setIsExporting(true);
    setError('');

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
      link.download = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]
        || 'k8s_cluster_logs.zip';
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
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
      <h2 className="page-title">Sessions</h2>
      <section className="card" aria-labelledby="export-logs-title">
        <h3 id="export-logs-title" className="card-title">Export cluster logs</h3>
        <p className="card-subtitle">
          Download the cluster's container logs as a ZIP file.
        </p>
        <button
          type="button"
          className="btn btn-primary"
          onClick={exportLogs}
          disabled={isExporting}
          aria-busy={isExporting}
        >
          {isExporting ? 'Exporting...' : 'Export logs ZIP'}
        </button>
        {isExporting && <p role="status">Collecting logs. This may take a moment.</p>}
        {error && <p className="alert alert-warning" role="alert">{error}</p>}
      </section>
    </div>
  );
};

export default Sessions;
