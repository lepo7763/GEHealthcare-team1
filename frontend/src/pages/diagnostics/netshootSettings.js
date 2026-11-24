export const NETSHOOT_DEFAULT_SCOPE = 'both';

export const NETSHOOT_SCOPES = [
  {
    value: 'both',
    label: 'Both',
    detail: 'Capture pod and host traffic',
  },
  {
    value: 'pod',
    label: 'Pod traffic only',
  },
  {
    value: 'host',
    label: 'Host traffic only',
  },
];

export const NETSHOOT_SCOPE_TEXT = {
  both: 'Pod and host traffic',
  pod: 'Pod traffic only',
  host: 'Host traffic only',
};

export const NETSHOOT_MIN_DURATION = 1;
export const NETSHOOT_MAX_DURATION = 600;
