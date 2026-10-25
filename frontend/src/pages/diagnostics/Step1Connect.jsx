const Step1Connect = ({ host, setHost, phase, result, error, isChecking, onCheck }) => {
  return (
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
            onClick={onCheck}
            disabled={isChecking || !host.trim()}
          >
            {isChecking && <span className="btn-spinner" aria-hidden="true" />}
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
  );
};

export default Step1Connect;
