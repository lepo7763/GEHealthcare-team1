export const DOWNLOAD_PATH_KEY = 'iomt-download-path';
export const ASK_LOCATION_KEY = 'iomt-ask-location';
export const DEFAULT_DOWNLOAD_PATH = 'Downloads';

export function getDownloadPath() {
  try {
    if (typeof localStorage !== 'undefined') {
      return localStorage.getItem(DOWNLOAD_PATH_KEY) || DEFAULT_DOWNLOAD_PATH;
    }
    return DEFAULT_DOWNLOAD_PATH;
  } catch {
    return DEFAULT_DOWNLOAD_PATH;
  }
}

export function setDownloadPath(path) {
  try {
    const value = path?.trim() || DEFAULT_DOWNLOAD_PATH;
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(DOWNLOAD_PATH_KEY, value);
    }
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      window.dispatchEvent(
        new CustomEvent('iomt-settings-updated', {
          detail: { downloadPath: value },
        })
      );
    }
    return value;
  } catch {
    return DEFAULT_DOWNLOAD_PATH;
  }
}

export function getAlwaysAskLocation() {
  try {
    if (typeof localStorage !== 'undefined') {
      return localStorage.getItem(ASK_LOCATION_KEY) === 'true';
    }
    return false;
  } catch {
    return false;
  }
}

export function setAlwaysAskLocation(alwaysAsk) {
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(ASK_LOCATION_KEY, alwaysAsk ? 'true' : 'false');
    }
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      window.dispatchEvent(
        new CustomEvent('iomt-settings-updated', {
          detail: { alwaysAskLocation: Boolean(alwaysAsk) },
        })
      );
    }
    return Boolean(alwaysAsk);
  } catch {
    return false;
  }
}

/**
 * Saves a file using the native file picker if user requested it,
 * otherwise triggers standard browser download to the configured download path.
 */
export async function saveBlobFile(blob, filename) {
  const askLocation = getAlwaysAskLocation();

  if (askLocation && typeof window !== 'undefined' && typeof window.showSaveFilePicker === 'function') {
    try {
      const ext = filename.split('.').pop() || 'zip';
      const handle = await window.showSaveFilePicker({
        suggestedName: filename,
        types: [
          {
            description: `${ext.toUpperCase()} File`,
            accept: { 'application/octet-stream': [`.${ext}`] },
          },
        ],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return { success: true, method: 'picker', name: handle.name };
    } catch (err) {
      if (err.name === 'AbortError') {
        return { success: false, aborted: true };
      }
      console.warn('Native save picker failed, falling back to download:', err);
    }
  }

  // Standard browser download trigger
  if (typeof document !== 'undefined') {
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }

  return { success: true, method: 'download', name: filename, path: getDownloadPath() };
}
