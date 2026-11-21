import {
  CORE_SINCE_OPTIONS,
  estimateSelection,
  formatBytes,
  formatTime,
  groupByProcess,
} from './coreDumps';

// Settings + live preview for the Core Dumps service. The preview comes from
// GET /api/core-dumps (a short-lived collector Job lists the node's cores).
const CoreDumpSettings = ({
  sinceHours,
  setSinceHours,
  processes,
  setProcesses,
  preview,
  onRefresh,
}) => {
  const files = preview.data?.files || [];
  const groups = groupByProcess(files);
  const estimate = estimateSelection(files, { sinceHours, processes });
  const host = preview.data?.host_config;
  const handlerMissing = host && host.core_pattern && !host.core_pattern.includes('coredump_handler');

  const toggleProcess = (name) => {
    setProcesses((prev) => (prev.includes(name) ? prev.filter((p) => p !== name) : [...prev, name]));
  };

  return (
    <>
      <div className="form-row">
        <label className="field grow">
          <span>Dumped since</span>
          <select value={sinceHours} onChange={(e) => setSinceHours(e.target.value)}>
            {CORE_SINCE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <small>Based on the crash time recorded in each core's filename.</small>
        </label>
      </div>

      <div className="core-preview">
        <div className="core-preview-head">
          <span className="check-title">Cores on the node</span>
          <button
            type="button"
            className="link-btn"
            onClick={onRefresh}
            disabled={preview.status === 'loading'}
          >
            {preview.status === 'loading' ? 'Scanning…' : 'Rescan'}
          </button>
        </div>

        {preview.status === 'loading' && !preview.data && (
          <p className="collect-meta">Scanning the node for core files…</p>
        )}
        {preview.status === 'error' && (
          <p className="collect-meta collect-error">
            Could not list core dumps: {preview.error}. You can still collect; any
            failure will be recorded in the package.
          </p>
        )}

        {preview.data && (
          <>
            <p className="collect-meta">
              {files.length} core{files.length === 1 ? '' : 's'} ·{' '}
              {formatBytes(preview.data.total_bytes)} in{' '}
              <span className="mono">{preview.data.host_dir}</span>
              {preview.data.node ? (
                <>
                  {' '}on <span className="mono">{preview.data.node}</span>
                </>
              ) : null}
            </p>
            {handlerMissing && (
              <p className="collect-meta collect-error">
                The kernel core_pattern is <span className="mono">{host.core_pattern}</span>, not
                the Axone handler, so new cores may not land here.
              </p>
            )}

            {groups.length > 0 ? (
              <div className="analysis-table-wrap">
                <table className="analysis-table core-table">
                  <thead>
                    <tr>
                      <th scope="col" aria-label="Include" />
                      <th scope="col">Process</th>
                      <th scope="col">Cores</th>
                      <th scope="col">Signal</th>
                      <th scope="col">Latest</th>
                      <th scope="col">Size</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groups.map((g) => {
                      const selectable = g.process !== '(unrecognized name)';
                      return (
                        <tr key={g.process}>
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Only include ${g.process}`}
                              disabled={!selectable}
                              checked={processes.includes(g.process)}
                              onChange={() => toggleProcess(g.process)}
                            />
                          </td>
                          <td className="mono">{g.process}</td>
                          <td>{g.count}</td>
                          <td>{g.signals.join(', ') || '—'}</td>
                          <td>{formatTime(g.latest)}</td>
                          <td>{formatBytes(g.bytes)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="collect-meta">No core files found on the node.</p>
            )}

            <p className="collect-meta">
              {processes.length === 0
                ? 'No processes ticked: all processes are included. '
                : `Only ${processes.join(', ')}. `}
              <strong>
                Will collect {estimate.count} core{estimate.count === 1 ? '' : 's'} ·{' '}
                {formatBytes(estimate.bytes)}
              </strong>
            </p>
          </>
        )}
      </div>
    </>
  );
};

export default CoreDumpSettings;
