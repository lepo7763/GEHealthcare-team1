// Renders the AnalysisReport returned by POST /api/analysis/zip.
// Log lines come from the cluster, so they're only ever rendered as React text
// (which escapes them), never with dangerouslySetInnerHTML.

const label = (c) => `${c.namespace}/${c.pod}/${c.container}`;

const AnalysisReport = ({ report }) => {
  const crashed = new Set(report.crashed_containers);
  const maxPatternCount = Math.max(1, ...report.top_errors.map((p) => p.count));
  const maxContainerLines = Math.max(
    1,
    ...report.containers.map((c) => c.error_lines + c.warning_lines),
  );
  const problems = [
    ...report.collection_errors.map((e) => ({
      key: `c-${e.namespace}/${e.pod}/${e.container}`,
      where: `${e.namespace}/${e.pod}/${e.container}`,
      text: `Not collected: ${e.reason}${e.status ? ` (${e.status})` : ''}`,
    })),
    ...report.skipped_files.map((f) => ({ key: `s-${f}`, where: '', text: `Skipped: ${f}` })),
  ];

  return (
    <div className="page-stack">
      <section className="stat-grid" aria-label="Analysis totals">
        <div className="card stat-card">
          <span className="stat-value">{report.files_analyzed}</span>
          <span className="stat-label">log files · {report.total_lines} lines</span>
        </div>
        <div className="card stat-card">
          <span className="stat-value analysis-error-text">{report.error_lines}</span>
          <span className="stat-label">error lines</span>
        </div>
        <div className="card stat-card">
          <span className="stat-value analysis-warning-text">{report.warning_lines}</span>
          <span className="stat-label">warning lines</span>
        </div>
        <div className="card stat-card">
          <span className="stat-value analysis-error-text">{report.crashed_containers.length}</span>
          <span className="stat-label">crashed containers</span>
        </div>
      </section>

      <section className="card" aria-labelledby="top-errors-title">
        <h3 id="top-errors-title" className="card-title">Most frequent errors</h3>
        <p className="card-subtitle">
          Lines that differ only by time, IDs, IPs or numbers are counted together.
        </p>
        {report.top_errors.length === 0 ? (
          <p className="check-detail">No errors found.</p>
        ) : (
          <div className="analysis-table-wrap">
            <table className="analysis-table">
              <thead>
                <tr><th>Count</th><th aria-hidden="true" /><th>Example</th><th>Where</th><th>Suggested action</th></tr>
              </thead>
              <tbody>
                {report.top_errors.map((p) => (
                  <tr key={p.pattern}>
                    <td className="analysis-num">{p.count}</td>
                    <td className="analysis-bar-cell">
                      <div className="analysis-bar" style={{ width: `${(p.count / maxPatternCount) * 100}%` }} />
                    </td>
                    <td><code className="mono">{p.example}</code></td>
                    <td>{p.containers.map((c) => <div key={c}>{c}</div>)}</td>
                    <td className="analysis-action">
                      {p.recommendation ? (
                        <>
                          <strong>{p.recommendation.title}</strong>
                          <span>{p.recommendation.action}</span>
                        </>
                      ) : (
                        <span className="check-detail">No known fix — send to engineering.</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card" aria-labelledby="containers-title">
        <h3 id="containers-title" className="card-title">Containers</h3>
        <p className="card-subtitle">Most errors first.</p>
        <div className="analysis-table-wrap">
          <table className="analysis-table">
            <thead>
              <tr><th>Container</th><th>Errors</th><th>Warnings</th><th aria-hidden="true" /><th>First error</th></tr>
            </thead>
            <tbody>
              {report.containers.map((c) => (
                <tr key={`${label(c)}-${c.is_previous}`}>
                  <td>
                    {label(c)}{' '}
                    {c.is_previous && <span className="badge badge-error">before crash</span>}
                    {!c.is_previous && crashed.has(label(c)) && (
                      <span className="badge badge-warning">restarted</span>
                    )}
                  </td>
                  <td className="analysis-num">{c.error_lines}</td>
                  <td className="analysis-num">{c.warning_lines}</td>
                  <td className="analysis-bar-cell">
                    <div className="analysis-bar" style={{ width: `${(c.error_lines / maxContainerLines) * 100}%` }} />
                    <div className="analysis-bar analysis-bar-warning" style={{ width: `${(c.warning_lines / maxContainerLines) * 100}%` }} />
                  </td>
                  <td>{c.first_error ? <code className="mono">{c.first_error}</code> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {problems.length > 0 && (
        <section className="card" aria-labelledby="problems-title">
          <h3 id="problems-title" className="card-title">Could not collect / skipped</h3>
          <ul className="check-list">
            {problems.map((p) => (
              <li key={p.key}>
                <div>
                  {p.where && <span className="check-title mono">{p.where}</span>}
                  <span className="check-detail" style={{ display: 'block' }}>{p.text}</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
};

export default AnalysisReport;
