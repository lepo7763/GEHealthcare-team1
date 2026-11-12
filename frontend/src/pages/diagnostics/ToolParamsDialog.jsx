import { useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import AxoneLogParamsForm from './AxoneLogParams';
import UmfRtiParamsForm from './UmfRtiParams';
import { getToolIssue } from './toolParams';

const FORMS = {
  'umf-rti': UmfRtiParamsForm,
  'axone-logs': AxoneLogParamsForm,
};

// Edits a draft copy of one tool's parameters; Save commits it, Cancel/Escape
// discards it. Saving an incomplete draft is allowed so progress isn't lost; the
// Configure step blocks continuing until required parameters are complete.
const ToolParamsDialog = ({ tool, params, onSave, onClose }) => {
  const [draft, setDraft] = useState(params);
  const Form = FORMS[tool.id];
  const issue = getToolIssue(tool.id, draft);

  const handleSubmit = (event) => {
    event.preventDefault();
    onSave(draft);
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle>{tool.name} parameters</DialogTitle>
        <DialogDescription>{tool.description}</DialogDescription>

        <form onSubmit={handleSubmit} noValidate>
          <div className="dialog-body">
            <Form value={draft} onChange={setDraft} />
          </div>

          <p
            className="dialog-issue"
            role="status"
            style={{ visibility: issue ? 'visible' : 'hidden' }}
          >
            Still needed: {issue || 'nothing'}
          </p>

          <div className="action-row dialog-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Save
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default ToolParamsDialog;
