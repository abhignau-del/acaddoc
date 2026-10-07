// Sign-in: first-run setup, the login form, and the signed-in user for the rest of the app.
import { createContext, useCallback, useContext, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api, whenSignedOut } from "./api";
import type { User } from "./types";

interface Session { user: User; signOut: () => Promise<void>; setUser: (u: User) => void }
const Ctx = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside AuthGate");
  return s;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ loading: boolean; needsSetup: boolean; user: User | null; expired: boolean }>(
    { loading: true, needsSetup: false, user: null, expired: false });

  const load = useCallback(() =>
    api.authState()
      .then((s) => setState({ loading: false, needsSetup: s.needs_setup, user: s.user, expired: false }))
      .catch(() => setState((x) => ({ ...x, loading: false }))), []);

  useEffect(() => {
    load();
    whenSignedOut(() => setState((x) => (x.user ? { ...x, user: null, expired: true } : x)));
  }, [load]);

  const signOut = useCallback(async () => {
    try { await api.logout(); } finally { setState({ loading: false, needsSetup: false, user: null, expired: false }); }
  }, []);

  if (state.loading) return <div className="centre muted">Loading…</div>;
  if (state.needsSetup) return <Setup onDone={(user) => setState({ loading: false, needsSetup: false, user, expired: false })} />;
  if (!state.user) return <Login expired={state.expired} onDone={(user) => setState({ ...state, user, expired: false })} />;
  const setUser = (user: User) => setState((x) => ({ ...x, user }));
  return <Ctx.Provider value={{ user: state.user, signOut, setUser }}>{children}</Ctx.Provider>;
}

function Login({ onDone, expired }: { onDone: (u: User) => void; expired: boolean }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(expired ? "Your session ended. Please sign in again." : null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try { onDone((await api.login(username, password)).user); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <div className="centre">
      <form className="card auth" onSubmit={submit}>
        <h1>AcadDoc</h1>
        <p className="muted">Sign in to edit and review courses.</p>
        {error && <div className="alert" role="alert"><span>{error}</span></div>}
        <label className="field"><span>Username</span>
          <input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} /></label>
        <label className="field"><span>Password</span>
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        <button className="btn primary" disabled={busy || !username || !password}>{busy ? "Signing in…" : "Sign in"}</button>
        <p className="hint">Forgotten your password? Ask your AcadDoc administrator to reset it.</p>
      </form>
    </div>
  );
}

function Setup({ onDone }: { onDone: (u: User) => void }) {
  const [f, setF] = useState({ username: "", display_name: "", password: "", again: "" });
  const [error, setError] = useState<string | null>(null);
  const mismatch = f.again !== "" && f.again !== f.password;

  async function submit(e: FormEvent) {
    e.preventDefault(); setError(null);
    try { onDone((await api.setup(f.username, f.display_name, f.password)).user); }
    catch (err) { setError((err as Error).message); }
  }

  const field = (k: keyof typeof f, label: string, type = "text", auto = "off") => (
    <label className="field"><span>{label}</span>
      <input type={type} autoComplete={auto} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>
  );
  return (
    <div className="centre">
      <form className="card auth" onSubmit={submit}>
        <h1>Welcome to AcadDoc</h1>
        <p className="muted">Create the administrator account. The administrator adds faculty, HODs and the dean.</p>
        {error && <div className="alert" role="alert"><span>{error}</span></div>}
        {field("display_name", "Your name")}
        {field("username", "Username", "text", "username")}
        {field("password", "Password (at least 8 characters)", "password", "new-password")}
        {field("again", "Password again", "password", "new-password")}
        {mismatch && <p className="bad">The passwords differ.</p>}
        <button className="btn primary" disabled={!f.username || !f.display_name || f.password.length < 8 || f.again !== f.password}>
          Create administrator
        </button>
      </form>
    </div>
  );
}
