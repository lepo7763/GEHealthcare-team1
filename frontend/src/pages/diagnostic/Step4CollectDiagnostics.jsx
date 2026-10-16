import { useEffect, useState } from 'react';
import '../pages.css';

// [PLACEHOLDER] The backend currently exposes Kubernetes log collection only.
// Replace these entries with real task endpoints when those collectors exist.
const COLLECTION_TASKS = [
  {
    id: 'kubernetes-logs',
    title: 'System and application logs',
    description: 'Collect application and service logs across the environment and include the collection manifest.',
    available: true,
  },
  {
    id: 'network-capture',
    title: 'Network information and packet captures',
    description: 'Netshoot and tshark collection is not connected to a backend endpoint yet. ',
    available: false,
  },
  {
    id: 'configuration-snapshot',
    title: 'Configuration snapshots',
    description: 'Configuration export is not connected to a backend endpoint yet. ',
    available: false,
  },
  {
    id: 'grafana',
    title: 'Grafana data and system health metrics',
    description: 'Grafana and health-metric collection are not connected to a backend endpoint yet. ',
    available: false,
  },
];

const formatTime = (totalSeconds) => {
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
};

const formatTimestamp = (value) => {
  if (!value) return 'Not collected';
  return new Date(value).toLocaleString();
};

const getTaskStatus = (status) => {
  if (status === 'running') return { label: 'Running', badge: 'badge-purple' };
  if (status === 'completed') return { label: 'Completed', badge: 'badge-success' };
  if (status === 'failed') return { label: 'Failed', badge: 'badge-warning' };
  return { label: 'Waiting', badge: 'badge-warning' };
};

const Step4CollectDiagnostics = ({ sessionData, updateSessionData, onNext, onBack }) => {
  const [tasks, setTasks] = useState(() =>
    COLLECTION_TASKS.map((task) => ({
      ...task,
      ...(sessionData.collectionTasks || []).find((savedTask) => savedTask.id === task.id),
    }))
  );
  const [currentTime, setCurrentTime] = useState(Date.now());

  const activeTask = tasks.find((task) => task.status === 'running');
  const logsTask = tasks.find((task) => task.id === 'kubernetes-logs');
  const collectionState = activeTask
    ? 'collecting'
    : logsTask?.status === 'completed'
      ? 'finished'
      : logsTask?.status === 'failed'
        ? 'failed'
        : 'idle';
  const collectionStartedAt = activeTask?.startedAt || logsTask?.startedAt;
  const elapsedSeconds = collectionStartedAt
    ? Math.max(0, Math.floor((currentTime - new Date(collectionStartedAt).getTime()) / 1000))
    : 0;
  const collectedBytes = logsTask?.sizeBytes || 0;

  useEffect(() => {
    if (collectionState !== 'collecting') return undefined;
    const interval = setInterval(() => setCurrentTime(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [collectionState]);

  const persistTasks = (nextTasks, state, additionalData = {}) => {
    setTasks(nextTasks);
    updateSessionData({
      collectionTasks: nextTasks,
      collectionState: state,
      ...additionalData,
    });
  };

  const handleCollectLogs = async () => {
    if (activeTask) return;

    const startedAt = new Date().toISOString();
    const runningTasks = tasks.map((task) => task.id === 'kubernetes-logs'
      ? { ...task, status: 'running', startedAt, completedAt: null, error: null }
      : task);
    persistTasks(runningTasks, 'collecting', { collectionStartedAt: startedAt });

    try {
      const response = await fetch('/api/logs/zip');
      if (!response.ok) {
        let detail = '';
        try {
          const body = await response.json();
          detail = body.detail || '';
        } catch {
          detail = '';
        }
        throw new Error(detail || `Log collection failed (HTTP ${response.status}).`);
      }

      const blob = await response.blob();
      const completedAt = new Date().toISOString();
      const filename = response.headers
        .get('Content-Disposition')
        ?.match(/filename="([^"]+)"/)?.[1] || 'k8s_cluster_logs.zip';
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);

      const completedTasks = tasks.map((task) => task.id === 'kubernetes-logs'
        ? {
          ...task,
          status: 'completed',
          completedAt,
          filename,
          sizeBytes: blob.size,
          error: null,
        }
        : task);
      const durationSeconds = Math.max(
        0,
        Math.floor((new Date(completedAt).getTime() - new Date(startedAt).getTime()) / 1000)
      );
      persistTasks(completedTasks, 'finished', {
        collectionCompletedAt: completedAt,
        elapsedSeconds: durationSeconds,
        collectedBytesMB: Number((blob.size / (1024 * 1024)).toFixed(2)),
      });
    } catch (error) {
      const completedAt = new Date().toISOString();
      const failedTasks = tasks.map((task) => task.id === 'kubernetes-logs'
        ? {
          ...task,
          status: 'failed',
          completedAt,
          error: error instanceof Error ? error.message : 'Log collection failed.',
        }
        : task);
      persistTasks(failedTasks, 'failed', { collectionCompletedAt: completedAt });
    }
  };

  const handleProceed = () => {
    window.alert('Diagnostic collection is still in development.');
    onNext();
  };

  return (
    <div className="step-content-pane">
      <div className="card-header" style={{ marginBottom: 'var(--eds-spacing-md)' }}>
        <div>
          <h3 className="card-title">4. Collect Diagnostics</h3>
          <p className="card-subtitle">
            Run available collection tasks and track their status, errors, and collection times.
          </p>
        </div>
        <span className="badge badge-purple">Step 4 of 6</span>
      </div>

      <div className="alert alert-warning" role="status" style={{ marginBottom: 'var(--eds-spacing-md)' }}>
        <strong>Collection capabilities:</strong>
        <span>
          System logs can be collected now. Other sources are placeholders until their backend
          collectors are implemented. The current log endpoint runs while its request remains
          active; navigating within this workflow does not cancel it, but browser/session recovery
          and backend cancellation are not yet supported.
        </span>
      </div>

      <div className="stat-grid" style={{ marginBottom: 'var(--eds-spacing-md)' }}>
        <div className="card stat-card">
          <span className={`badge ${collectionState === 'finished' ? 'badge-success' : collectionState === 'failed' ? 'badge-warning' : 'badge-purple'}`}>
            {collectionState === 'collecting'
              ? 'Active'
              : collectionState === 'finished'
                ? 'Complete'
                : collectionState === 'failed'
                  ? 'Failed'
                  : 'Not started'}
          </span>
          <div className="stat-value">{formatTime(elapsedSeconds)}</div>
          <div className="stat-label">Elapsed Collection Time</div>
        </div>
        <div className="card stat-card">
          <span className="badge badge-purple">Downloaded artifact</span>
          <div className="stat-value">{collectedBytes ? `${(collectedBytes / (1024 * 1024)).toFixed(2)} MB` : '—'}</div>
          <div className="stat-label">System log archive</div>
        </div>
        <div className="card stat-card">
          <span className="badge badge-purple">Sources</span>
          <div className="stat-value">{tasks.filter((task) => task.status === 'completed').length} / {tasks.length}</div>
          <div className="stat-label">Completed collection tasks</div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <h4 className="card-title" style={{ fontSize: '1rem' }}>Collection Tasks</h4>
            <p className="card-subtitle">
              Collected artifacts are downloaded as they complete; timestamps are saved with the session.
            </p>
          </div>
          <span className={`badge ${collectionState === 'finished' ? 'badge-success' : collectionState === 'failed' ? 'badge-warning' : 'badge-purple'}`}>
            {collectionState === 'collecting' ? 'Collection in progress' : collectionState === 'finished' ? 'Collection complete' : collectionState === 'failed' ? 'Collection failed' : 'Ready'}
          </span>
        </div>

        {activeTask && (
          <div className="alert alert-warning" role="status">
            <strong>Collection is running.</strong>
            <span>The backend does not report incremental progress. Keep this workflow open until the archive download begins.</span>
            <progress aria-label="System log collection in progress" style={{ display: 'block', width: '100%', marginTop: '10px' }} />
          </div>
        )}

        <ul className="check-list" style={{ marginTop: '12px' }}>
          {tasks.map((task) => {
            const status = getTaskStatus(task.status);
            return (
              <li key={task.id} style={{ alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <div className="check-title">{task.title}</div>
                  <div className="check-detail">{task.description}</div>
                  {task.startedAt && (
                    <div className="check-detail">Started: {formatTimestamp(task.startedAt)}</div>
                  )}
                  {task.completedAt && (
                    <div className="check-detail">Finished: {formatTimestamp(task.completedAt)}</div>
                  )}
                  {task.filename && (
                    <div className="check-detail">
                      Artifact: <span className="mono">{task.filename}</span> ({task.sizeBytes.toLocaleString()} bytes)
                    </div>
                  )}
                  {task.error && (
                    <div className="alert alert-warning" role="alert" style={{ marginTop: '8px' }}>
                      <strong>Collection error:</strong>
                      <span>{task.error} Check the environment connection and permissions, then retry.</span>
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className={`badge ${task.available ? status.badge : 'badge-warning'}`}>
                    {task.available ? status.label : 'Placeholder'}
                  </span>
                  {task.available && task.id === 'kubernetes-logs' && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleCollectLogs}
                      disabled={Boolean(activeTask)}
                    >
                      {task.status === 'running'
                        ? 'Collecting...'
                        : task.status === 'failed'
                          ? 'Retry'
                          : task.status === 'completed'
                            ? 'Collect again'
                            : 'Collect'}
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 'var(--eds-spacing-lg)' }}>
        <button type="button" className="btn btn-secondary" onClick={onBack}>
          &larr; Back to Deploy Tools
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleProceed}
        >
          {logsTask?.status === 'completed'
            ? 'Continue to Analyze & Package →'
            : 'Collect system logs to continue'}
        </button>
      </div>
    </div>
  );
};

export default Step4CollectDiagnostics;
