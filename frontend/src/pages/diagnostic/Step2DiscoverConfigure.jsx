import { useState } from 'react';
import '../pages.css';

// [PLACEHOLDER] Modular Tool Catalog.
// Designed with an extensible schema so additional diagnostic tools (e.g., eBPF/Sysdig, Node Exporter)
// can be added by registering a new descriptor without rewriting UI logic.
const TOOL_CATALOG = [
  {
    id: 'netshoot',
    name: 'Netshoot Network Toolkit',
    version: 'v0.12',
    image: 'nicolaka/netshoot:latest',
    imageType: 'Approved Specialized Exception',
    description: 'Ephemeral network diagnostics: DNS resolution, ICMP ping latency, route tracing, curl, socat.',
  },
  {
    id: 'umf_rti',
    name: 'UMF RTI',
    version: 'v2.4',
    image: 'gehc/umf-rti:2.4-ubuntu22',
    imageType: 'Ubuntu 22-based Standard',
    description: 'Real-time telemetry and DDS (Data Distribution Service) middleware topic observer.',
  },
  {
    id: 'tshark',
    name: 'Wireshark / tshark Packet Sniffer',
    version: 'v4.0',
    image: 'gehc/wireshark-tshark:4.0-ubuntu22',
    imageType: 'Ubuntu 22-based Standard',
    description: 'Deep packet capture (PCAP) and protocol dissection on mirror/promiscuous interface.',
  },
];

// [PLACEHOLDER] Discovered components from network discovery.
// In production, these are dynamically discovered via Kubernetes CoreV1Api and platform ARP/mDNS scan.
const DISCOVERED_TOPOLOGY = {
  networkSettings: {
    subnet: '192.168.0.0/24',
    gateway: '192.168.0.1',
    mtu: '1500 bytes',
    dns: '192.168.0.1',
    clockDrift: '+2.8s on Hub Self',
  },
  components: [
    { name: 'Viewer', type: 'Clinical Display', ip: '192.168.0.5', status: 'Reachable', latency: '1.2ms' },
    { name: 'Virtual Hub Host', type: 'App Server', ip: '192.168.0.4', status: 'Reachable', latency: '0.8ms' },
    { name: 'Virtual Hub Self', type: 'Gateway Process', ip: '192.168.0.100', status: 'Reachable', latency: '2.8s clock drift', warn: true },
    { name: 'MiniEdge P360', type: 'K3s Edge Compute', ip: '192.168.0.3', status: 'Reachable', latency: '1.5ms' },
    { name: 'Workstation', type: 'Field Client', ip: '192.168.0.6', status: 'Local Host', latency: '0.1ms' },
  ],
  services: [
    { name: 'monitor-api', namespace: 'iomt-hub', replicas: '2/2', status: 'Healthy' },
    { name: 'sidecar-proxy', namespace: 'iomt-hub', replicas: '2/2', status: 'Healthy' },
    { name: 'telemetry-broker', namespace: 'iomt-hub', replicas: '1/1', status: 'Healthy' },
    { name: 'auth-gateway', namespace: 'kube-system', replicas: '1/1', status: 'Healthy' },
    { name: 'influx-relay', namespace: 'monitoring', replicas: '1/1', status: 'Healthy' },
    { name: 'event-audit', namespace: 'security', replicas: '1/1', status: 'Healthy' },
  ],
  k8sNodes: [
    { name: 'miniedge-node-01', role: 'control-plane, worker', status: 'Ready', k8sVersion: 'v1.28.3+k3s1', cpuAlloc: '24%', memAlloc: '38%' },
    { name: 'hub-node-02', role: 'worker', status: 'Ready', k8sVersion: 'v1.28.3+k3s1', cpuAlloc: '18%', memAlloc: '42%' },
  ],
};

const Step2DiscoverConfigure = ({ sessionData, updateSessionData, onNext, onBack }) => {
  // Tool Selection
  const [selectedTools, setSelectedTools] = useState(sessionData.tools || ['netshoot', 'umf_rti', 'tshark']);

  // Global Resource & Safety Limits
  const [captureDuration, setCaptureDuration] = useState(sessionData.captureDuration || '15');
  const [maxLogSize, setMaxLogSize] = useState(sessionData.maxLogSize || '100');
  const [cpuLimit, setCpuLimit] = useState(sessionData.cpuLimit || '0.5');
  const [memoryLimit, setMemoryLimit] = useState(sessionData.memoryLimit || '512');

  // Field-Level Validation State
  const [fieldErrors, setFieldErrors] = useState({});
  const [validationBanner, setValidationBanner] = useState(null); // { type: 'success' | 'error', message: '' }

  const toggleTool = (toolId) => {
    if (selectedTools.includes(toolId)) {
      if (selectedTools.length === 1) {
        setFieldErrors({ tools: 'At least one diagnostic tool must remain selected.' });
        return;
      }
      setSelectedTools(selectedTools.filter((t) => t !== toolId));
    } else {
      setSelectedTools([...selectedTools, toolId]);
    }
    setFieldErrors({ ...fieldErrors, tools: null });
    setValidationBanner(null);
  };

  const validateAllConfigurations = () => {
    const errors = {};

    if (selectedTools.length === 0) {
      errors.tools = 'Please select at least one diagnostic tool to deploy.';
    }

    const duration = parseInt(captureDuration, 10);
    if (!captureDuration || isNaN(duration) || duration < 1 || duration > 120) {
      errors.captureDuration = 'Duration must be between 1 and 120 minutes.';
    }

    const logSize = parseInt(maxLogSize, 10);
    if (!maxLogSize || isNaN(logSize) || logSize < 10 || logSize > 2000) {
      errors.maxLogSize = 'Log output limit must be between 10 MB and 2000 MB.';
    }

    const cpu = parseFloat(cpuLimit);
    if (!cpuLimit || isNaN(cpu) || cpu < 0.1 || cpu > 2.0) {
      errors.cpuLimit = 'CPU limit must be between 0.1 and 2.0 cores per container.';
    }

    const mem = parseInt(memoryLimit, 10);
    if (!memoryLimit || isNaN(mem) || mem < 64 || mem > 2048) {
      errors.memoryLimit = 'Memory limit must be between 64 MiB and 2048 MiB.';
    }

    setFieldErrors(errors);
    return errors;
  };

  const handleValidateClick = () => {
    const errs = validateAllConfigurations();
    if (Object.keys(errs).length > 0) {
      setValidationBanner({
        type: 'error',
        message: 'Configuration has validation errors. Please correct the highlighted fields before proceeding.',
      });
    } else {
      setValidationBanner({
        type: 'success',
        message: 'All configuration values and resource quotas successfully validated against clinical safety policy.',
      });
    }
  };

  const handleProceed = () => {
    const errs = validateAllConfigurations();
    if (Object.keys(errs).length > 0) {
      setValidationBanner({
        type: 'error',
        message: 'Please resolve validation errors before continuing to deployment.',
      });
      return;
    }

    updateSessionData({
      tools: selectedTools,
      captureDuration,
      maxLogSize,
      cpuLimit,
      memoryLimit,
      discoveredTopology: DISCOVERED_TOPOLOGY,
    });
    onNext();
  };

  return (
    <div className="step-content-pane">
      <div className="card-header" style={{ marginBottom: 'var(--eds-spacing-md)' }}>
        <div>
          <h3 className="card-title">2. Discover and Configure</h3>
          <p className="card-subtitle">
            Inspect discovered Portrait Mobile components, select diagnostic analysis services, and review generated values.
          </p>
        </div>
        <span className="badge badge-purple">Step 2 of 6</span>
      </div>

      <div className="two-col" style={{ gap: 'var(--eds-spacing-lg)' }}>
        {/* LEFT COLUMN: TOOL SELECTION */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--eds-spacing-md)' }}>
          {/* TOOL SELECTION */}
          <div className="card">
            <div className="card-header">
              <div>
                <h4 className="card-title" style={{ fontSize: '1rem' }}>Diagnostic Tool Selection</h4>
                <p className="card-subtitle">Select analysis services to deploy to the live environment</p>
              </div>
              <span className="badge badge-purple">{selectedTools.length} selected</span>
            </div>
            <div className="alert alert-warning" role="note">
              <strong>Tool catalog (Sample):</strong>
              <span>Tool images and specifications are sample values and have not been verified against a live environment.</span>
            </div>

            {fieldErrors.tools && <div className="field-error" style={{ marginBottom: '8px' }}>{fieldErrors.tools}</div>}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px' }}>
              {TOOL_CATALOG.map((tool) => {
                const isSelected = selectedTools.includes(tool.id);

                return (
                  <div
                    key={tool.id}
                    role="checkbox"
                    aria-checked={isSelected}
                    tabIndex={0}
                    onClick={() => toggleTool(tool.id)}
                    onKeyDown={(event) => {
                      if (event.target !== event.currentTarget) return;
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        toggleTool(tool.id);
                      }
                    }}
                    style={{
                      border: isSelected ? '1px solid var(--eds-color-purple)' : '1px solid var(--eds-color-gray-200)',
                      borderRadius: 'var(--eds-radius-sm)',
                      background: isSelected ? 'var(--eds-color-purple-subtle)' : 'var(--eds-color-white)',
                      padding: '12px',
                      transition: 'all 0.15s ease',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onClick={(event) => event.stopPropagation()}
                        onChange={() => toggleTool(tool.id)}
                        style={{ marginTop: '4px', cursor: 'pointer' }}
                      />
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontWeight: 'var(--eds-font-weight-semibold)', color: 'var(--eds-color-gray-900)' }}>
                            {tool.name}
                          </span>
                          <span className="badge" style={{ background: '#f3f4f6', color: '#4b5563', fontSize: '0.7rem' }}>
                            {tool.imageType}
                          </span>
                        </div>
                        <p className="card-subtitle" style={{ margin: '2px 0 6px' }}>{tool.description}</p>
                        <div className="mono" style={{ fontSize: '0.7rem', color: 'var(--eds-color-gray-600)' }}>
                          Docker Image: {tool.image}
                        </div>

                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* SAFETY RESOURCE LIMITS */}
          <div className="card">
            <h4 className="card-title" style={{ fontSize: '1rem', marginBottom: '4px' }}>
              System Safety &amp; Resource Limits
            </h4>
            <p className="card-subtitle">
              Enforce CPU and memory throttles to safeguard live patient telemetry streams from degradation.
            </p>

            <div className="form-row">
              <label className="field grow">
                <span>Capture Duration (minutes) *</span>
                <input
                  type="number"
                  className={fieldErrors.captureDuration ? 'error' : ''}
                  value={captureDuration}
                  onChange={(e) => {
                    setCaptureDuration(e.target.value);
                    setFieldErrors({ ...fieldErrors, captureDuration: null });
                  }}
                />
                {fieldErrors.captureDuration && <span className="field-error">{fieldErrors.captureDuration}</span>}
                <small>1 to 120 min auto-cutoff</small>
              </label>

              <label className="field grow">
                <span>Max Log File Size (MB) *</span>
                <input
                  type="number"
                  className={fieldErrors.maxLogSize ? 'error' : ''}
                  value={maxLogSize}
                  onChange={(e) => {
                    setMaxLogSize(e.target.value);
                    setFieldErrors({ ...fieldErrors, maxLogSize: null });
                  }}
                />
                {fieldErrors.maxLogSize && <span className="field-error">{fieldErrors.maxLogSize}</span>}
                <small>Throttles output size</small>
              </label>
            </div>

            <div className="form-row">
              <label className="field grow">
                <span>CPU Cap per Tool (cores) *</span>
                <input
                  type="text"
                  className={fieldErrors.cpuLimit ? 'error' : ''}
                  value={cpuLimit}
                  onChange={(e) => {
                    setCpuLimit(e.target.value);
                    setFieldErrors({ ...fieldErrors, cpuLimit: null });
                  }}
                />
                {fieldErrors.cpuLimit && <span className="field-error">{fieldErrors.cpuLimit}</span>}
              </label>

              <label className="field grow">
                <span>Memory Cap (MiB) *</span>
                <input
                  type="number"
                  className={fieldErrors.memoryLimit ? 'error' : ''}
                  value={memoryLimit}
                  onChange={(e) => {
                    setMemoryLimit(e.target.value);
                    setFieldErrors({ ...fieldErrors, memoryLimit: null });
                  }}
                />
                {fieldErrors.memoryLimit && <span className="field-error">{fieldErrors.memoryLimit}</span>}
              </label>
            </div>

            <div className="action-row" style={{ marginTop: 'var(--eds-spacing-md)' }}>
              <button type="button" className="btn btn-secondary" onClick={handleValidateClick}>
                Validate Configuration &amp; Limits
              </button>
            </div>

            {validationBanner && (
              <div
                className={`alert ${validationBanner.type === 'success' ? 'alert-success' : 'alert-warning'}`}
                style={{ marginTop: '12px', marginBottom: 0 }}
              >
                <strong>{validationBanner.type === 'success' ? 'Validation Passed' : 'Validation Error'}:</strong>
                <span>{validationBanner.message}</span>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN: DISCOVERED TOPOLOGY & NETWORK SETTINGS */}
        <aside className="card card-tinted">
          <div className="card-header">
            <div>
              <h4 className="card-title" style={{ fontSize: '1rem' }}>Discovered System Topology</h4>
              <p className="card-subtitle">Portrait Mobile components &amp; system nodes (Sample)</p>
            </div>
            <span className="badge badge-warning">Sample data</span>
          </div>

          <span className="page-eyebrow" style={{ display: 'block', margin: '10px 0 4px' }}>
            Devices &amp; Gateways
          </span>
          <ul className="device-list">
            {DISCOVERED_TOPOLOGY.components.map((c) => (
              <li key={c.name} style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="check-title">{c.name}</span>
                  <span className="mono" style={{ fontSize: '0.75rem' }}>{c.ip}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="check-detail">{c.type}</span>
                  <span className="mono" style={{ color: c.warn ? 'var(--eds-color-warning)' : 'var(--eds-color-gray-500)', fontSize: '0.7rem' }}>
                    {c.latency}
                  </span>
                </div>
              </li>
            ))}
          </ul>

          <span className="page-eyebrow" style={{ display: 'block', margin: '14px 0 4px' }}>
            System Hosts
          </span>
          <ul className="device-list">
            {DISCOVERED_TOPOLOGY.k8sNodes.map((node) => (
              <li key={node.name} style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="check-title">{node.name}</span>
                  <span className="badge badge-success">{node.status}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--eds-color-gray-500)' }}>
                  <span>{node.role}</span>
                  <span className="mono">{node.k8sVersion}</span>
                </div>
              </li>
            ))}
          </ul>

          <span className="page-eyebrow" style={{ display: 'block', margin: '14px 0 4px' }}>
            Discovered Services
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {DISCOVERED_TOPOLOGY.services.map((srv) => (
              <span key={srv.name} className="badge badge-purple" title={`Service group · ${srv.replicas}`}>
                {srv.name}
              </span>
            ))}
          </div>

          <div style={{ marginTop: '14px', paddingTop: '10px', borderTop: '1px solid var(--eds-color-gray-200)', fontSize: '0.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
              <span style={{ color: 'var(--eds-color-gray-600)' }}>Subnet / MTU:</span>
              <span className="mono">{DISCOVERED_TOPOLOGY.networkSettings.subnet} ({DISCOVERED_TOPOLOGY.networkSettings.mtu})</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
              <span style={{ color: 'var(--eds-color-gray-600)' }}>Clock Variance:</span>
              <span className="mono" style={{ color: 'var(--eds-color-warning)' }}>{DISCOVERED_TOPOLOGY.networkSettings.clockDrift}</span>
            </div>
          </div>
        </aside>
      </div>

      {/* STEP NAVIGATION ACTIONS */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 'var(--eds-spacing-lg)' }}>
        <button type="button" className="btn btn-secondary" onClick={onBack}>
          &larr; Back to Select Environment
        </button>
        <button type="button" className="btn btn-primary" onClick={handleProceed}>
          Continue to Review &amp; Deploy &rarr;
        </button>
      </div>
    </div>
  );
};

export default Step2DiscoverConfigure;
