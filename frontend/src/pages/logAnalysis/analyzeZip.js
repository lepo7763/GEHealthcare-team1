// Sends a log zip (from GET /api/logs/zip) to one of the /api/analysis endpoints and returns
// the JSON report. Throws an Error with a readable message so callers can show it in an alert.
async function postZip(path, file, filename) {
  // Field name must be "file" to match the UploadFile parameter in log_analysis/router.py
  const form = new FormData();
  form.append('file', file, filename);

  let response;
  try {
    response = await fetch(path, { method: 'POST', body: form });
  } catch {
    throw new Error('Could not reach the backend. Is it running on port 8000?');
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    // 400 from our own checks has a string detail; 422 from FastAPI validation has a list
    const detail = typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body;
}

export const analyzeZip = (file, filename = 'logs.zip') =>
  postZip('/api/analysis/zip', file, filename);

export const scanZipForPrivacy = (file, filename = 'logs.zip') =>
  postZip('/api/analysis/privacy', file, filename);
