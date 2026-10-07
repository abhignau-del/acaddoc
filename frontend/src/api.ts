import type { Course, CourseSummary, Issue, StructureProblem } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string, public issues: Issue[] = []) { super(message); }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) throw await toError(r);
  return (r.status === 204 ? undefined : await r.json()) as T;
}

async function toError(r: Response): Promise<ApiError> {
  let body: { detail?: unknown; issues?: Issue[] } = {};
  try { body = await r.json(); } catch { /* not JSON */ }
  const d = body.detail;
  const msg = typeof d === "string" ? d
    : Array.isArray(d) ? d.map((e: { loc?: unknown[]; msg?: string }) => `${(e.loc ?? []).slice(1).join(".")}: ${e.msg}`).join("; ")
    : `Request failed (${r.status})`;
  return new ApiError(r.status, msg, body.issues ?? []);
}

export interface Saved { course: Course; updated_at: string; issues: Issue[] }

export const api = {
  list: () => call<CourseSummary[]>("/api/courses"),
  get: (code: string) => call<Saved>(`/api/courses/${encodeURIComponent(code)}`),
  create: (c: Course) => call<Saved>("/api/courses", { method: "POST", body: JSON.stringify(c) }),
  update: (code: string, c: Course) =>
    call<Saved>(`/api/courses/${encodeURIComponent(code)}`, { method: "PUT", body: JSON.stringify(c) }),
  remove: (code: string) => call<void>(`/api/courses/${encodeURIComponent(code)}`, { method: "DELETE" }),
  validate: (draft: unknown) =>
    call<{ structure: StructureProblem[]; issues: Issue[] }>("/api/validate", { method: "POST", body: JSON.stringify(draft) }),
  programmes: () => call<string[]>("/api/programmes"),
};

/** Fetch a generated file and hand it to the browser as a download. Returns the response headers. */
export async function download(path: string, fallbackName: string): Promise<Headers> {
  const r = await fetch(BASE + path);
  if (!r.ok) throw await toError(r);
  const name = /filename="?([^"]+)"?/.exec(r.headers.get("content-disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await r.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
  return r.headers;
}
