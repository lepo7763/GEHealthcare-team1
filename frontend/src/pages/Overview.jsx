import { useState } from 'react';
import './pages.css';
import PasswordInput from '../components/PasswordInput';

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

const KIND_ORDER = ['viewer', 'hub', 'backend', 'node', 'service'];
const KIND_LABEL = {
  viewer: 'Viewer',
  hub: 'Hub',
  backend: 'Backend',
  node: 'Kubernetes node',
  service: 'Service',
};

const errorText = async (response) => {
  let detail = `Request failed (${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body?.detail === 'string') detail = body.detail;
    else if (Array.isArray(body?.detail)) detail = body.detail.map((d) => d.msg).join(', ');
  } catch {
    // Non-JSON body; keep generic message.
  }
  return detail;
};

const TopologyNode = ({ c }) => (
  <div className="topo-node" title={c.detail || ''}>
    <div>
      <div className="check-title">{c.name}</div>
      <div className="mono">{c.address || 'no address'}</div>
    </div>
    <span
      className={`status-dot ${c.online ? '' : 'status-dot-off'}`}
      aria-label={c.online ? 'Online' : 'Offline'}
    />
  </div>
);

const Overview = ({ onNavigate }) => {
  const [host, setHost] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [discovering, setDiscovering] = useState(false);
  const [discovery, setDiscovery] = useState(null);
  const [error, setError] = useState('');

  const handleDiscover = async (e) => {
    e.preventDefault();
    setDiscovering(true);
    setError('');
    setDiscovery(null);
    try {
      const response = await fetch('/api/environments/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          host: host.trim(),
          username: username.trim() || null,
          password: password || null,
        }),
      });
      if (!response.ok) throw new Error(await errorText(response));
      setDiscovery(await response.json());
    } catch (err) {
      setError(err.message || 'Discovery failed.');
    } finally {
      setPassword('');
      setDiscovering(false);
    }
  };

  const components = discovery?.ok ? discovery.components : [];
  const online = components.filter((c) => c.online).length;
  const groups = KIND_ORDER.map((kind) => ({
    kind,
    items: components.filter((c) => c.kind === kind),
  })).filter((g) => g.items.length);

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

      <section className="card">
        <h3 className="card-title">Connect to platform</h3>
        <p className="card-subtitle">
          Provide the platform address and credentials. The platform's Kubernetes nodes are
          discovered automatically.
          Leave credentials empty to use <code>~/.kube/config</code> on this machine.
        </p>
        <form onSubmit={handleDiscover} autoComplete="off">
          <div className="form-row">
            <label className="field grow">
              <span>Platform IP or hostname</span>
              <input
                value={host}
                placeholder="192.168.0.3"
                disabled={discovering}
                onChange={(e) => setHost(e.target.value)}
              />
            </label>
            <label className="field grow">
              <span>Username</span>
              <input
                value={username}
                autoComplete="off"
                disabled={discovering}
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>
            <label className="field grow">
              <span>Password</span>
              <PasswordInput
                value={password}
                autoComplete="new-password"
                disabled={discovering}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
          </div>
          <div className="action-row" style={{ marginTop: '1.15rem' }}>
            <button className="btn btn-primary" type="submit" disabled={discovering || !host.trim()}>
              {discovering && <span className="btn-spinner" aria-hidden="true" />}
              {discovering ? 'Discovering…' : 'Connect & discover'}
            </button>
          </div>
        </form>
        {discovering && (
          <div className="progress progress-indeterminate" role="progressbar" aria-label="Discovering components">
            <div className="progress-fill" />
          </div>
        )}
        {error && (
          <div className="alert alert-error">
            <strong>Discovery failed</strong>
            <span>{error}</span>
          </div>
        )}
        {discovery && !discovery.ok && (
          <div className="alert alert-error">
            <strong>Could not discover components</strong>
            <span>{discovery.message}</span>
          </div>
        )}
      </section>

      {discovery?.ok && (
        <section className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Discovered topology</h3>
              <p className="card-subtitle">
                Components found on {discovery.host}. Addresses can be overridden before deployment.
              </p>
            </div>
            <span className="badge badge-success">
              {online} of {components.length} online
            </span>
          </div>
          {groups.length === 0 ? (
            <p className="card-subtitle">No components were reported by the platform.</p>
          ) : (
            <div className="topo-panel">
              <div className="topo-node topo-root">
                <div>
                  <div className="check-title">Platform</div>
                  <div className="mono">{discovery.host}</div>
                </div>
                <span className="status-dot" aria-label="Reachable" />
              </div>
              {groups.map((g) => (
                <div className="topo-group" key={g.kind}>
                  <div className="topo-group-label">
                    {KIND_LABEL[g.kind]} · {g.items.length}
                  </div>
                  <div className="topo-row">
                    {g.items.map((c) => (
                      <TopologyNode c={c} key={`${c.kind}-${c.name}`} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

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
