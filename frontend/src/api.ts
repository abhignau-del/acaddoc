import type {
  Action, Course, CourseFull, CourseSummary, HistoryEvent, Issue, MailRow, MailStatus, Role, StructureProblem, User,
  VersionInfo,
} from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string, public issues: Issue[] = []) { super(message); }
}

/** Called when the server says the session has ended, so the app can show the sign-in screen. */
let onSignedOut: () => void = () => {};
export function whenSignedOut(f: () => void) { onSignedOut = f; }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...init });
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
  if (r.status === 401 && !r.url.includes("/api/auth/")) onSignedOut();
  return new ApiError(r.status, msg, body.issues ?? []);
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export interface AuthState { needs_setup: boolean; user: User | null; roles: Role[] }

export const api = {
  authState: () => call<AuthState>("/api/auth/state"),
  setup: (username: string, display_name: string, password: string) =>
    call<{ user: User }>("/api/auth/setup", json("POST", { username, display_name, password })),
  login: (username: string, password: string) => call<{ user: User }>("/api/auth/login", json("POST", { username, password })),
  logout: () => call<void>("/api/auth/logout", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    call<void>("/api/auth/password", json("POST", { current_password, new_password })),
  updateProfile: (email: string) => call<{ user: User }>("/api/auth/me", json("PATCH", { email })),

  users: () => call<User[]>("/api/users"),
  addUser: (u: { username: string; display_name: string; password: string; role: Role; department: string; email: string }) =>
    call<User>("/api/users", json("POST", u)),
  editUser: (id: string, patch: Partial<Pick<User, "display_name" | "role" | "department" | "disabled" | "email">> & { password?: string }) =>
    call<User>(`/api/users/${id}`, json("PATCH", patch)),

  list: () => call<CourseSummary[]>("/api/courses"),
  get: (code: string) => call<CourseFull>(`/api/courses/${encodeURIComponent(code)}`),
  create: (c: Course) => call<CourseFull>("/api/courses", json("POST", c)),
  update: (code: string, c: Course) => call<CourseFull>(`/api/courses/${encodeURIComponent(code)}`, json("PUT", c)),
  setMeta: (code: string, patch: { department?: string; owner_id?: string }) =>
    call<CourseFull>(`/api/courses/${encodeURIComponent(code)}/meta`, json("PATCH", patch)),
  remove: (code: string) => call<void>(`/api/courses/${encodeURIComponent(code)}`, { method: "DELETE" }),
  act: (code: string, action: Action, comment = "") =>
    call<CourseFull>(`/api/courses/${encodeURIComponent(code)}/actions/${action}`, json("POST", { comment })),
  history: (code: string) =>
    call<{ events: HistoryEvent[]; versions: VersionInfo[] }>(`/api/courses/${encodeURIComponent(code)}/history`),
  validate: (draft: unknown) =>
    call<{ structure: StructureProblem[]; issues: Issue[] }>("/api/validate", json("POST", draft)),
  programmes: () => call<string[]>("/api/programmes"),

  mailStatus: () => call<MailStatus>("/api/admin/mail"),
  mailTest: () => call<MailRow>("/api/admin/mail/test", { method: "POST" }),
  mailRetry: (id: number) => call<MailRow>(`/api/admin/mail/${id}/retry`, { method: "POST" }),
};

/** Fetch a generated file and hand it to the browser as a download. Returns the response headers. */
export async function download(path: string, fallbackName: string): Promise<Headers> {
  const r = await fetch(BASE + path, { credentials: "same-origin" });
  if (!r.ok) throw await toError(r);
  const name = /filename="?([^"]+)"?/.exec(r.headers.get("content-disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await r.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
  return r.headers;
}
