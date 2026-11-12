import { DateTimePicker } from '../../components/DateTimePicker';

// Controlled form for the Axone Logs tool parameters. 
const AxoneLogParamsForm = ({ value, onChange, idPrefix = 'axone' }) => {
  const set = (patch) => onChange({ ...value, ...patch });
  const hintIds = `${idPrefix}-range-hint ${idPrefix}-time-hint`;

  return (
    <fieldset className="log-export-fields log-export-form" aria-describedby={hintIds}>
      <legend className="log-export-legend">Axone log filters</legend>
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
          id={`${idPrefix}-start`}
          label="Start"
          value={value.start}
          onChange={(start) => set({ start })}
          describedBy={hintIds}
        />
        <DateTimePicker
          id={`${idPrefix}-end`}
          label="End"
          value={value.end}
          onChange={(end) => set({ end })}
          describedBy={hintIds}
        />
      </div>
      <p id={`${idPrefix}-range-hint`} className="log-export-hint">
        {value.scope === 'device'
          ? 'One device: up to 7 days. End time must be after start time.'
          : 'All devices: up to 1 hour, with the same hour on both timestamps (for example, 09:00 to 09:45).'}
      </p>
      <p id={`${idPrefix}-time-hint`} className="log-export-hint">
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
          aria-describedby={`${idPrefix}-category-hint`}
        />
        <small id={`${idPrefix}-category-hint`}>
          Leave blank for all events. Use a numeric code confirmed by your team; category names
          are not mapped yet.
        </small>
      </label>
    </fieldset>
  );
};

export default AxoneLogParamsForm;
