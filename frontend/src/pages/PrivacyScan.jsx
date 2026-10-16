import { useState } from 'react';
import './pages.css';

import ZipUpload from './logAnalysis/ZipUpload';
import { scanZipForPrivacy } from './logAnalysis/analyzeZip';

// Shows where a log package may contain PHI/PII before it is sent to engineering.
// The backend only returns masked values, so this page never displays the real data.
const PrivacyScan = () => {
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState('');
  const [report, setReport] = useState(null);

  const runScan = async (file) => {
    setIsScanning(true);
    setError('');
    setReport(null);
    try {
      setReport(await scanZipForPrivacy(file, file.name));
    } catch (err) {
      setError(err.message);
    } finally {
      setIsScanning(false);
    }
  };

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <span className="page-eyebrow">Diagnostic Artifacts</span>
          <h2 className="page-title">Privacy Scan</h2>
          <p className="page-subtitle">
            Check a log package for patient or personal data (PHI/PII) before sharing it.
          </p>
        </div>
      </section>

      <section className="card" aria-labelledby="privacy-upload-title">
        <h3 id="privacy-upload-title" className="card-title">Log package</h3>
        <p className="card-subtitle">Values are masked in the results; the scan never shows the raw data.</p>

        <ZipUpload
          buttonLabel="Scan"
          busyLabel="Scanning…"
          isBusy={isScanning}
          onSubmit={runScan}
          onFileChange={() => { setError(''); setReport(null); }}
        />

        {error && (
          <div className="alert alert-error" role="alert" style={{ marginTop: 'var(--eds-spacing-md)' }}>
            <strong>Scan failed</strong>
            <span>{error}</span>
          </div>
        )}
      </section>

      {report && (
        <>
          {report.total_findings === 0 ? (
            <div className="alert alert-success" role="status">
              <strong>No PHI/PII patterns found</strong>
              <span>
                Scanned {report.files_scanned} log files. This checks common patterns only, so
                still review the package before sharing it outside the hospital.
              </span>
            </div>
          ) : (
            <div className="alert alert-warning" role="status">
              <strong>
                {report.total_findings} possible PHI/PII finding{report.total_findings === 1 ? '' : 's'}
              </strong>
              <span>
                In {report.files_scanned} log files. Review these containers before sharing the package.
              </span>
            </div>
          )}

          {report.categories.length > 0 && (
            <section className="card" aria-labelledby="privacy-results-title">
              <h3 id="privacy-results-title" className="card-title">Findings by type</h3>
              <div className="analysis-table-wrap">
                <table className="analysis-table">
                  <thead>
                    <tr><th>Type</th><th>Count</th><th>Containers</th><th>Examples (masked)</th></tr>
                  </thead>
                  <tbody>
                    {report.categories.map((c) => (
                      <tr key={c.category}>
                        <td><span className="badge badge-warning">{c.label}</span></td>
                        <td className="analysis-num">{c.count}</td>
                        <td>{c.containers.map((name) => <div key={name}>{name}</div>)}</td>
                        <td>
                          {c.examples.map((ex) => (
                            <div key={`${ex.container}-${ex.line_number}-${ex.masked}`}>
                              <code className="mono">{ex.masked}</code>{' '}
                              <span className="check-detail">line {ex.line_number}</span>
                            </div>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
};

export default PrivacyScan;
