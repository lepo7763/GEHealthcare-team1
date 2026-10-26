import './pages.css';

const STATS = [
  { value: '92%', label: 'Environment readiness', badge: '1 advisory', tone: 'success' },
  { value: '11', label: 'Discovered components', badge: '5 devices · 6 services', tone: 'purple' },
  { value: '1', label: 'Active sessions', badge: '18m 42s elapsed', tone: 'purple' },
  { value: 'Ready', label: 'Package status', badge: '2 exports retained', tone: 'success' },
];

const CHECKS = [
  { title: 'Platform reachability', detail: 'Viewer, hub, MiniEdge reachable', status: 'Passed' },
  { title: 'System access', detail: '3 nodes healthy · 18 services running', status: 'Passed' },
  { title: 'Local storage', detail: '286 GB available', status: 'Passed' },
  { title: 'Clock alignment', detail: 'Drift detected: 2.8 seconds', status: 'Advisory' },
];

const DEVICES = [
  { name: 'Viewer', ip: '192.168.0.5' },
  { name: 'Virtual Hub', ip: '192.168.0.4' },
  { name: 'MiniEdge P360', ip: '192.168.0.3' },
  { name: 'Workstation', ip: '192.168.0.6' },
];

const SESSIONS = [
  { id: 'SES-240928-0947', tag: 'Live collection', meta: 'Netshoot · UMF RTI · tshark', time: '18:42' },
  { id: 'SES-240927-1612', tag: 'Partial results preserved', meta: 'Netshoot · tshark', time: '64% complete' },
];

const Overview = ({ onNavigate }) => {
  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <span className="page-eyebrow">Operations overview</span>
          <h2 className="page-title">Portrait Lab — Central</h2>
          <p className="page-subtitle">
            Readiness, active collection, and recent diagnostic evidence for the connected environment.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => onNavigate?.('diagnostics')}>
          Start diagnostic session
        </button>
      </section>

      <section className="stat-grid">
        {STATS.map((s) => (
          <div className="card stat-card" key={s.label}>
            <span className={`badge badge-${s.tone}`}>{s.badge}</span>
            <div className="stat-value">{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </section>

      <section className="two-col">
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Environment readiness</h3>
              <p className="card-subtitle">Last verified today at 09:42 UTC</p>
            </div>
            <span className="badge badge-success">Operational</span>
          </div>
          <div className="progress">
            <div className="progress-fill" style={{ width: '92%' }} />
          </div>
          <p className="card-subtitle">11 of 12 readiness checks passed</p>
          <ul className="check-list">
            {CHECKS.map((c) => (
              <li key={c.title}>
                <div>
                  <div className="check-title">{c.title}</div>
                  <div className="check-detail">{c.detail}</div>
                </div>
                <span className={`badge ${c.status === 'Passed' ? 'badge-success' : 'badge-warning'}`}>
                  {c.status}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="card card-tinted">
          <h3 className="card-title">Discovered system</h3>
          <p className="card-subtitle">Portrait Mobile 3.4.2</p>
          <ul className="device-list">
            {DEVICES.map((d) => (
              <li key={d.name}>
                <div>
                  <div className="check-title">{d.name}</div>
                  <div className="mono">{d.ip}</div>
                </div>
                <span className="status-dot" aria-label="Reachable" />
              </li>
            ))}
          </ul>
          <button className="btn btn-secondary btn-block" onClick={() => onNavigate?.('diagnostics')}>
            Start diagnostics
          </button>
        </div>
      </section>

      <section className="two-col">
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Recent sessions</h3>
              <p className="card-subtitle">Collection history retained on this workstation</p>
            </div>
            <button className="link-btn" onClick={() => onNavigate?.('diagnostics')}>
              View all sessions
            </button>
          </div>
          <ul className="session-list">
            {SESSIONS.map((s) => (
              <li key={s.id}>
                <div>
                  <span className="mono-strong">{s.id}</span>
                  <span className="badge badge-purple">{s.tag}</span>
                  <div className="check-detail">{s.meta}</div>
                </div>
                <span className="session-time">{s.time}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <h3 className="card-title">Alerts</h3>
          <p className="card-subtitle">1 item needs attention</p>
          <div className="alert alert-warning">
            <strong>Clock drift may affect correlation</strong>
            <span>Virtual Hub Self is 2.8 seconds ahead of the workstation.</span>
          </div>
        </div>
      </section>
    </div>
  );
};

export default Overview;
