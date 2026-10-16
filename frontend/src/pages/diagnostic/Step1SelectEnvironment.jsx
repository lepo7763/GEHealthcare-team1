import { useState } from 'react';
import '../pages.css';

// [PLACEHOLDER] Initial saved environments list.
// In production, this would be fetched from the backend or persistent encrypted local storage.
const SAVED_ENVIRONMENTS = [
  {
    id: 'env-portrait-central',
    name: 'Env1',
    host: '192.168.0.4',
    port: '22',
    account: 'diagnostic-ops',
    context: 'portrait-mobile-prod',
    devicesCount: 5,
    tag: 'Default Lab',
    systemInfo: {
      platformVersion: '3.4.2',
      k8sVersion: 'v1.28.3+k3s1',
      os: 'Ubuntu 22.04 LTS (Jammy)',
      kernel: '5.15.0-89-generic',
    },
  },
  {
    id: 'env-icu-pod-3',
    name: 'Env2',
    host: '10.120.44.10',
    port: '22',
    account: 'field-service',
    context: 'icu-cluster-primary',
    devicesCount: 8,
    tag: 'Clinical Live',
    systemInfo: {
      platformVersion: '3.4.0',
      k8sVersion: 'v1.28.2+k3s1',
      os: 'Ubuntu 22.04 LTS',
      kernel: '5.15.0-88-generic',
    },
  },
  {
    id: 'env-stjude-mobile',
    name: 'Env3',
    host: '172.16.8.2',
    port: '2222',
    account: 'ge-specialist',
    context: 'mobile-k3s-edge',
    devicesCount: 3,
    tag: 'Staging',
    systemInfo: {
      platformVersion: '3.3.9',
      k8sVersion: 'v1.27.5+k3s1',
      os: 'Ubuntu 22.04 LTS',
      kernel: '5.15.0-84-generic',
    },
  },
];

const Step1SelectEnvironment = ({ sessionData, updateSessionData, onNext }) => {
  const [savedEnvs] = useState(SAVED_ENVIRONMENTS);
  const [selectedEnvId, setSelectedEnvId] = useState(sessionData.envId || 'env-portrait-central');
  const [isCustom, setIsCustom] = useState(sessionData.envId === 'custom');

  // Form Fields
  const [host, setHost] = useState(sessionData.host || '192.168.0.4');
  const [port, setPort] = useState(sessionData.port || '22');
  const [account, setAccount] = useState(sessionData.account || 'diagnostic-ops');
  const [secret, setSecret] = useState(sessionData.secret || '');
  const [showSecret, setShowSecret] = useState(false);
  const [context, setContext] = useState(sessionData.context || 'portrait-mobile-prod');

  // Field Validation Errors
  const [errors, setErrors] = useState({});

  // Validate form inputs
  const validateInputs = () => {
    const newErrors = {};
    if (!host.trim()) {
      newErrors.host = 'IP address or hostname is required.';
    } else {
      // Basic IP or hostname regex
      const ipOrHostRegex = /^([a-zA-Z0-9-.]+)|(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$/;
      if (!ipOrHostRegex.test(host.trim())) {
        newErrors.host = 'Please enter a valid IP address or domain hostname.';
      }
    }

    const portNum = parseInt(port, 10);
    if (!port || isNaN(portNum) || portNum < 1 || portNum > 65535) {
      newErrors.port = 'Port must be between 1 and 65535.';
    }

    if (!account.trim()) {
      newErrors.account = 'Service account or username is required.';
    }

    if (!context.trim()) {
      newErrors.context = 'Environment context is required.';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSelectSaved = (env) => {
    setSelectedEnvId(env.id);
    setIsCustom(false);
    setHost(env.host);
    setPort(env.port);
    setAccount(env.account);
    setContext(env.context);
    setErrors({});
  };

  const handleCustomMode = () => {
    setIsCustom(true);
    setSelectedEnvId('custom');
    setHost('');
    setPort('22');
    setAccount('');
    setSecret('');
    setContext('');
    setErrors({});
  };

  const handleTestConnection = () => {
    window.alert('Connection testing is not available yet.');
  };

  const handleProceed = () => {
    if (!validateInputs()) {
      return;
    }
    updateSessionData({
      envId: selectedEnvId,
      host,
      port,
      account,
      context,
      connectionVerified: false,
    });
    onNext();
  };

  return (
    <div className="step-content-pane">
      <div className="card-header" style={{ marginBottom: 'var(--eds-spacing-md)' }}>
        <div>
          <h3 className="card-title">1. Select Environment and Connect</h3>
          <p className="card-subtitle">
            Choose a saved Portrait Mobile environment or enter target connection information. Authenticate and test reachability.
          </p>
        </div>
        <span className="badge badge-purple">Step 1 of 6</span>
      </div>

      {/* SAVED PORTRAIT MOBILE ENVIRONMENTS */}
      <div style={{ marginBottom: 'var(--eds-spacing-lg)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <span className="page-eyebrow">Saved Portrait Mobile Environments (Sample)</span>
          <span className="check-detail">{savedEnvs.length} profiles configured</span>
        </div>

        <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
          {savedEnvs.map((env) => {
            const isChosen = selectedEnvId === env.id && !isCustom;
            return (
              <div
                key={env.id}
                className={`card stat-card ${isChosen ? 'card-tinted' : ''}`}
                style={{
                  cursor: 'pointer',
                  border: isChosen ? '2px solid var(--eds-color-purple)' : '1px solid var(--eds-color-gray-100)',
                  transition: 'all 0.15s ease',
                }}
                onClick={() => handleSelectSaved(env)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && handleSelectSaved(env)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="badge badge-purple">{env.tag}</span>
                  {isChosen && <span className="status-dot" title="Active selection" />}
                </div>
                <div className="stat-value" style={{ fontSize: '1.05rem', marginTop: '6px' }}>
                  {env.name}
                </div>
                <div className="mono" style={{ fontSize: '0.8rem' }}>
                  {env.host}:{env.port}
                </div>
                <div className="stat-label" style={{ marginTop: '4px' }}>
                  {env.devicesCount} devices · {env.context}
                </div>
              </div>
            );
          })}

          <div
            className={`card stat-card ${isCustom ? 'card-tinted' : ''}`}
            style={{
              cursor: 'pointer',
              border: isCustom ? '2px solid var(--eds-color-purple)' : '1px dashed var(--eds-color-gray-300)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
              minHeight: '110px',
            }}
            onClick={handleCustomMode}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && handleCustomMode()}
          >
            <div style={{ fontWeight: 'var(--eds-font-weight-semibold)', color: 'var(--eds-color-purple)' }}>
              + Manual Connection
            </div>
            <div className="check-detail">Enter IP and credentials</div>
          </div>
        </div>
      </div>

      {/* CONNECTION PARAMETERS & CREDENTIALS CARD */}
      <div className="card">
        <div className="card-header">
          <div>
            <h4 className="card-title" style={{ fontSize: '1rem' }}>
              Connection Parameters &amp; Authorized Credentials
            </h4>
            <p className="card-subtitle">
              Authorized credentials are used to discover system settings and provision ephemeral diagnostic tools.
            </p>
          </div>
        </div>
        <div className="alert alert-warning" role="note">
          <strong>Connection test (Sample):</strong>
          <span>Connection testing and secure profile persistence are not available yet.</span>
        </div>

        <div className="form-row">
          <label className="field grow">
            <span>Target IP Address or Hostname *</span>
            <input
              type="text"
              className={errors.host ? 'error' : ''}
              value={host}
              onChange={(e) => {
                setHost(e.target.value);
                setErrors({ ...errors, host: null });
              }}
              placeholder="e.g. 192.168.0.4"
            />
            {errors.host && <span className="field-error">{errors.host}</span>}
            <small>Portrait Mobile Hub host or MiniEdge static IP</small>
          </label>

          <label className="field port">
            <span>SSH / Mgmt Port *</span>
            <input
              type="text"
              className={errors.port ? 'error' : ''}
              value={port}
              onChange={(e) => {
                setPort(e.target.value);
                setErrors({ ...errors, port: null });
              }}
              placeholder="22"
            />
            {errors.port && <span className="field-error">{errors.port}</span>}
            <small>Standard: 22</small>
          </label>
        </div>

        <div className="form-row">
          <label className="field grow">
            <span>Service Account / Username *</span>
            <input
              type="text"
              className={errors.account ? 'error' : ''}
              value={account}
              onChange={(e) => {
                setAccount(e.target.value);
                setErrors({ ...errors, account: null });
              }}
              placeholder="diagnostic-ops"
            />
            {errors.account && <span className="field-error">{errors.account}</span>}
          </label>

          <label className="field grow">
            <span>Authorized Secret / SSH Key</span>
            <div className="input-with-action">
              <input
                type={showSecret ? 'text' : 'password'}
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder="Token, password, or key passphrase"
              />
              <button type="button" onClick={() => setShowSecret(!showSecret)}>
                {showSecret ? 'Hide' : 'Show'}
              </button>
            </div>
            <small>Held in memory during session only; never logged</small>
          </label>
        </div>

        <label className="field">
          <span>Environment Context *</span>
          <input
            type="text"
            className={errors.context ? 'error' : ''}
            value={context}
            onChange={(e) => {
              setContext(e.target.value);
              setErrors({ ...errors, context: null });
            }}
            placeholder="e.g. portrait-mobile-prod"
          />
          {errors.context && <span className="field-error">{errors.context}</span>}
          <small>Context name from the system connection configuration</small>
        </label>

        <div className="alert alert-warning" role="note" style={{ marginTop: 'var(--eds-spacing-md)' }}>
          <strong>Secure environment saving (Sample):</strong>
          <span>Saved profiles are sample data and new connection details are not persisted.</span>
        </div>

        {/* CONNECTION TEST ACTION */}
        <div className="action-row" style={{ marginTop: 'var(--eds-spacing-md)' }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleTestConnection}
          >
            Test Connection
          </button>
        </div>
      </div>

      {/* STEP NAVIGATION ACTIONS */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--eds-spacing-lg)' }}>
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleProceed}
        >
          Continue to Discover &amp; Configure &rarr;
        </button>
      </div>
    </div>
  );
};

export default Step1SelectEnvironment;
