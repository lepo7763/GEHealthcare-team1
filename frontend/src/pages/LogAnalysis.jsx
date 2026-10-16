import { useRef, useState } from 'react';
import './pages.css';

import AnalysisReport from './logAnalysis/AnalysisReport';
import { analyzeZip } from './logAnalysis/analyzeZip';

// Upload any log zip (e.g. one downloaded earlier from Diagnostics) and see the analysis.
// Works without a cluster connection, since the analysis only reads the uploaded file.
const LogAnalysis = () => {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState('');
  const [report, setReport] = useState(null);

  const chooseFile = (picked) => {
    if (!picked) return;
    setFile(picked);
    setError('');
    setReport(null);
  };

  const runAnalysis = async () => {
    setIsAnalyzing(true);
    setError('');
    setReport(null);
    try {
      setReport(await analyzeZip(file, file.name));
    } catch (err) {
      setError(err.message);
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="page-stack">
      <section className="page-hero">
        <div>
          <span className="page-eyebrow">Diagnostic Artifacts</span>
          <h2 className="page-title">Log Analysis</h2>
          <p className="page-subtitle">
            Upload a log package to see which containers need attention first.
          </p>
        </div>
      </section>

      <section className="card" aria-labelledby="upload-title">
        <h3 id="upload-title" className="card-title">Log package</h3>
        <p className="card-subtitle">The ZIP downloaded from the Diagnostics collect step.</p>

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
            onClick={runAnalysis}
            disabled={!file || isAnalyzing}
            aria-busy={isAnalyzing}
          >
            {isAnalyzing ? 'Analyzing…' : 'Analyze'}
          </button>
        </div>

        {error && (
          <div className="alert alert-error" role="alert" style={{ marginTop: 'var(--eds-spacing-md)' }}>
            <strong>Analysis failed</strong>
            <span>{error}</span>
          </div>
        )}
      </section>

      {report && <AnalysisReport report={report} />}
    </div>
  );
};

export default LogAnalysis;
