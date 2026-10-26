// Shared constants and helpers for the Diagnostics workflow.

export const STEPS = ['Connect & discover', 'Configure', 'Review & deploy', 'Collect'];

export const SERVICES = [
  {
    id: 'container-logs',
    name: 'Container Log Collection',
    description: 'Logs from every container across all namespaces.',
  },
  {
    id: 'wireshark',
    name: 'Wireshark',
    description: 'Placeholder — capture platform network traffic.',
  },
  {
    id: 'netshoot',
    name: 'Netshoot',
    description: 'Capture network traffic from Kubernetes test pods and download PCAP files.',
  },
  {
    id: 'umf-rti',
    name: 'UMF RTI',
    description: 'Placeholder — UMF real-time interface data.',
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
  listing: 'Listing pods across the cluster…',
  packaging: 'Packaging logs…',
};

export const parseFilename = (disposition) => {
  if (!disposition) return null;
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return match ? match[1] : null;
};
