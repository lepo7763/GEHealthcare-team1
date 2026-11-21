import { CORE_SINCE_OPTIONS } from './coreDumps';

// Settings for the Core Dumps service: every core in the chosen time range is collected.
const CoreDumpSettings = ({ sinceHours, setSinceHours }) => (
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
);

export default CoreDumpSettings;
