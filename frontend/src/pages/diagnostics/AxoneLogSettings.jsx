import { DateTimePicker } from '../../components/DateTimePicker';

// Axone Logs settings for the Configure step: device scope, device UUID, the
// local time range (shadcn calendar + time fields) and an optional event code.
// `issue` is the current validation message from toAxoneQuery, or null.
const AxoneLogSettings = ({ value, onChange, issue }) => {
  const set = (patch) => onChange({ ...value, ...patch });
  const hintIds = 'axone-range-hint axone-time-hint';

  return (
    <div className="log-export-fields log-export-form" aria-describedby={hintIds}>
      <div className="log-export-grid">
        <label className="field log-export-full">
          <span>Device scope</span>
          <select value={value.scope} onChange={(event) => set({ scope: event.target.value })}>
            <option value="device">One device</option>
            <option value="all">All devices</option>
          </select>
        </label>
        {value.scope === 'device' && (
          <label className="field log-export-full">
            <span>Device UUID</span>
            <input
              value={value.deviceuuid}
              onChange={(event) => set({ deviceuuid: event.target.value })}
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
          value={value.start}
          onChange={(start) => set({ start })}
          describedBy={hintIds}
        />
        <DateTimePicker
          id="axone-end"
          label="End"
          value={value.end}
          onChange={(end) => set({ end })}
          describedBy={hintIds}
        />
      </div>
      <p id="axone-range-hint" className="log-export-hint">
        {value.scope === 'device'
          ? 'One device: up to 7 days. End time must be after start time.'
          : 'All devices: up to 1 hour, with the same hour on both timestamps (for example, 09:00 to 09:45).'}
      </p>
      <p id="axone-time-hint" className="log-export-hint">
        Use the log service's local date and time. Logs are exported as CSV.
      </p>
      <label className="field">
        <span>Event category code (optional)</span>
        <input
          type="number"
          step="1"
          value={value.eventCategory}
          onChange={(event) => set({ eventCategory: event.target.value })}
          placeholder="All events"
          aria-describedby="axone-category-hint"
        />
        <small id="axone-category-hint">
          Leave blank for all events. Use a numeric code confirmed by your team; category names
          are not mapped yet.
        </small>
      </label>
      {issue && (
        <small className="field-error" role="status">
          {issue}
        </small>
      )}
    </div>
  );
};

export default AxoneLogSettings;
