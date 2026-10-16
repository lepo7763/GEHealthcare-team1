import '../pages.css';

// [PLACEHOLDER] Tool deployment specifications.
// In production, the Python backend deploys these manifests via kubernetes.client.AppsV1Api and CoreV1Api.
const TOOL_DEPLOY_SPECS = {
  netshoot: {
    name: 'Netshoot Network Toolkit',
    image: 'nicolaka/netshoot:latest',
    imageType: 'Approved Specialized Exception',
    podPrefix: 'diag-netshoot',
    targetNode: 'MiniEdge P360 (192.168.0.3)',
  },
  umf_rti: {
    name: 'UMF RTI Telemetry Monitor',
    image: 'gehc/umf-rti:2.4-ubuntu22',
    imageType: 'Ubuntu 22-based Standard',
    podPrefix: 'diag-umf-rti',
    targetNode: 'Virtual Hub Host (192.168.0.4)',
  },
  tshark: {
    name: 'Wireshark / tshark Packet Sniffer',
    image: 'gehc/wireshark-tshark:4.0-ubuntu22',
    imageType: 'Ubuntu 22-based Standard',
    podPrefix: 'diag-tshark',
    targetNode: 'MiniEdge P360 (192.168.0.3)',
  },
};

const Step3DeployTools = ({
  sessionData,
  onNext,
  onBackToEnvironment,
  onBackToToolSelection,
}) => {
  const selectedToolIds = sessionData.tools || ['netshoot', 'umf_rti', 'tshark'];

  const handleStartDeploy = () => {
    window.alert('Deployment is not available yet.');
  };

  const handleProceed = () => {
    window.alert('Deployment is still in development.');
    onNext();
  };

  return (
    <div className="step-content-pane">
      <div className="card-header" style={{ marginBottom: 'var(--eds-spacing-md)' }}>
        <div>
          <h3 className="card-title">3. Review and Deploy</h3>
          <p className="card-subtitle">
            Review the planned diagnostic deployment and deploy tools to the live environment via the Python backend.
          </p>
        </div>
        <span className="badge badge-purple">Step 3 of 6</span>
      </div>
      <div className="alert alert-warning" role="note">
        <strong>Deployment details (Sample):</strong>
        <span>The tool images, target systems, and deployment summary below are sample data. No tools are deployed to the environment yet.</span>
      </div>

      {/* SUMMARY MANIFEST REVIEW CARD */}
      <div className="card" style={{ marginBottom: 'var(--eds-spacing-md)' }}>
        <div className="card-header">
          <div>
            <h4 className="card-title" style={{ fontSize: '1rem' }}>Deployment Configuration Summary</h4>
            <p className="card-subtitle">Pre-deployment inspection of target environment and resource quotas</p>
          </div>
          <span className="badge badge-purple">{sessionData.context || 'portrait-mobile-prod'}</span>
        </div>

        <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', marginTop: '10px' }}>
          <div>
            <div className="stat-label">Target Host</div>
            <div className="mono-strong">{sessionData.host || '192.168.0.4'}</div>
          </div>
          <div>
            <div className="stat-label">Temporary Workspace</div>
            <div className="mono-strong">Diagnostic tools</div>
          </div>
          <div>
            <div className="stat-label">CPU / Memory Quota</div>
            <div className="mono">{sessionData.cpuLimit || '0.5'} CPU · {sessionData.memoryLimit || '512'} MiB</div>
          </div>
          <div>
            <div className="stat-label">Capture Cap</div>
            <div className="mono">{sessionData.captureDuration || '15'} min · max {sessionData.maxLogSize || '100'} MB</div>
          </div>
        </div>

        <span className="page-eyebrow" style={{ display: 'block', margin: '14px 0 6px' }}>
          Selected Tool Manifests ({selectedToolIds.length})
        </span>

        <ul className="check-list">
          {selectedToolIds.map((toolId) => {
            const spec = TOOL_DEPLOY_SPECS[toolId] || { name: toolId, image: 'unknown', imageType: 'Standard', targetNode: 'MiniEdge' };
            return (
              <li key={toolId} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <span className="mono-strong">{spec.name}</span>
                  <div className="check-detail">
                    Target: {spec.targetNode} · Image: <span className="mono">{spec.image}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span className="badge" style={{ background: '#f3f4f6', color: '#4b5563', fontSize: '0.72rem' }}>
                    {spec.imageType}
                  </span>
                  <span className="badge badge-warning">Not deployed</span>
                </div>
              </li>
            );
          })}
        </ul>
        <div className="action-row" style={{ marginTop: 'var(--eds-spacing-md)' }}>
          <button type="button" className="btn btn-secondary" onClick={onBackToEnvironment}>
            &larr; Back to Environment
          </button>
          <button type="button" className="btn btn-secondary" onClick={onBackToToolSelection}>
            &larr; Back to Tool Selection
          </button>
        </div>
      </div>

      {/* DEPLOYMENT ACTION */}
      <div className="card">
        <h4 className="card-title" style={{ fontSize: '1rem', marginBottom: '4px' }}>
          Deployment
        </h4>
        <p className="card-subtitle">
          The Python backend deployment endpoint is not available yet.
        </p>

        <div className="action-row" style={{ marginTop: '12px' }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleStartDeploy}
          >
            Deploy Tools to Environment
          </button>
        </div>
      </div>

      {/* STEP NAVIGATION ACTIONS */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 'var(--eds-spacing-lg)' }}>
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleProceed}
        >
          Continue to Collect Diagnostics &rarr;
        </button>
      </div>
    </div>
  );
};

export default Step3DeployTools;
