// Utilities to normalize backend media file paths into public URLs

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api/v1';

function backendOrigin(): string {
  try {
    const u = new URL(API_BASE_URL);
    // strip trailing /api/v1 (with or without trailing slash)
    const origin = `${u.protocol}//${u.host}`;
    return origin;
  } catch {
    return 'http://127.0.0.1:8000';
  }
}

function isHttpUrl(url: string): boolean {
  return /^https?:\/\//i.test(url);
}

function sanitizeFilename(value: string): string {
  return value.replace(/[<>:"/\\|?*\u0000-\u001F]/g, '-').trim();
}

/**
 * Normalize raw path/URL returned by backend/tooling to a browser-accessible URL.
 * Handles:
 * - file:/// absolute URLs → /files/{temp|generated|uploads}/...
 * - Windows absolute paths → /files/... with normalized slashes
 * - POSIX absolute paths → /files/...
 * - Already-public paths (http(s):// or /files/...) → returned as-is (with backend origin when needed)
 */
export function resolvePublicMediaUrl(raw?: string | null): string | undefined {
  if (!raw) return undefined;
  let s = String(raw).trim();
  if (!s) return undefined;

  // Already absolute http(s)
  if (isHttpUrl(s)) return s;

  // file:// scheme → strip and continue
  if (s.startsWith('file://')) {
    s = s.replace(/^file:\/\//i, '');
  }

  // Normalize slashes for matching
  const normalized = s.replace(/\\/g, '/');

  // If already a public static path (relative), prefix backend origin
  if (normalized.startsWith('/files/')) {
    return `${backendOrigin()}${normalized}`;
  }

  // Try to locate a storage subfolder and rest path
  const m = normalized.match(/(?:^|\/)storage\/(uploads|generated|temp|outputs)\/(.+)$/i);
  if (m) {
    const bucket = m[1].toLowerCase();
    const rest = m[2];
    return `${backendOrigin()}/files/${bucket}/${rest}`;
  }

  // Sometimes full repo path contains /backend/storage/...; capture from there
  const m2 = normalized.match(/(?:^|\/)backend\/storage\/(uploads|generated|temp|outputs)\/(.+)$/i);
  if (m2) {
    const bucket = m2[1].toLowerCase();
    const rest = m2[2];
    return `${backendOrigin()}/files/${bucket}/${rest}`;
  }

  // Fallback: if it looks like a bare filename, serve from temp bucket
  const filename = normalized.split('/').pop();
  if (filename && !filename.includes('.')) return undefined;
  if (filename) {
    if (/^final_/i.test(filename)) {
      const subdir = filename.endsWith('.mp3') ? 'audio' : 'videos';
      return `${backendOrigin()}/files/outputs/${subdir}/${filename}`;
    }
    return `${backendOrigin()}/files/temp/${filename}`;
  }

  return undefined;
}

export function getMediaDownloadFilename(raw?: string | null, fallbackBase = 'generated-video'): string {
  if (raw) {
    try {
      const pathname = isHttpUrl(raw) ? new URL(raw).pathname : raw;
      const candidate = decodeURIComponent(
        pathname
          .replace(/\\/g, '/')
          .replace(/^file:\/\//i, '')
          .split(/[?#]/, 1)[0]
          .split('/')
          .pop() || ''
      );
      if (candidate.includes('.')) {
        return sanitizeFilename(candidate);
      }
    } catch {
      // Fall through to the fallback filename below.
    }
  }

  const safeBase = sanitizeFilename(fallbackBase) || 'generated-video';
  return safeBase.endsWith('.mp4') ? safeBase : `${safeBase}.mp4`;
}
