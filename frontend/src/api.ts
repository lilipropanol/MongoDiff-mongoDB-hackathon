import type { Config, Plan, Report, Source } from './types';

const key = 'schema-guard-session';
export const sessionId = sessionStorage.getItem(key) || crypto.randomUUID();
sessionStorage.setItem(key, sessionId);

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(45000),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(typeof payload.detail === 'string' ? payload.detail : 'The request failed. Check the API server and try again.');
  }
  return response.json() as Promise<T>;
}

export const api = {
  config: () => request<Config>('/config'),
  analyze: (source: Source) => request<Report>('/analyze', { source, session_id: sessionId }),
  history: () => request<Report[]>(`/runs?session_id=${sessionId}`),
  plan: (id: string, defaults: Record<string, unknown>, mappings: Record<string, Record<string, unknown>>) => request<Plan>(`/runs/${id}/plan`, { session_id: sessionId, defaults, mappings }),
  applyDemo: (plan_id: string) => request<Report>('/demo/apply', { session_id: sessionId, plan_id }),
  reset: () => request<Report>('/demo/reset', { session_id: sessionId, source: 'demo' }),
};

export function download(filename: string, text: string, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename; anchor.click();
  URL.revokeObjectURL(url);
}

export function number(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value) ? '—' : new Intl.NumberFormat('en-IE', { maximumFractionDigits: 0 }).format(value);
}

export function percent(failing: number, total: number) {
  const value = total ? failing / total * 100 : 0;
  if (value > 0 && value < 0.1) return '<0.1%';
  return `${new Intl.NumberFormat('en-IE', { maximumFractionDigits: 1 }).format(value)}%`;
}
