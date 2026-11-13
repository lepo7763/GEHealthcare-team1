import { useEffect, useState } from 'react';
import {
  DEFAULT_DOWNLOAD_PATH,
  getAlwaysAskLocation,
  getDownloadPath,
  setAlwaysAskLocation,
  setDownloadPath,
} from '../lib/settings';
import './pages.css';

const PRESET_PATHS = [
  { label: 'Downloads (Default)', value: 'Downloads' },
  { label: 'Desktop', value: 'Desktop' },
  { label: 'Documents', value: 'Documents' },
  { label: 'C:\\GEHC_Diagnostics', value: 'C:\\GEHC_Diagnostics' },
];

const Settings = ({ onClose }) => {
  const [path, setPath] = useState(getDownloadPath);
  const [alwaysAsk, setAlwaysAsk] = useState(getAlwaysAskLocation);
  const [savedMessage, setSavedMessage] = useState('');
  const [pickerNotice, setPickerNotice] = useState('');

  const hasDirectoryPicker = typeof window !== 'undefined' && typeof window.showDirectoryPicker === 'function';

  // Close on Escape key press
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && onClose) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleChooseFolder = async () => {
    setPickerNotice('');
    if (hasDirectoryPicker) {
      try {
        const dirHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
        if (dirHandle?.name) {
          setPath(dirHandle.name);
          setSavedMessage(`Selected folder: "${dirHandle.name}"`);
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.warn('Folder picker error:', err);
          setPickerNotice('Could not open folder picker. Enter the path manually or choose a preset.');
        }
      }
    } else {
      setPickerNotice(
        'Direct folder browsing requires a Chromium browser (Chrome/Edge). You can type the path or click a preset below.'
      );
    }
  };

  const handleSave = (e) => {
    e?.preventDefault();
    const saved = setDownloadPath(path);
    setAlwaysAskLocation(alwaysAsk);
    setPath(saved);
    setSavedMessage('Settings saved successfully.');
    setTimeout(() => {
      setSavedMessage('');
      if (onClose) onClose();
    }, 700);
  };

  const handleSelectPreset = (presetValue) => {
    setPath(presetValue);
    setSavedMessage('');
    setPickerNotice('');
  };

  return (
    <div
      className="settings-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-dialog-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && onClose) onClose();
      }}
    >
      <div className="settings-floating-card">
        {/* HEADER */}
        <div className="settings-card-header">
          <div className="settings-card-title-group">
            <div className="settings-icon-circle" aria-hidden="true">
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
              </svg>
            </div>
            <div>
              <h2 id="settings-dialog-title" className="settings-card-title">
                Workstation Settings
              </h2>
              <p className="settings-card-subtitle">
                Configure diagnostic export destination and storage options
              </p>
            </div>
          </div>
          {onClose && (
            <button
              type="button"
              className="settings-card-close-btn"
              onClick={onClose}
              title="Close settings"
              aria-label="Close settings"
            >
              ✕
            </button>
          )}
        </div>

        {/* BODY */}
        <form onSubmit={handleSave}>
          <div className="settings-card-body">
            {/* DOWNLOAD PATH SECTION */}
            <div>
              <h4 className="settings-section-title">Diagnostic Exports Destination</h4>
              <label className="field">
                <span>Download folder</span>
                <div className="settings-input-group">
                  <input
                    type="text"
                    value={path}
                    placeholder="Downloads"
                    onChange={(e) => {
                      setPath(e.target.value);
                      setSavedMessage('');
                    }}
                    autoFocus
                  />
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleChooseFolder}
                    title="Open system directory picker to choose a folder"
                  >
                    Choose folder…
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => handleSelectPreset(DEFAULT_DOWNLOAD_PATH)}
                    title="Reset to default Downloads folder"
                  >
                    Default
                  </button>
                </div>
              </label>

              {/* QUICK PRESET CHIPS */}
              <div style={{ marginTop: '0.5rem' }}>
                <span
                  style={{
                    fontSize: 'var(--eds-font-size-xs)',
                    color: 'var(--eds-color-gray-500)',
                    marginRight: '6px',
                  }}
                >
                  Quick presets:
                </span>
                <div className="settings-chip-group" style={{ display: 'inline-flex' }}>
                  {PRESET_PATHS.map((preset) => (
                    <button
                      key={preset.value}
                      type="button"
                      className={`settings-chip-btn ${path === preset.value ? 'active' : ''}`}
                      onClick={() => handleSelectPreset(preset.value)}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>

              {pickerNotice && (
                <div className="alert alert-warning" style={{ marginTop: '0.75rem' }}>
                  <span>{pickerNotice}</span>
                </div>
              )}

              {/* ALWAYS ASK LOCATION OPTION */}
              <label className="settings-checkbox-row">
                <input
                  type="checkbox"
                  checked={alwaysAsk}
                  onChange={(e) => setAlwaysAsk(e.target.checked)}
                />
                <div className="settings-checkbox-text">
                  <span className="settings-checkbox-label">
                    Prompt for save destination on every export (Save As…)
                  </span>
                  <span className="settings-checkbox-desc">
                    When checked, exports open the native file dialog so you can choose a folder for each download.
                  </span>
                </div>
              </label>
            </div>

            {/* CLINICAL COMPLIANCE PREFERENCES */}
            <div>
              <h4 className="settings-section-title">Security &amp; Workstation</h4>
              <ul className="check-list">
                <li>
                  <div>
                    <div className="check-title">Session Inactivity Lock</div>
                    <div className="check-detail">
                      5 minutes timeout (Active collections continue in background)
                    </div>
                  </div>
                  <span className="badge badge-success">Enforced</span>
                </li>
                <li>
                  <div>
                    <div className="check-title">Cluster Security Profile</div>
                    <div className="check-detail">
                      TLS 1.3 · Port 6443 · Dedicated Developer Namespaces
                    </div>
                  </div>
                  <span className="badge badge-purple">Standard</span>
                </li>
              </ul>
            </div>

            {savedMessage && (
              <div className="alert alert-success" role="status">
                <strong>Success</strong>
                <span>{savedMessage}</span>
              </div>
            )}
          </div>

          {/* FOOTER */}
          <div className="settings-card-footer">
            {onClose && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
              >
                Cancel
              </button>
            )}
            <button type="submit" className="btn btn-primary">
              Save changes
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Settings;
