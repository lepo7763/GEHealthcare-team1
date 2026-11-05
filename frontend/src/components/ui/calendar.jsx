import { useEffect, useRef } from 'react';
import { ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon } from 'lucide-react';
import { DayPicker, getDefaultClassNames } from 'react-day-picker';
import { cn } from '@/lib/utils';
import { Button } from './button';
import { buttonVariants } from './button-variants';

// JavaScript adaptation of shadcn/ui's New York Calendar.
function Calendar({ className, classNames, showOutsideDays = true, captionLayout = 'label', buttonVariant = 'ghost', formatters, components, ...props }) {
  const defaults = getDefaultClassNames();
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn('group/calendar bg-background p-3 [--cell-size:--spacing(8)] [[data-slot=popover-content]_&]:bg-transparent', className)}
      captionLayout={captionLayout}
      formatters={{ formatMonthDropdown: (date) => date.toLocaleString('default', { month: 'short' }), ...formatters }}
      classNames={{
        root: cn('w-fit', defaults.root),
        months: cn('relative flex flex-col gap-4 md:flex-row', defaults.months),
        month: cn('flex w-full flex-col gap-4', defaults.month),
        nav: cn('absolute inset-x-0 top-0 flex w-full items-center justify-between gap-1', defaults.nav),
        button_previous: cn(buttonVariants({ variant: buttonVariant }), 'size-(--cell-size) p-0 select-none aria-disabled:opacity-50', defaults.button_previous),
        button_next: cn(buttonVariants({ variant: buttonVariant }), 'size-(--cell-size) p-0 select-none aria-disabled:opacity-50', defaults.button_next),
        month_caption: cn('flex h-(--cell-size) w-full items-center justify-center px-(--cell-size)', defaults.month_caption),
        dropdowns: cn('flex h-(--cell-size) w-full items-center justify-center gap-1.5 text-sm font-medium', defaults.dropdowns),
        dropdown_root: cn('relative rounded-md border border-input shadow-xs has-focus:border-ring has-focus:ring-[3px] has-focus:ring-ring/50', defaults.dropdown_root),
        dropdown: cn('absolute inset-0 bg-popover opacity-0', defaults.dropdown),
        caption_label: cn('font-medium select-none', captionLayout === 'label' ? 'text-sm' : 'flex h-8 items-center gap-1 rounded-md pr-1 pl-2 text-sm [&>svg]:size-3.5 [&>svg]:text-muted-foreground', defaults.caption_label),
        month_grid: cn('w-full border-collapse', defaults.month_grid),
        weekdays: cn('flex', defaults.weekdays),
        weekday: cn('flex-1 rounded-md text-[0.8rem] font-normal text-muted-foreground select-none', defaults.weekday),
        week: cn('mt-2 flex w-full', defaults.week),
        week_number_header: cn('w-(--cell-size) select-none', defaults.week_number_header),
        week_number: cn('text-[0.8rem] text-muted-foreground select-none', defaults.week_number),
        day: cn('group/day relative aspect-square h-full w-full p-0 text-center select-none [&:last-child[data-selected=true]_button]:rounded-r-md', props.showWeekNumber ? '[&:nth-child(2)[data-selected=true]_button]:rounded-l-md' : '[&:first-child[data-selected=true]_button]:rounded-l-md', defaults.day),
        range_start: cn('rounded-l-md bg-accent', defaults.range_start),
        range_middle: cn('rounded-none', defaults.range_middle),
        range_end: cn('rounded-r-md bg-accent', defaults.range_end),
        today: cn('rounded-md bg-accent text-accent-foreground data-[selected=true]:rounded-none', defaults.today),
        outside: cn('text-muted-foreground aria-selected:text-muted-foreground', defaults.outside),
        disabled: cn('text-muted-foreground opacity-50', defaults.disabled),
        hidden: cn('invisible', defaults.hidden),
        ...classNames,
      }}
      components={{
        Root: ({ className, rootRef, ...rootProps }) => <div data-slot="calendar" ref={rootRef} className={cn(className)} {...rootProps} />,
        Chevron: ({ className, orientation, ...chevronProps }) => {
          const Icon = orientation === 'left' ? ChevronLeftIcon : orientation === 'right' ? ChevronRightIcon : ChevronDownIcon;
          return <Icon className={cn('size-4', className)} aria-hidden="true" {...chevronProps} />;
        },
        DayButton: CalendarDayButton,
        WeekNumber: ({ children, ...weekProps }) => <td {...weekProps}><div className="flex size-(--cell-size) items-center justify-center text-center">{children}</div></td>,
        ...components,
      }}
      {...props}
    />
  );
}

function CalendarDayButton({ className, day, modifiers, ...props }) {
  const defaults = getDefaultClassNames();
  const ref = useRef(null);
  useEffect(() => {
    if (modifiers.focused) ref.current?.focus();
  }, [modifiers.focused]);

  return (
    <Button
      ref={ref}
      variant="ghost"
      size="icon"
      data-day={day.date.toLocaleDateString()}
      data-selected-single={modifiers.selected && !modifiers.range_start && !modifiers.range_end && !modifiers.range_middle}
      data-range-start={modifiers.range_start}
      data-range-end={modifiers.range_end}
      data-range-middle={modifiers.range_middle}
      className={cn(
        'flex aspect-square size-auto w-full min-w-(--cell-size) flex-col gap-1 leading-none font-normal group-data-[focused=true]/day:relative group-data-[focused=true]/day:z-10 group-data-[focused=true]/day:border-ring group-data-[focused=true]/day:ring-[3px] group-data-[focused=true]/day:ring-ring/50 data-[range-end=true]:rounded-md data-[range-end=true]:rounded-r-md data-[range-end=true]:bg-primary data-[range-end=true]:text-primary-foreground data-[range-middle=true]:rounded-none data-[range-middle=true]:bg-accent data-[range-middle=true]:text-accent-foreground data-[range-start=true]:rounded-md data-[range-start=true]:rounded-l-md data-[range-start=true]:bg-primary data-[range-start=true]:text-primary-foreground data-[selected-single=true]:bg-primary data-[selected-single=true]:text-primary-foreground [&>span]:text-xs [&>span]:opacity-70',
        defaults.day,
        className,
      )}
      {...props}
    />
  );
}

export { Calendar, CalendarDayButton };
