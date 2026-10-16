import { useState } from 'react';
import './pages.css';

import Step1SelectEnvironment from './diagnostic/Step1SelectEnvironment';
import Step2DiscoverConfigure from './diagnostic/Step2DiscoverConfigure';
import Step3DeployTools from './diagnostic/Step3DeployTools';
import Step4CollectDiagnostics from './diagnostic/Step4CollectDiagnostics';
import Step5AnalyzePackage from './diagnostic/Step5AnalyzePackage';
import Step6ReviewCleanup from './diagnostic/Step6ReviewCleanup';

// # GEHealthcare-team1
// The color requirements:
// - "Compassion Purple" (Pantone 267 C, RGB 96/34/166, CMYK 81/99/0/0)
// - "White" (RGB 255/255/255, CMYK 0/0/0/0)
// - "Cool Gray" (Pantone Cool Gray 1 C, RGB 228/228/228, CMYK 0/0/0/10)
// Font requirement: "Inter" system-ui, Avenir, Helvetica, Arial, sans-serif

const STEPS = [
  {
    id: 1,
    title: 'Select Environment',
    label: 'Select Environment',
    desc: 'Choose a saved environment or enter the IP/hostname and credentials. Test the connection.',
  },
  {
    id: 2,
    title: 'Discover & Configure',
    label: 'Discover & Configure',
    desc: 'Discover the viewer, hub, backend services, and system nodes. Select tools and validate settings.',
  },
  {
    id: 3,
    title: 'Review and Deploy',
    label: 'Review and Deploy',
    desc: 'Review the configuration and deploy the selected diagnostic tools.',
  },
  {
    id: 4,
    title: 'Collect Diagnostics',
    label: 'Collect Diagnostics',
    desc: 'Run tools, collect logs and system data, and monitor progress.',
  },
  {
    id: 5,
    title: 'Analyze & Package',
    label: 'Analyze & Package',
    desc: 'Process collected data and generate the diagnostic package.',
  },
  {
    id: 6,
    title: 'Review & Cleanup',
    label: 'Review & Cleanup',
    desc: 'Review and download results, then clean up deployed resources.',
  },
];

const Diagnostic = ({ onNavigate, initialStep = 1 }) => {
  const [currentStep, setCurrentStep] = useState(initialStep);
  const [sessionData, setSessionData] = useState({
    envId: 'env-portrait-central',
    host: '192.168.0.4',
    port: '22',
    account: 'diagnostic-ops',
    context: 'portrait-mobile-prod',
    tools: ['netshoot', 'umf_rti', 'tshark'],
    captureDuration: '15',
    maxLogSize: '100',
    cpuLimit: '0.5',
    memoryLimit: '512',
    deploymentState: 'idle',
    collectionState: 'idle',
  });

  const updateSessionData = (patch) => {
    setSessionData((prev) => ({ ...prev, ...patch }));
  };

  const handleRestart = () => {
    setSessionData({
      envId: 'env-portrait-central',
      host: '192.168.0.4',
      port: '22',
      account: 'diagnostic-ops',
      context: 'portrait-mobile-prod',
      tools: ['netshoot', 'umf_rti', 'tshark'],
      captureDuration: '15',
      maxLogSize: '100',
      cpuLimit: '0.5',
      memoryLimit: '512',
      deploymentState: 'idle',
      collectionState: 'idle',
    });
    setCurrentStep(1);
  };

  const renderCurrentStep = () => {
    switch (currentStep) {
      case 1:
        return (
          <Step1SelectEnvironment
            sessionData={sessionData}
            updateSessionData={updateSessionData}
            onNext={() => setCurrentStep(2)}
          />
        );
      case 2:
        return (
          <Step2DiscoverConfigure
            sessionData={sessionData}
            updateSessionData={updateSessionData}
            onNext={() => setCurrentStep(3)}
            onBack={() => setCurrentStep(1)}
          />
        );
      case 3:
        return (
          <Step3DeployTools
            sessionData={sessionData}
            updateSessionData={updateSessionData}
            onNext={() => setCurrentStep(4)}
            onBackToEnvironment={() => setCurrentStep(1)}
            onBackToToolSelection={() => setCurrentStep(2)}
          />
        );
      case 4:
        return (
          <Step4CollectDiagnostics
            sessionData={sessionData}
            updateSessionData={updateSessionData}
            onNext={() => setCurrentStep(5)}
            onBack={() => setCurrentStep(3)}
          />
        );
      case 5:
        return (
          <Step5AnalyzePackage
            sessionData={sessionData}
            updateSessionData={updateSessionData}
            onNext={() => setCurrentStep(6)}
            onBack={() => setCurrentStep(4)}
          />
        );
      case 6:
        return (
          <Step6ReviewCleanup
            sessionData={sessionData}
            onRestart={handleRestart}
            onNavigateOverview={() => onNavigate?.('overview')}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="page-stack">
      {/* PAGE HERO */}
      <section className="page-hero">
        <div>
          <span className="page-eyebrow">
            Diagnostic Session · Step {currentStep} of 6
          </span>
          <h2 className="page-title">{STEPS[currentStep - 1]?.title}</h2>
          <p className="page-subtitle">
            {STEPS[currentStep - 1]?.desc}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span className="badge badge-purple">
            Host: {sessionData.host}
          </span>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onNavigate?.('overview')}
            style={{ height: '32px', padding: '0 12px', fontSize: 'var(--eds-font-size-xs)' }}
          >
            Exit Session
          </button>
        </div>
      </section>

      {/* 6-STEP CONTINUOUS WORKFLOW STEPPER */}
      <nav aria-label="Diagnostic Workflow Steps" className="diagnostic-stepper-wrap">
        <ol className="stepper diagnostic-stepper">
          {STEPS.map((s) => {
            const isActive = currentStep === s.id;
            const isCompleted = currentStep > s.id;
            return (
              <li
                key={s.id}
                className={`step ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}
                onClick={() => setCurrentStep(s.id)}
                role="button"
                tabIndex={0}
                style={{ cursor: 'pointer' }}
                title={`Go to Step ${s.id}: ${s.label}`}
              >
                <span className="step-num">
                  {isCompleted ? '✓' : s.id}
                </span>
                <span className="step-label-group">
                  <span className="step-label">{s.label}</span>
                </span>
              </li>
            );
          })}
        </ol>
      </nav>

      {/* ACTIVE STEP BODY */}
      <div className="diagnostic-step-container">
        {renderCurrentStep()}
      </div>
    </div>
  );
};

export default Diagnostic;
