import { useEffect, useRef, useState } from 'react';
import './pages.css';

import { STEPS, STEP_INFO, SERVICES, RUNNING_STATUSES, parseFilename } from './diagnostics/constants';
import Step1Connect from './diagnostics/Step1Connect';
import Step2Configure from './diagnostics/Step2Configure';
import Step3Review from './diagnostics/Step3Review';
import Step4Collect from './diagnostics/Step4Collect';

// # GEHealthcare-team1
// The color requrements:
// - "Compassion Purple" (Pantone 267 C, RGB 96/34/166, CMYK 81/99/0/0)
// - "White" (RGB 255/255/255, CMYK 0/0/0/0)
// - "Cool Gray" (Pantone Cool Gray 1 C, RGB 228/228/228, CMYK 0/0/0/10)
// Font requirement: "Inter" system-ui, Avenir, Helvetica, Arial, sans-serif

const Diagnostics = () => {
  const [host, setHost] = useState('192.168.0.3');
  const [step, setStep] = useState(1);
  // idle -> checking -> done
  const [phase, setPhase] = useState('idle');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(['container-logs']);

  // Collection (Step 4) state.
  const [collect, setCollect] = useState(null);
  const [collectError, setCollectError] = useState('');
  const [download, setDownload] = useState(null);
  const pollRef = useRef(null);
  const abortRef = useRef(null);
  const downloadUrlRef = useRef(null);

  const isChecking = phase === 'checking';
  const info = STEP_INFO[step] || STEP_INFO[1];

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const pollProgress = () => {
    fetch('/api/logs/progress')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setCollect(data);
      })
      .catch(() => {
        /* keep polling */
      });
  };

  const startPolling = () => {
    stopPolling();
    pollRef.current = setInterval(pollProgress, 400);
  };

  const startCollection = async () => {
    setCollectError('');
    setDownload(null);
    if (downloadUrlRef.current) {
      URL.revokeObjectURL(downloadUrlRef.current);
      downloadUrlRef.current = null;
    }

    // Attach to a run that's already in progress instead of starting a second.
    let current = null;
    try {
      const res = await fetch('/api/logs/progress');
      if (res.ok) current = await res.json();
    } catch {
      /* ignore — fall through and try to start */
    }
    if (current) setCollect(current);
    if (current && RUNNING_STATUSES.includes(current.status)) {
      startPolling();
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;

    fetch('/api/logs/zip', { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) {
          let detail = `Collection failed (${res.status}).`;
          try {
            const body = await res.json();
            if (body?.detail) detail = body.detail;
          } catch {
            /* non-JSON error body */
          }
          throw new Error(detail);
        }
        const filename =
          parseFilename(res.headers.get('Content-Disposition')) || 'k8s_cluster_logs.zip';
        const blob = await res.blob();
        return { blob, filename };
      })
      .then(({ blob, filename }) => {
        stopPolling();
        pollProgress();
        const url = URL.createObjectURL(blob);
        downloadUrlRef.current = url;
        setDownload({ url, filename });
      })
      .catch((e) => {
        if (e.name === 'AbortError') return;
        stopPolling();
        setCollectError(e.message || 'Collection failed.');
      });

    startPolling();
  };

  // Stop polling and abort any in-flight request if the page is left.
  useEffect(() => {
    return () => {
      stopPolling();
      if (abortRef.current) abortRef.current.abort();
      if (downloadUrlRef.current) URL.revokeObjectURL(downloadUrlRef.current);
    };
  }, []);

  const toggleService = (id) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((serviceId) => serviceId !== id) : [...prev, id],
    );
  };

  const selectedServices = SERVICES.filter((service) => selected.includes(service.id));

  const resetCheck = () => {
    setPhase('idle');
    setResult(null);
    setError('');
  };

  const handleCheck = async () => {
    setPhase('checking');
    setResult(null);
    setError('');

    try {
      const response = await fetch('/api/environments/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: host.trim() }),
      });

      if (!response.ok) {
        let detail = `Request failed (${response.status}).`;
        try {
          const body = await response.json();
          if (body?.detail) {
            detail =
              typeof body.detail === 'string'
                ? body.detail
                : body.detail.map?.((d) => d.msg).join(', ') || JSON.stringify(body.detail);
          }
        } catch {
          // Non-JSON error body; keep the generic message.
        }
        throw new Error(detail);
      }

      const data = await response.json();
      setResult(data);
      setPhase('done');
      if (data.ok) {
        setStep(2);
      }
    } catch (e) {
      setError(e.message || 'Could not reach the analysis tool backend.');
      setPhase('done');
    }
  };

  const handleBackToConnect = () => {
    setStep(1);
    resetCheck();
  };

  return (
    <div className="page-stack">
      <section className="page-header-compact">
        <h2 className="page-title-sm">{info.title}</h2>
        <p className="page-subtitle-sm">{info.subtitle}</p>
      </section>

      <ol className="stepper">
        {STEPS.map((label, i) => (
          <li key={label} className={i === step - 1 ? 'step active' : 'step'}>
            <span className="step-num">{i + 1}</span>
            {label}
          </li>
        ))}
      </ol>

      {step === 1 && (
        <Step1Connect
          host={host}
          setHost={setHost}
          phase={phase}
          result={result}
          error={error}
          isChecking={isChecking}
          onCheck={handleCheck}
        />
      )}

      {step === 2 && (
        <Step2Configure
          selected={selected}
          onToggleService={toggleService}
          onBack={handleBackToConnect}
          onContinue={() => setStep(3)}
        />
      )}

      {step === 3 && (
        <Step3Review
          result={result}
          selectedServices={selectedServices}
          onEditConnection={() => setStep(1)}
          onEditServices={() => setStep(2)}
          onBack={() => setStep(2)}
          onStart={() => {
            setStep(4);
            startCollection();
          }}
        />
      )}

      {step === 4 && (
        <Step4Collect
          collect={collect}
          collectError={collectError}
          download={download}
          onBack={() => setStep(3)}
        />
      )}
    </div>
  );
};

export default Diagnostics;
