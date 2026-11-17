import CoreDumpSettings from './CoreDumpSettings';

const IDLE_PREVIEW = { status: 'idle', data: null, error: '' };

// Adapts the shared tool-dialog contract ({ value, onChange, context }) to the
// Core Dumps settings panel. The node preview lives in the Diagnostics page so
// the Review step can reuse it; it arrives through `context`.
const CoreDumpParamsForm = ({ value, onChange, context = {} }) => {
  const set = (patch) => onChange({ ...value, ...patch });
  return (
    <CoreDumpSettings
      sinceHours={value.sinceHours}
      setSinceHours={(sinceHours) => set({ sinceHours })}
      processes={value.processes}
      setProcesses={(next) =>
        set({ processes: typeof next === 'function' ? next(value.processes) : next })
      }
      maxMb={value.maxMb}
      setMaxMb={(maxMb) => set({ maxMb })}
      preview={context.corePreview || IDLE_PREVIEW}
      onRefresh={context.onRefreshCorePreview || (() => {})}
    />
  );
};

export default CoreDumpParamsForm;
