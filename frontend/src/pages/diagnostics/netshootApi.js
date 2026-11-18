// Netshoot packet capture client — MOCK.
//
// Agreed configuration (team meeting, 11/16): no namespace picking, just a capture
// duration and a capture scope (Pod traffic, host traffic, or both). The backend
// (ethan/netshoot-api-integration) is being updated to match; until progress, cancel and
// download endpoints exist, this module simulates the whole capture in the browser.
// When the real endpoints land, only this file changes; the UI talks to
// startNetshootCapture() and the handle it returns.
//
// TODO(SCRUM-86): confirm the request field names with Ethan. Assumed for now:
//   POST /api/network/captures  { scope: 'both' | 'pod' | 'host', duration_seconds: 1-600 }

export const NETSHOOT_SCOPES = [
  { value: 'both', label: 'Both', detail: 'capture Pod and host traffic' },
  { value: 'pod', label: 'Pod traffic only' },
  { value: 'host', label: 'Host traffic only' },
];
export const NETSHOOT_DEFAULT_SCOPE = 'both';

export const NETSHOOT_SCOPE_TEXT = {
  both: 'Pod and host traffic',
  pod: 'Pod traffic only',
  host: 'Host traffic only',
};

export const NETSHOOT_MIN_DURATION = 1;
export const NETSHOOT_MAX_DURATION = 600;

// Fake cluster layout: running pods per node.
const MOCK_NODE_PODS = { 'miniedge-p360': 8, 'hub-node-1': 5 };

const buildNodes = (scope) => {
  const suffix = Date.now() % 100000;
  return Object.entries(MOCK_NODE_PODS).map(([node, pods]) => ({
    node,
    jobName: `netshoot-${node}-${suffix}`,
    pods: scope === 'host' ? 0 : pods,
    host: scope !== 'pod',
  }));
};

const placeholderDownload = (state) => {
  const lines = [
    'SIMULATED NETSHOOT CAPTURE (frontend mock, no packets were captured)',
    `Scope: ${NETSHOOT_SCOPE_TEXT[state.scope]}`,
    `Captured: ${state.elapsed} of ${state.durationSeconds} s${state.status === 'cancelled' ? ' (cancelled)' : ''}`,
    ...state.nodes.flatMap((n) => [
      ...(n.pods > 0 ? [`${n.node}: ${n.pods} pods -> ${n.node}-pods.pcap`] : []),
      ...(n.host ? [`${n.node}: host interfaces -> ${n.node}-host.pcap`] : []),
    ]),
  ];
  const blob = new Blob([lines.join('\n') + '\n'], { type: 'text/plain' });
  return {
    url: URL.createObjectURL(blob),
    filename: `netshoot_capture_SIMULATED${state.status === 'cancelled' ? '_partial' : ''}.txt`,
  };
};

// Starts a (simulated) capture. onUpdate receives the full state on every change:
//   { status: 'scheduling' | 'capturing' | 'packaging' | 'done' | 'cancelled' | 'error',
//     scope, durationSeconds, elapsed, nodes: [{ node, jobName, pods, host }],
//     download: { url, filename } | null, error: string | null }
// Returns { cancel(), dispose() }.
export const startNetshootCapture = ({ scope, durationSeconds }, onUpdate) => {
  let state = {
    status: 'scheduling',
    scope,
    durationSeconds,
    elapsed: 0,
    nodes: [],
    download: null,
    error: null,
  };
  const timers = [];
  const emit = (patch) => {
    state = { ...state, ...patch };
    onUpdate(state);
  };
  const later = (fn, ms) => timers.push(setTimeout(fn, ms));
  const stopTimers = () => timers.forEach((t) => (clearTimeout(t), clearInterval(t)));

  emit({});

  // POST /api/network/captures (simulated latency, then the 202 response)
  later(() => {
    emit({ status: 'capturing', nodes: buildNodes(scope) });

    const tick = setInterval(() => {
      const elapsed = state.elapsed + 1;
      if (elapsed < durationSeconds) {
        emit({ elapsed });
        return;
      }
      clearInterval(tick);
      emit({ elapsed: durationSeconds, status: 'packaging' });
      later(() => emit({ status: 'done', download: placeholderDownload(state) }), 1200);
    }, 1000);
    timers.push(tick);
  }, 800);

  return {
    cancel: () => {
      if (!['scheduling', 'capturing'].includes(state.status)) return;
      stopTimers();
      // Partial results are kept, like the real Jobs would upload what they captured so far.
      const cancelled = { ...state, status: 'cancelled' };
      emit({ status: 'cancelled', download: state.elapsed > 0 ? placeholderDownload(cancelled) : null });
    },
    dispose: stopTimers,
  };
};
