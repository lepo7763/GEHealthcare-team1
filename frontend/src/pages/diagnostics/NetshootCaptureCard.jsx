import { NETSHOOT_SCOPE_TEXT } from './netshootApi';

// Step 4 card for a Netshoot packet capture: overall progress, one row per node
// (one Netshoot Job per node), Cancel while running, and Download when finished or
// cancelled with partial results. State comes from netshootApi.startNetshootCapture.

const STATUS_TEXT = {
  scheduling: 'Scheduling capture Jobs…',
  capturing: 'Capturing',
  packaging: 'Packaging capture files…',
  done: 'Capture complete',
  cancelled: 'Capture cancelled',
  error: 'Capture failed',
};

const NetshootCaptureCard = ({ capture, onCancel }) => {
  const { status, elapsed, durationSeconds, nodes, download, error, scope } = capture;
  const isRunning = status === 'scheduling' || status === 'capturing';
  const percent =
    status === 'done' || status === 'packaging'
      ? 100
      : Math.min(100, Math.round((elapsed / durationSeconds) * 100));
  const indeterminate = status === 'scheduling';
  const totalPods = nodes.reduce((sum, node) => sum + node.pods, 0);
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
  const nodeText = (node) =>
    [node.pods > 0 && plural(node.pods, 'pod'), node.host && 'host'].filter(Boolean).join(' + ');
  const targetSummary =
    scope === 'host'
      ? `host traffic on ${plural(nodes.length, 'node')}`
      : `${plural(totalPods, 'pod')}${scope === 'both' ? ' + host' : ''} on ${plural(nodes.length, 'node')}`;

  return (
    <div className={`service-progress-card service-progress-${status === 'capturing' ? 'collecting' : status}`}>
      <div className="service-progress-head">
        <div>
          <div className="check-title">Netshoot packet capture</div>
          <div className="check-detail">
            {STATUS_TEXT[status] || status}
            {status === 'capturing' || status === 'cancelled'
              ? ` · ${elapsed} of ${durationSeconds} seconds`
              : ''}
            {nodes.length > 0
              ? ` · ${targetSummary}`
              : ''}
          </div>
        </div>
        {!indeterminate && status !== 'error' && (
          <span className="service-progress-percent">{percent}%</span>
        )}
      </div>

      <div
        className={indeterminate ? 'progress progress-indeterminate' : 'progress'}
        role="progressbar"
        aria-label="Netshoot capture progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate ? undefined : percent}
      >
        <div className="progress-fill" style={indeterminate ? undefined : { width: `${percent}%` }} />
      </div>

      <p className="collect-meta">
        Scope: {NETSHOOT_SCOPE_TEXT[scope]}
      </p>

      {nodes.length > 0 && (
        <ul className="netshoot-node-list">
          {nodes.map((node) => (
            <li key={node.node}>
              <span className="mono">{node.node}</span>
              <span>
                {nodeText(node)} · Job{' '}
                <span className="mono">{node.jobName}</span>
              </span>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="collect-meta collect-error">{error}</p>}
      {status === 'cancelled' && (
        <p className="collect-meta">
          {download
            ? 'Packets captured before cancelling were kept.'
            : 'Cancelled before any packets were captured.'}
        </p>
      )}

      {(isRunning || download) && (
        <div className="action-row">
          {isRunning && (
            <button type="button" className="btn btn-secondary" onClick={onCancel}>
              Cancel capture
            </button>
          )}
          {download && (
            <a className="btn btn-primary" href={download.url} download={download.filename}>
              {status === 'cancelled' ? 'Download partial capture' : 'Download capture'}
            </a>
          )}
        </div>
      )}
    </div>
  );
};

export default NetshootCaptureCard;
