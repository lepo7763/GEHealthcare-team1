import { useState } from 'react';
import { format } from 'date-fns';
import { CalendarIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { TimeFields } from './TimeFields';
import { normalizeTime } from '@/lib/time';

export function DateTimePicker({ id, label, value, onChange, disabled = false, describedBy }) {
  const [isOpen, setIsOpen] = useState(false);
  const time = normalizeTime(value.time);
  const dateLabel = value.date ? format(value.date, 'MMM d, yyyy') : '';
  const selectionLabel = value.date
    ? `${dateLabel}${time ? ` · ${time}` : ' · Set time'}`
    : 'Pick a date and time';

  return (
    <div className="field" role="group" aria-labelledby={`${id}-label`}>
      <span id={`${id}-label`}>{label} date and time</span>
      <div className="date-time-picker-controls grid min-w-0 gap-2">
        <label className="sr-only" htmlFor={`${id}-date`}>{label} date and time</label>
        <Popover open={isOpen && !disabled} onOpenChange={(open) => setIsOpen(open && !disabled)}>
          <PopoverTrigger asChild>
            <Button
              id={`${id}-date`}
              type="button"
              variant="outline"
              className="h-[42px] w-full min-w-0 justify-start text-left font-normal data-[empty=true]:text-muted-foreground"
              data-empty={!value.date}
              disabled={disabled}
              aria-describedby={describedBy}
              aria-label={`${label} date and time, ${selectionLabel}`}
            >
              <CalendarIcon aria-hidden="true" />
              <span className="truncate">{selectionLabel}</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent
            className="w-[320px] max-w-[calc(100vw-24px)] p-0"
            align="start"
            collisionPadding={12}
            aria-labelledby={`${id}-popover-title`}
          >
            <div className="border-b border-border p-3">
              <div id={`${id}-popover-title`} className="text-sm font-semibold">{label} date and time</div>
              <div className="mt-1 text-xs text-muted-foreground">Use the log service's local time.</div>
            </div>
            <div className="flex justify-center">
              <Calendar
                mode="single"
                selected={value.date}
                defaultMonth={value.date}
                captionLayout="dropdown"
                onSelect={(date) => onChange({ ...value, date })}
                disabled={disabled}
                required
                autoFocus
              />
            </div>
            <div className="border-t border-border p-3">
              <TimeFields
                id={`${id}-time`}
                label={label}
                value={value.time}
                onChange={(nextTime) => onChange({ ...value, time: nextTime })}
                disabled={disabled}
              />
              <div className="mt-3 flex items-center justify-between gap-3">
                <span className="text-xs text-muted-foreground">24-hour time</span>
                <Button
                  type="button"
                  size="sm"
                  disabled={disabled || !value.date || !time}
                  onClick={() => {
                    onChange({ ...value, time });
                    setIsOpen(false);
                  }}
                >
                  Done
                </Button>
              </div>
            </div>
          </PopoverContent>
        </Popover>
      </div>
    </div>
  );
}
