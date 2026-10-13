import { useState } from 'react';
import './pages.css';

// # GEHealthcare-team1
// The color requrements:
// - "Compassion Purple" (Pantone 267 C, RGB 96/34/166, CMYK 81/99/0/0)
// - "White" (RGB 255/255/255, CMYK 0/0/0/0)
// - "Cool Gray" (Pantone Cool Gray 1 C, RGB 228/228/228, CMYK 0/0/0/10)
// Font requirement: "Inter" system-ui, Avenir, Helvetica, Arial, sans-serif

const STEPS = ['Connect & discover', 'Configure', 'Review & deploy', 'Collect'];

const SUMMARY = [
  { label: 'Devices', value: '5 / 5 reachable' },
  { label: 'Kubernetes nodes', value: '3 healthy' },
  { label: 'Backend services', value: '6 discovered' },
  { label: 'Clock variance', value: '2.8 seconds', warn: true },
  { label: 'Platform version', value: '3.4.2' },
];

const Environments = () => {
  const [host, setHost] = useState('192.168.0.4');
  const [port, setPort] = useState('22');
  const [account, setAccount] = useState('diagnostic-ops');
  const [secret, setSecret] = useState('');
  const [showSecret, setShowSecret] = useState(false);
  const [context, setContext] = useState('portrait-mobile-prod');

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <span className="page-eyebrow">New diagnostic session · Step 1 of 4</span>
          <h2 className="page-title">Connect &amp; discover</h2>
          <p className="page-subtitle">
            Verify access to the Portrait Mobile platform, then map devices, Kubernetes nodes, and
            backend services before collecting data.
          </p>
        </div>
        <span className="badge badge-success">Discovery complete</span>
      </section>

      <ol className="stepper">
        {STEPS.map((label, i) => (
          <li key={label} className={i === 0 ? 'step active' : 'step'}>
            <span className="step-num">{i + 1}</span>
            {label}
          </li>
        ))}
      </ol>

      <section className="two-col two-col-form">
        <div className="card">
          <h3 className="card-title">Platform access</h3>
          <p className="card-subtitle">
            Credentials are used for this discovery only and are not included in the package.
          </p>

          <div className="form-row">
            <label className="field grow">
              <span>Platform IP or hostname</span>
              <input value={host} onChange={(e) => setHost(e.target.value)} />
              <small>IPv4, IPv6, or resolvable host name</small>
            </label>
            <label className="field port">
              <span>SSH port</span>
              <input value={port} onChange={(e) => setPort(e.target.value)} />
              <small>1–65535</small>
            </label>
          </div>

          <div className="form-row">
            <label className="field grow">
              <span>Service account</span>
              <input value={account} onChange={(e) => setAccount(e.target.value)} />
            </label>
            <label className="field grow">
              <span>Password or token</span>
              <div className="input-with-action">
                <input
                  type={showSecret ? 'text' : 'password'}
                  value={secret}
                  placeholder="••••••••••••"
                  onChange={(e) => setSecret(e.target.value)}
                />
                <button type="button" onClick={() => setShowSecret(!showSecret)}>
                  {showSecret ? 'Hide' : 'Show'}
                </button>
              </div>
            </label>
          </div>

          <label className="field">
            <span>Kubernetes context</span>
            <input value={context} onChange={(e) => setContext(e.target.value)} />
            <small>Context validated · 3 accessible nodes</small>
          </label>

          <div className="alert alert-success">
            <strong>Validation passed</strong>
            <span>
              Host key verified. TLS certificate is trusted. Service account has read access and
              scoped temporary deployment permissions.
            </span>
          </div>

          <div className="action-row">
            <button className="btn btn-primary">Discover system</button>
            <button className="btn btn-secondary">Test credentials</button>
            <span className="card-subtitle">Last run 09:44:12 UTC · 8.3s</span>
          </div>
        </div>

        <aside className="card card-tinted summary-card">
          <h3 className="card-title">Discovery summary</h3>
          <p className="card-subtitle">Portrait Lab — Central</p>
          <dl className="summary-list">
            {SUMMARY.map((row) => (
              <div key={row.label}>
                <dt>{row.label}</dt>
                <dd className={row.warn ? 'warn' : ''}>{row.value}</dd>
              </div>
            ))}
          </dl>
          <button className="btn btn-primary btn-block">Continue to configuration</button>
        </aside>
      </section>
    </div>
  );
};

export default Environments;
