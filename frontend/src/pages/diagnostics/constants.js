// Shared constants and helpers for the Diagnostics workflow.

export const STEPS = ['Connect & discover', 'Configure', 'Review & deploy', 'Collect'];

export const SERVICES = [
  {
    id: 'container-logs',
    name: 'Container Log Collection',
    description: 'Logs from every container across all namespaces.',
  },
  {
    id: 'umf-rti',
    name: 'UMF RTI',
    description:
      'Captures UMF RTI discovery and QoS data from the live platform. No sample values are read.',
  },
  {
    id: 'wireshark-tshark',
    name: 'Wireshark / tshark',
    description:
      'Captures live network packets and analyzes TCP resets, retransmissions, and DNS failures.',
  },
];

export const STEP_INFO = {
  1: {
    title: 'Connect & discover',
    subtitle: 'Verify Kubernetes reachability and cluster access from this workstation.',
  },
  2: {
    title: 'Configure collection',
    subtitle: 'Choose which services to include in this diagnostic session.',
  },
  3: {
    title: 'Review & deploy',
    subtitle: 'Confirm the collection plan before running it.',
  },
  4: {
    title: 'Collect',
    subtitle: 'Run the configured collection and monitor progress.',
  },
};

// Progress statuses that mean the backend is actively collecting.
export const RUNNING_STATUSES = ['listing', 'collecting', 'packaging'];

export const STATUS_LABEL = {
  idle: 'Starting collection…',
  listing: 'Preparing collection…',
  collecting: 'Collecting…',
  packaging: 'Packaging diagnostic package…',
  done: 'Collection complete.',
  error: 'Collection failed.',
};

export const SERVICE_STATUS_LABEL = {
  pending: 'Waiting',
  collecting: 'Collecting',
  done: 'Complete',
  error: 'Failed',
};

export const parseFilename = (disposition) => {
  if (!disposition) return null;
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return match ? match[1] : null;
};
