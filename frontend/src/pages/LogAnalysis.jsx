import { useState } from 'react';
import './pages.css';

import AnalysisReport from './logAnalysis/AnalysisReport';
import ZipUpload from './logAnalysis/ZipUpload';
import { analyzeZip } from './logAnalysis/analyzeZip';

// Upload any log zip (e.g. one downloaded earlier from Diagnostics) and see the analysis.
// Works without a cluster connection, since the analysis only reads the uploaded file.
const LogAnalysis = () => {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState('');
  const [report, setReport] = useState(null);

  const runAnalysis = async (file) => {
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

        <ZipUpload
          buttonLabel="Analyze"
          busyLabel="Analyzing…"
          isBusy={isAnalyzing}
          onSubmit={runAnalysis}
          onFileChange={() => { setError(''); setReport(null); }}
        />

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
