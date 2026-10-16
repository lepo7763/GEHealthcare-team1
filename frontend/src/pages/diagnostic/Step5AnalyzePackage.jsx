import '../pages.css';

const Step5AnalyzePackage = ({ sessionData, onNext, onBack }) => {
  const packageMeta = sessionData.packageMeta || {
    id: 'PKG-20261015-094722',
    filename: 'k8s_cluster_logs_20261015_094722.zip',
    size: `${sessionData.collectedBytesMB || 18.4} MB`,
    totalContainers: 5,
    totalPackets: sessionData.packetCount || 12450,
    phiStatus: 'Scrubbed & Compliant (0 identifiers detected)',
    format: 'ZIP + JSON Manifest',
  };

  const handleGeneratePackage = () => {
    window.alert('Package generation is not available yet.');
  };

  const handleProceed = () => {
    window.alert('Package review is still in development.');
    onNext();
  };

  return (
    <div className="step-content-pane">
      <div className="card-header" style={{ marginBottom: 'var(--eds-spacing-md)' }}>
        <div>
          <h3 className="card-title">5. Analyze &amp; Package</h3>
          <p className="card-subtitle">
            Aggregate raw logs and packet captures, apply PHI/PII anonymization, and compile a standardized diagnostic archive.
          </p>
        </div>
        <span className="badge badge-purple">Step 5 of 6</span>
      </div>
      <div className="alert alert-warning" role="note">
        <strong>Analysis and package results (Sample):</strong>
        <span>The processing checks, package metadata, and privacy claims below are sample content. No package is generated yet.</span>
      </div>

      <div className="two-col">
        {/* PIPELINE PROCESSING CHECKLIST */}
        <div className="card">
          <h4 className="card-title" style={{ fontSize: '1rem', marginBottom: '8px' }}>
            Data Processing Pipeline
          </h4>
          <p className="card-subtitle">Automated validation checks executed before bundle compression</p>

          <ul className="check-list" style={{ marginTop: '12px' }}>
            <li>
              <div>
                <div className="check-title">Log Normalization</div>
                <div className="check-detail">Aggregated logs across system and application service groups.</div>
              </div>
              <span className="badge badge-success">Passed</span>
            </li>
            <li>
              <div>
                <div className="check-title">PHI / PII Redaction Filter</div>
                <div className="check-detail">Scanned outputs for medical record numbers, patient names, and addresses.</div>
              </div>
              <span className="badge badge-success">Compliant</span>
            </li>
            <li>
              <div>
                <div className="check-title">Clock Skew Correlation</div>
                <div className="check-detail">Virtual Hub Self (+2.8s offset) timestamp indexed with workstation clock.</div>
              </div>
              <span className="badge badge-warning">Adjusted</span>
            </li>
            <li>
              <div>
                <div className="check-title">Standardized Manifest Generation</div>
                <div className="check-detail">Generating root manifest.json with environment metadata and tool versions.</div>
              </div>
              <span className="badge badge-success">Valid</span>
            </li>
          </ul>

          <div style={{ marginTop: 'var(--eds-spacing-lg)' }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleGeneratePackage}
            >
              Generate Diagnostic Package
            </button>
          </div>
        </div>

        {/* PACKAGE ARTIFACT DETAILS */}
        <aside className="card card-tinted">
          <div className="card-header">
            <div>
              <h4 className="card-title" style={{ fontSize: '1rem' }}>Package Summary</h4>
                <p className="card-subtitle">Sample artifact details</p>
            </div>
            <span className="badge badge-warning">Placeholder</span>
          </div>

          <dl className="summary-list" style={{ marginTop: '10px' }}>
            <div>
              <dt>Package ID</dt>
              <dd className="mono">{packageMeta.id}</dd>
            </div>
            <div>
              <dt>Format</dt>
              <dd>{packageMeta.format}</dd>
            </div>
            <div>
              <dt>Archive Size</dt>
              <dd>{packageMeta.size}</dd>
            </div>
            <div>
              <dt>Container Streams</dt>
              <dd>{packageMeta.totalContainers} service containers</dd>
            </div>
            <div>
              <dt>Captured Packets</dt>
              <dd>{packageMeta.totalPackets.toLocaleString()} frames</dd>
            </div>
            <div>
              <dt>HIPAA / Privacy</dt>
              <dd style={{ color: 'var(--eds-color-success)' }}>Zero PHI exposed</dd>
            </div>
          </dl>

        </aside>
      </div>

      {/* STEP NAVIGATION ACTIONS */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 'var(--eds-spacing-lg)' }}>
        <button type="button" className="btn btn-secondary" onClick={onBack}>
          &larr; Back to Collect Diagnostics
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleProceed}
        >
          Continue to Review &amp; Cleanup &rarr;
        </button>
      </div>
    </div>
  );
};

export default Step5AnalyzePackage;
