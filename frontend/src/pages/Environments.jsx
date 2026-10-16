import { useState } from 'react';
import './pages.css';

// # GEHealthcare-team1
// The color requrements:
// - "Compassion Purple" (Pantone 267 C, RGB 96/34/166, CMYK 81/99/0/0)
// - "White" (RGB 255/255/255, CMYK 0/0/0/0)
// - "Cool Gray" (Pantone Cool Gray 1 C, RGB 228/228/228, CMYK 0/0/0/10)
// Font requirement: "Inter" system-ui, Avenir, Helvetica, Arial, sans-serif

const STEPS = ['Connect & discover', 'Configure', 'Review & deploy', 'Collect'];

const SERVICES = [
  {
    id: 'container-logs',
    name: 'Container Log Collection',
    description:
      'Collects logs from every container across all namespaces in the verified cluster.',
  },
  {
    id: 'wireshark',
    name: 'Wireshark',
    description: "Placeholder — capture network traffic across the platform's interfaces.",
  },
  {
    id: 'netshoot',
    name: 'Netshoot',
    description: 'Placeholder — run network diagnostics from a temporary debug container.',
  },
  {
    id: 'umf-rti',
    name: 'UMF RTI',
    description: 'Placeholder — collect real-time interface data from the UMF service.',
  },
];

const STEP_INFO = {
  1: {
    title: 'Connect & discover',
    subtitle: 'Verify Kubernetes reachability and cluster access from this workstation.',
  },
  2: {
    title: 'Configure collection',
    subtitle: 'Choose which services to include in this diagnostic session.',
  },
  3: {
    title: 'Review & deploy',
    subtitle: 'Confirm the collection plan before running it.',
  },
};

const Environments = () => {
  const [host, setHost] = useState('192.168.0.3');
  const [step, setStep] = useState(1);
  // idle -> checking -> done
  const [phase, setPhase] = useState('idle');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(['container-logs']);

  const isChecking = phase === 'checking';
  const info = STEP_INFO[step] || STEP_INFO[1];

  const toggleService = (id) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((serviceId) => serviceId !== id) : [...prev, id],
    );
  };

  const selectedServices = SERVICES.filter((service) => selected.includes(service.id));

  const resetCheck = () => {
    setPhase('idle');
    setResult(null);
    setError('');
  };

  const handleCheck = async () => {
    setPhase('checking');
    setResult(null);
    setError('');

    try {
      const response = await fetch('/api/environments/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: host.trim() }),
      });

      if (!response.ok) {
        let detail = `Request failed (${response.status}).`;
        try {
          const body = await response.json();
          if (body?.detail) {
            detail =
              typeof body.detail === 'string'
                ? body.detail
                : body.detail.map?.((d) => d.msg).join(', ') || JSON.stringify(body.detail);
          }
        } catch {
          // Non-JSON error body; keep the generic message.
        }
        throw new Error(detail);
      }

      const data = await response.json();
      setResult(data);
      setPhase('done');
      if (data.ok) {
        setStep(2);
      }
    } catch (e) {
      setError(e.message || 'Could not reach the analysis tool backend.');
      setPhase('done');
    }
  };

  const handleBackToConnect = () => {
    setStep(1);
    resetCheck();
  };

  return (
    <div className="page-stack">
      <section className="page-header-compact">
        <h2 className="page-title-sm">{info.title}</h2>
        <p className="page-subtitle-sm">{info.subtitle}</p>
      </section>

      <ol className="stepper">
        {STEPS.map((label, i) => (
          <li key={label} className={i === step - 1 ? 'step active' : 'step'}>
            <span className="step-num">{i + 1}</span>
            {label}
          </li>
        ))}
      </ol>

      {step === 1 && (
        <section className="section-narrow">
          <div className="card">
            <h3 className="card-title">Platform access</h3>
            <p className="card-subtitle">
              Requires a reachable Kubernetes API on port 6443 and a valid{' '}
              <code>~/.kube/config</code> file on this machine.
            </p>

            <div className="form-row" style={{ marginBottom: '1.15rem' }}>
              <label className="field grow">
                <span>Platform IP or hostname</span>
                <input
                  value={host}
                  placeholder="192.168.0.3"
                  disabled={isChecking}
                  onChange={(e) => setHost(e.target.value)}
                />
                <small>IPv4, IPv6, or resolvable host name</small>
              </label>
            </div>

            <div className="action-row">
              <button
                className="btn btn-primary"
                onClick={handleCheck}
                disabled={isChecking || !host.trim()}
              >
                {isChecking ? 'Checking…' : 'Check Kubernetes & access'}
              </button>
            </div>

            {isChecking && (
              <div
                className="progress progress-indeterminate"
                role="progressbar"
                aria-label="Checking platform connectivity and authentication"
              >
                <div className="progress-fill" />
              </div>
            )}

            {phase === 'done' && result && (
              <>
                <ul className="check-list">
                  <li>
                    <div>
                      <div className="check-title">
                        {result.reachability.ok ? 'Kubernetes reachable' : 'Kubernetes unreachable'} (
                        {result.host}:{result.port})
                      </div>
                      <div className="check-detail">{result.reachability.message}</div>
                    </div>
                    <span
                      className={`badge ${
                        result.reachability.ok ? 'badge-success' : 'badge-error'
                      }`}
                    >
                      {result.reachability.ok ? 'Passed' : 'Failed'}
                    </span>
                  </li>
                  <li>
                    <div>
                      <div className="check-title">
                        Cluster authentication (~/.kube/config)
                      </div>
                      <div className="check-detail">{result.authentication.message}</div>
                      {result.authentication.server && (
                        <div className="check-detail mono">
                          context: {result.authentication.context || '—'} · server:{' '}
                          {result.authentication.server}
                          {result.authentication.user ? ` · user: ${result.authentication.user}` : ''}
                        </div>
                      )}
                    </div>
                    <span
                      className={`badge ${
                        result.authentication.ok ? 'badge-success' : 'badge-error'
                      }`}
                    >
                      {result.authentication.ok ? 'Passed' : 'Failed'}
                    </span>
                  </li>
                </ul>

                {!result.ok && (
                  <div className="alert alert-error">
                    <strong>Cannot continue</strong>
                    <span>Resolve the failed check(s) above, then run the check again.</span>
                  </div>
                )}
              </>
            )}

            {error && (
              <div className="alert alert-error">
                <strong>Check failed</strong>
                <span>{error}</span>
              </div>
            )}
          </div>
        </section>
      )}

      {step === 2 && (
        <section className="section-narrow">
          <div className="card">
            <h3 className="card-title">Collection services</h3>
            <p className="card-subtitle">
              Select and configure the services to include in this diagnostic session.
            </p>

            {/* TODO: expose per-service options (e.g. Container Log Collection: max bytes
                per container, tail lines, include previous, throttle delay) once collection
                is wired up. */}
            <ul className="service-list">
              {SERVICES.map((service) => {
                const isSelected = selected.includes(service.id);
                return (
                  <li key={service.id}>
                    <button
                      type="button"
                      className={`service-option ${isSelected ? 'selected' : ''}`}
                      aria-pressed={isSelected}
                      onClick={() => toggleService(service.id)}
                    >
                      <div>
                        <div className="check-title">{service.name}</div>
                        <div className="check-detail">{service.description}</div>
                      </div>
                      <span className="service-check" aria-hidden="true">
                        {isSelected ? '✓' : ''}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>

            <div className="action-row">
              <button className="btn btn-secondary" onClick={handleBackToConnect}>
                Back
              </button>
              <button
                className="btn btn-primary"
                onClick={() => setStep(3)}
                disabled={selected.length === 0}
              >
                Continue to review
              </button>
            </div>

            {/* Always rendered (visibility-toggled) so showing the hint doesn't
                change the page height and jolt the layout/scrollbar. */}
            <p
              className="future-note"
              style={{ visibility: selected.length === 0 ? 'visible' : 'hidden' }}
            >
              Select at least one service to continue.
            </p>
          </div>
        </section>
      )}

      {step === 3 && (
        <section className="section-narrow">
          <div className="card">
            <h3 className="card-title">Review &amp; deploy</h3>
            <p className="card-subtitle">
              Confirm the details below, then go back to any step to make changes.
            </p>

            <ul className="check-list">
              <li>
                <div>
                  <div className="check-title">Platform connection</div>
                  {result && (
                    <div className="check-detail">
                      {result.host}:{result.port} · authenticated
                      {result.authentication.user ? ` as ${result.authentication.user}` : ''} via{' '}
                      {result.authentication.context || '~/.kube/config'}
                    </div>
                  )}
                </div>
                <button className="link-btn" onClick={() => setStep(1)}>
                  Edit
                </button>
              </li>
              <li>
                <div>
                  <div className="check-title">Collection services</div>
                  <div className="check-detail">
                    {selectedServices.length > 0
                      ? selectedServices.map((service) => service.name).join(', ')
                      : 'None selected'}
                  </div>
                </div>
                <button className="link-btn" onClick={() => setStep(2)}>
                  Edit
                </button>
              </li>
            </ul>

            <p className="future-note">Deploying the collection will be added in a later step.</p>
          </div>
        </section>
      )}
    </div>
  );
};

export default Environments;
