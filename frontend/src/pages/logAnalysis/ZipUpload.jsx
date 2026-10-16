import { useRef, useState } from 'react';

// File picker (click or drag and drop) plus a submit button, shared by the
// Log Analysis and Privacy Scan pages. The parent decides what to do with the file.
const ZipUpload = ({ buttonLabel, busyLabel, isBusy, onSubmit, onFileChange }) => {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);

  const chooseFile = (picked) => {
    if (!picked) return;
    setFile(picked);
    onFileChange?.(picked);
  };

  return (
    <>
      <button
        type="button"
        className={`analysis-drop ${isDragging ? 'dragging' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          chooseFile(e.dataTransfer.files[0]);
        }}
      >
        <strong>Choose a ZIP</strong> or drag it here
        <span className="check-detail">
          {file ? `${file.name} (${(file.size / 1024).toFixed(1)} KB)` : 'No file selected'}
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".zip,application/zip"
        hidden
        onChange={(e) => chooseFile(e.target.files[0])}
      />

      <div className="action-row" style={{ marginTop: 'var(--eds-spacing-md)' }}>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => onSubmit(file)}
          disabled={!file || isBusy}
          aria-busy={isBusy}
        >
          {isBusy ? busyLabel : buttonLabel}
        </button>
      </div>
    </>
  );
};

export default ZipUpload;
