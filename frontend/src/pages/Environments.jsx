import { useState } from 'react';
import './pages.css';

// # GEHealthcare-team1
// The color requrements:
// - "Compassion Purple" (Pantone 267 C, RGB 96/34/166, CMYK 81/99/0/0)
// - "White" (RGB 255/255/255, CMYK 0/0/0/0)
// - "Cool Gray" (Pantone Cool Gray 1 C, RGB 228/228/228, CMYK 0/0/0/10)
// Font requirement: "Inter" system-ui, Avenir, Helvetica, Arial, sans-serif

const STEPS = ['Connect & discover', 'Configure', 'Review & deploy', 'Collect'];

const Environments = () => {
  const [host, setHost] = useState('192.168.0.3');
  const [step, setStep] = useState(1);
  // idle -> checking -> done
  const [phase, setPhase] = useState('idle');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const isChecking = phase === 'checking';

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

  const handleBack = () => {
    setStep(1);
    resetCheck();
  };

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <span className="page-eyebrow">New diagnostic session · Step {step} of 4</span>
          <h2 className="page-title">{step === 2 ? 'Configure' : 'Connect & discover'}</h2>
          <p className="page-subtitle">
            {step === 2
              ? 'Configure the collection once the platform has been verified.'
              : 'Verify that Kubernetes is reachable and that this workstation is authenticated before collecting data.'}
          </p>
        </div>
      </section>

      <ol className="stepper">
        {STEPS.map((label, i) => (
          <li key={label} className={i === step - 1 ? 'step active' : 'step'}>
            <span className="step-num">{i + 1}</span>
            {label}
          </li>
        ))}
      </ol>

      {step === 1 ? (
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
                        Kubernetes unreachable ({result.host}:{result.port})
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
      ) : (
        <section className="section-narrow">
          <div className="card">
            <h3 className="card-title">Configure</h3>
            <p className="card-subtitle">Configuration options are coming soon.</p>

            {result?.ok && (
              <div className="alert alert-success">
                <strong>Platform connected</strong>
                <span>
                  Kubernetes reachable at {result.host}:{result.port} and authenticated
                  {result.authentication.user ? ` as ${result.authentication.user}` : ''} via{' '}
                  {result.authentication.context || '~/.kube/config'}.
                </span>
              </div>
            )}

            <div className="action-row">
              <button className="btn btn-secondary" onClick={handleBack}>
                Back
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
};

export default Environments;
