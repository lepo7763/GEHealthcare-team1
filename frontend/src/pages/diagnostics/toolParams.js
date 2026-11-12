// Per-tool parameter handling for the Configure step. A tool listed here gets
// an Edit button; tools without parameters (e.g. container logs) do not.
import { DEFAULT_AXONE_PARAMS, summarizeAxone, toAxoneQuery } from './axoneParams';
import { DEFAULT_UMF_PARAMS, summarizeUmf, toUmfQuery } from './umfParams';

export const TOOL_PARAMS = {
  'umf-rti': { defaults: DEFAULT_UMF_PARAMS, toQuery: toUmfQuery, summarize: summarizeUmf },
  'axone-logs': {
    defaults: DEFAULT_AXONE_PARAMS,
    toQuery: toAxoneQuery,
    summarize: summarizeAxone,
  },
};

export const isConfigurable = (toolId) => toolId in TOOL_PARAMS;

export const defaultToolParams = () =>
  Object.fromEntries(Object.entries(TOOL_PARAMS).map(([id, tool]) => [id, tool.defaults]));

// Returns a user-facing message describing what's missing/invalid, or null.
export const getToolIssue = (toolId, params) => {
  const tool = TOOL_PARAMS[toolId];
  if (!tool) return null;
  try {
    tool.toQuery(params);
    return null;
  } catch (e) {
    return e.message;
  }
};

// Query params for every selected configurable tool. Throws on invalid params.
export const buildToolQuery = (selected, toolParams) => {
  const query = new URLSearchParams();
  selected.forEach((toolId) => {
    const tool = TOOL_PARAMS[toolId];
    if (tool) tool.toQuery(toolParams[toolId]).forEach((v, k) => query.append(k, v));
  });
  return query;
};

// One-line, human-readable summary of a tool's parameters (Review step).
export const summarizeToolParams = (toolId, params) =>
  TOOL_PARAMS[toolId]?.summarize(params) ?? '';
