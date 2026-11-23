import { DateTimePicker } from '../../components/DateTimePicker';

const CmsSettings = ({ value, onChange, issue }) => {
    const set = (patch) => onChange({ ...value, ...patch });

    return (
        <div
            className="log-export-fields log-export-form"
            aria-describedby="cms-time-hint"
        >
            <div className="log-export-grid">
                <DateTimePicker
                    id="cms-start"
                    label="Start (UTC)"
                    value={value.start}
                    onChange={(start) => set({ start })}
                    describedBy="cms-time-hint"
                    timeHint="Enter the start date and time in UTC."
                />

                <DateTimePicker
                    id="cms-end"
                    label="End (UTC)"
                    value={value.end}
                    onChange={(end) => set({ end })}
                    describedBy="cms-time-hint"
                    timeHint="Enter the end date and time in UTC."
                />
            </div>

            <p id="cms-time-hint" className="log-export-hint">
                Select a UTC time range for the CMS snapshot.
                The end time must be after the start time.
            </p>

            <p className="log-export-hint">
                CMS generates a snapshot archive for the selected period.
                The archive will be included in the diagnostic ZIP.
            </p>

            {issue && (
                <small className="field-error" role="status">
                    {issue}
                </small>
            )}
        </div>
    );
};

export default CmsSettings;