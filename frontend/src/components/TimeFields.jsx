import { Input } from '@/components/ui/input';

const UNITS = [
  { key: 'hours', label: 'Hours', placeholder: 'HH', max: 23, width: 2 },
  { key: 'minutes', label: 'Minutes', placeholder: 'MM', max: 59, width: 2 },
  { key: 'seconds', label: 'Seconds', placeholder: 'SS', max: 59, width: 2 },
  { key: 'milliseconds', label: 'Millisec.', placeholder: '000', max: 999, width: 3 },
];

function splitTime(value) {
  if (!value) return ['', '', '', ''];
  const [clock, fraction = '000'] = value.split('.');
  const [hours = '', minutes = '', seconds = '00'] = clock.split(':');
  return [hours, minutes, seconds, fraction];
}

export function TimeFields({ id, label, value, onChange, disabled = false }) {
  const parts = splitTime(value);

  const updatePart = (index, text) => {
    const next = value ? [...parts] : ['00', '00', '00', '000'];
    next[index] = text;
    onChange(`${next[0]}:${next[1]}:${next[2]}.${next[3]}`);
  };

  return (
    <fieldset className="m-0 min-w-0 border-0 p-0" disabled={disabled} aria-label={`${label} time`}>
      <legend className="mb-2 p-0 text-sm font-medium">Time (24-hour)</legend>
      <div className="grid grid-cols-4 gap-2">
        {UNITS.map((unit, index) => {
          const text = index === 3 && parts[index] !== ''
            ? String(Number(parts[index].padEnd(3, '0')))
            : parts[index];
          const invalid = text !== '' && Number(text) > unit.max;
          return (
            <label key={unit.key} className="grid min-w-0 gap-1 text-xs text-muted-foreground" htmlFor={`${id}-${unit.key}`}>
              <span>{unit.label}</span>
              <Input
                id={`${id}-${unit.key}`}
                type="text"
                role="spinbutton"
                inputMode="numeric"
                autoComplete="off"
                maxLength={unit.width}
                placeholder={unit.placeholder}
                value={text}
                aria-label={`${label} ${unit.key}`}
                aria-valuemin={0}
                aria-valuemax={unit.max}
                aria-valuenow={text !== '' && !invalid ? Number(text) : undefined}
                aria-invalid={invalid || undefined}
                disabled={disabled}
                className="min-w-0 px-2 text-center tabular-nums"
                onFocus={(event) => event.currentTarget.select()}
                onChange={(event) => {
                  const next = event.target.value;
                  if (/^\d*$/.test(next)) {
                    updatePart(index, index === 3 && next !== '' ? next.padStart(3, '0') : next);
                  }
                }}
                onBlur={() => {
                  if (text !== '' && !invalid) updatePart(index, text.padStart(unit.width, '0'));
                }}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
                    event.preventDefault();
                    const direction = event.key === 'ArrowUp' ? 1 : -1;
                    const next = text === ''
                      ? (direction > 0 ? 0 : unit.max)
                      : ((Number(text) + direction + unit.max + 1) % (unit.max + 1));
                    updatePart(index, String(next).padStart(unit.width, '0'));
                  } else if (event.key === 'Home' || event.key === 'End') {
                    event.preventDefault();
                    updatePart(index, String(event.key === 'Home' ? 0 : unit.max).padStart(unit.width, '0'));
                  }
                }}
              />
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
