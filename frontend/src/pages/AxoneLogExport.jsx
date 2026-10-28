import { useState } from 'react';
import { DateTimePicker } from '../components/DateTimePicker';
import { toLocalDateTime } from '../lib/dateTime';
import { normalizeTime } from '../lib/time';
import { buildLogExportQuery, downloadLogs } from '../lib/logExport';

const AxoneLogExport = () => {
  const [scope, setScope] = useState('device');
  const [format, setFormat] = useState('csv');
  const [deviceuuid, setDeviceuuid] = useState('');
  const [eventCategory, setEventCategory] = useState('');
  const [start, setStart] = useState({ date: undefined, time: '' });
  const [end, setEnd] = useState({ date: undefined, time: '' });
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');

  const exportLogs = async (event) => {
    event.preventDefault();
    setError('');
    setStatus('');

    try {
      const query = buildLogExportQuery({
        scope,
        format,
        deviceuuid,
        eventCategory,
        startTimestamp: toLocalDateTime(start.date, normalizeTime(start.time)),
        endTimestamp: toLocalDateTime(end.date, normalizeTime(end.time)),
      });
      setIsExporting(true);
      await downloadLogs(`/api/logs/export?${query}`, `axone_logs.${format}`);
      setStatus(`${format.toUpperCase()} download started.`);
    } catch (error) {
      setError(error instanceof TypeError
        ? 'Could not reach the backend. Make sure it is running and try again.'
        : error.message);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <section className="card" aria-labelledby="axone-export-title">
      <h3 id="axone-export-title" className="card-title">Export Axone logs</h3>
      <p className="card-subtitle">Download stored system logs for one device or all devices.</p>

      <form className="log-export-form" onSubmit={exportLogs} aria-describedby="axone-range-hint axone-time-hint">
        <fieldset className="log-export-fields" disabled={isExporting}>
          <legend className="log-export-legend">Log filters</legend>
          <div className="log-export-grid">
            <label className="field">
              <span>Device scope</span>
              <select value={scope} onChange={(event) => { setScope(event.target.value); setError(''); setStatus(''); }}>
                <option value="device">One device</option>
                <option value="all">All devices</option>
              </select>
            </label>
            <label className="field">
              <span>File format</span>
              <select value={format} onChange={(event) => setFormat(event.target.value)}>
                <option value="csv">CSV (.csv)</option>
                <option value="json">JSON (.json)</option>
              </select>
            </label>
            {scope === 'device' && (
              <label className="field log-export-full">
                <span>Device UUID</span>
                <input
                  value={deviceuuid}
                  onChange={(event) => setDeviceuuid(event.target.value)}
                  placeholder="d4e5f6a7-1234-5678-9abc-def012345678"
                  required
                  spellCheck={false}
                  autoComplete="off"
                />
                <small>Enter the device/source UUID used by the log service.</small>
              </label>
            )}
            <DateTimePicker
              id="axone-start"
              label="Start"
              value={start}
              onChange={setStart}
              disabled={isExporting}
              describedBy="axone-range-hint axone-time-hint"
            />
            <DateTimePicker
              id="axone-end"
              label="End"
              value={end}
              onChange={setEnd}
              disabled={isExporting}
              describedBy="axone-range-hint axone-time-hint"
            />
          </div>
          <p id="axone-range-hint" className="log-export-hint">
            {scope === 'device'
              ? 'One device: up to 7 days. End time must be after start time.'
              : 'All devices: up to 1 hour, with the same hour on both timestamps (for example, 09:00 to 09:45).'}
          </p>
          <p id="axone-time-hint" className="log-export-hint">Use the log service's local date and time.</p>
          <label className="field">
            <span>Event category code (optional)</span>
            <input
              type="number"
              step="1"
              value={eventCategory}
              onChange={(event) => setEventCategory(event.target.value)}
              placeholder="All events"
              aria-describedby="axone-category-hint"
            />
            <small id="axone-category-hint">Leave blank for all events. Use a numeric code confirmed by your team; category names are not mapped yet.</small>
          </label>
          <div className="action-row log-export-actions">
            <button type="submit" className="btn btn-primary" aria-busy={isExporting}>
              {isExporting ? 'Exporting...' : `Export Axone logs ${format.toUpperCase()}`}
            </button>
          </div>
        </fieldset>
        <p className="log-export-status" role="status">
          {isExporting ? 'Preparing your download. This may take a moment.' : status}
        </p>
        {error && <p className="alert alert-warning" role="alert">{error}</p>}
      </form>
    </section>
  );
};

export default AxoneLogExport;
