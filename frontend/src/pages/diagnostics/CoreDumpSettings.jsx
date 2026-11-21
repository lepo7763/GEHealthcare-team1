import { useState } from 'react';
import {
  CORE_SINCE_OPTIONS,
  CUSTOM_RANGE,
  customRangeError,
  dateKey,
} from './coreDumps';

const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
const pad = (n) => String(n).padStart(2, '0');
const toKey = (y, m, d) => `${y}-${pad(m + 1)}-${pad(d)}`;

// Month grid you click twice on: first click = start date, second = end date.
const RangeCalendar = ({ start, end, onChange }) => {
  const seed = start ? new Date(`${start}T00:00:00`) : new Date();
  const [view, setView] = useState({ year: seed.getFullYear(), month: seed.getMonth() });
  const { year, month } = view;

  const firstWeekday = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const today = dateKey();
  const cells = [
    ...Array(firstWeekday).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  const shiftMonth = (delta) => {
    const d = new Date(year, month + delta, 1);
    setView({ year: d.getFullYear(), month: d.getMonth() });
  };

  const pick = (key) => {
    if (!start || (start && end)) onChange({ start: key, end: '' }); // begin a new range
    else if (key < start) onChange({ start: key, end: start });
    else onChange({ start, end: key });
  };

  const monthLabel = new Date(year, month, 1).toLocaleString(undefined, {
    month: 'long',
    year: 'numeric',
  });

  return (
    <div className="range-calendar" role="group" aria-label="Choose date range">
      <div className="range-calendar-head">
        <button type="button" className="range-calendar-nav" onClick={() => shiftMonth(-1)} aria-label="Previous month">
          ‹
        </button>
        <strong>{monthLabel}</strong>
        <button type="button" className="range-calendar-nav" onClick={() => shiftMonth(1)} aria-label="Next month">
          ›
        </button>
      </div>
      <div className="range-calendar-grid">
        {WEEKDAYS.map((w) => (
          <span key={w} className="range-calendar-weekday">
            {w}
          </span>
        ))}
        {cells.map((day, i) => {
          if (day === null) return <span key={`blank-${i}`} />;
          const key = toKey(year, month, day);
          const isEdge = key === start || key === end;
          const inRange = start && end && key > start && key < end;
          const isFuture = key > today;
          return (
            <button
              key={key}
              type="button"
              className={`range-calendar-day${isEdge ? ' edge' : ''}${inRange ? ' in-range' : ''}`}
              aria-pressed={isEdge}
              disabled={isFuture}
              onClick={() => pick(key)}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );
};

// Settings for the Core Dumps service: every core in the chosen time range is collected.
const CoreDumpSettings = ({ sinceHours, setSinceHours, customRange, setCustomRange }) => {
  const isCustom = sinceHours === CUSTOM_RANGE;
  const bothDates = Boolean(customRange.start && customRange.end);
  const patch = (changes) => setCustomRange({ ...customRange, ...changes });
  const endIsToday = customRange.end === dateKey();
  const useNow = endIsToday && customRange.endNow;
  const rangeError = bothDates ? customRangeError(customRange) : '';

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

      {isCustom && (
        <>
          <RangeCalendar start={customRange.start} end={customRange.end} onChange={patch} />
          {!bothDates && (
            <small>
              {customRange.start ? 'Now click the end date.' : 'Click the start date, then the end date.'}
            </small>
          )}
          {bothDates && (
            <div className="form-row">
              <label className="field grow">
                <span>Start time ({customRange.start})</span>
                <input
                  type="time"
                  value={customRange.startTime}
                  onChange={(e) => patch({ startTime: e.target.value })}
                />
              </label>
              <div className="field grow">
                <span>End time ({customRange.end})</span>
                <div className="range-end-time">
                  <input
                    type="time"
                    value={customRange.endTime}
                    disabled={useNow}
                    max={endIsToday ? new Date().toTimeString().slice(0, 5) : undefined}
                    onChange={(e) => patch({ endTime: e.target.value })}
                  />
                  {endIsToday && (
                    <label className="range-now-check">
                      <input
                        type="checkbox"
                        checked={useNow}
                        onChange={(e) => patch({ endNow: e.target.checked })}
                      />
                      Current time
                    </label>
                  )}
                </div>
              </div>
            </div>
          )}
          {rangeError && <small className="field-error">{rangeError}</small>}
        </>
      )}
    </>
  );
};

export default CoreDumpSettings;
