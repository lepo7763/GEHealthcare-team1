import { useState } from 'react';
import { SERVICES } from './constants';
import { getToolIssue, isConfigurable } from './toolParams';
import ToolParamsDialog from './ToolParamsDialog';

const formatList = (names) =>
  names.length <= 1
    ? names.join('')
    : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;

const Step2Configure = ({
  selected,
  onToggleService,
  toolParams,
  onToolParamsChange,
  initialEditingId = null,
  onBack,
  onContinue,
}) => {
  // Review's per-tool Edit link returns here with that tool's dialog open.
  const [editingId, setEditingId] = useState(initialEditingId);
  const [attempted, setAttempted] = useState(false);

  const incomplete = SERVICES.filter(
    (service) => selected.includes(service.id) && getToolIssue(service.id, toolParams[service.id]),
  );
  const editingTool = SERVICES.find((service) => service.id === editingId);

  const handleContinue = () => {
    if (incomplete.length > 0) {
      setAttempted(true);
      return;
    }
    onContinue();
  };

  return (
    <section className="section-narrow">
      <div className="card">
        <h3 className="card-title">Collection tools</h3>
        <p className="card-subtitle">
          Select the tools to include in this diagnostic session. Use Edit to set a tool's
          parameters.
        </p>

        <ul className="service-list">
          {SERVICES.map((service) => {
            const isSelected = selected.includes(service.id);
            const configurable = isConfigurable(service.id);
            const needsEdit = incomplete.includes(service);
            const cardClass = [
              'service-card',
              isSelected && 'selected',
              needsEdit && attempted && 'needs-edit',
            ]
              .filter(Boolean)
              .join(' ');
            return (
              <li key={service.id}>
                <div className={cardClass}>
                  <button
                    type="button"
                    className="service-option"
                    aria-pressed={isSelected}
                    onClick={() => onToggleService(service.id)}
                  >
                    <div>
                      <div className="check-title">{service.name}</div>
                      <div className="check-detail">{service.description}</div>
                    </div>
                    <span className="service-check" aria-hidden="true">
                      {isSelected ? '✓' : ''}
                    </span>
                  </button>

                  {configurable && (
                    <div className="service-card-footer">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setEditingId(service.id)}
                        aria-label={`Edit ${service.name} parameters`}
                      >
                        Edit
                      </button>
                      {needsEdit && (
                        <span className="service-needs-edit">Needs editing</span>
                      )}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>

        {attempted && incomplete.length > 0 && (
          <div className="alert alert-warning configure-alert" role="alert">
            <strong>
              {formatList(incomplete.map((service) => service.name))}{' '}
              {incomplete.length === 1 ? 'requires' : 'require'} completion
            </strong>
            <span>Click Edit to fill in the required parameters before continuing.</span>
          </div>
        )}

        <div className="action-row">
          <button className="btn btn-secondary" onClick={onBack}>
            Back
          </button>
          <button
            className="btn btn-primary"
            onClick={handleContinue}
            disabled={selected.length === 0}
          >
            Continue to review
          </button>
        </div>

        {/* Always rendered (visibility-toggled) so showing the hint doesn't
            change the page height and jolt the layout/scrollbar. */}
        <p
          className="future-note future-note-error"
          style={{ visibility: selected.length === 0 ? 'visible' : 'hidden' }}
        >
          Select at least one tool to continue.
        </p>
      </div>

      {editingTool && (
        <ToolParamsDialog
          tool={editingTool}
          params={toolParams[editingTool.id]}
          onSave={(params) => {
            onToolParamsChange(editingTool.id, params);
            setEditingId(null);
          }}
          onClose={() => setEditingId(null)}
        />
      )}
    </section>
  );
};

export default Step2Configure;
