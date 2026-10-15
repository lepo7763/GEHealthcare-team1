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
  const [host, setHost] = useState('192.168.0.3');
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
            Must have a valid <code>~/.kube/config</code> file on this machine.
          </p>

          <div className="form-row" style={{ marginBottom: "1.15rem" }}>
            <label className="field grow">
              <span>Platform IP or hostname</span>
              <input placeholder={host} onChange={(e) => setHost(e.target.value)} />
              <small>IPv4, IPv6, or resolvable host name</small>
            </label>
          </div>

          <div className="action-row">
            <button className="btn btn-primary">Discover system</button>
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
