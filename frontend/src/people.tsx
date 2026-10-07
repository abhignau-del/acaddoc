// Account dialogs: change my password, and (admin) manage users.
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api } from "./api";
import { ROLE_LABELS } from "./courseops";
import type { Role, User } from "./types";

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    addEventListener("keydown", k);
    return () => removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal card" role="dialog" aria-modal="true" aria-label={title}>
        <div className="sub-head"><h2>{title}</h2><button className="btn" onClick={onClose} aria-label="Close">✕</button></div>
        {children}
      </div>
    </div>
  );
}

export function PasswordDialog({ onClose }: { onClose: () => void }) {
  const [f, setF] = useState({ current: "", next: "", again: "" });
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault(); setError(null);
    try { await api.changePassword(f.current, f.next); setDone(true); }
    catch (err) { setError((err as Error).message); }
  }
  return (
    <Modal title="Change password" onClose={done ? () => location.reload() : onClose}>
      {done
        ? <><p>Password changed. You have been signed out everywhere; sign in again with the new password.</p>
            <button className="btn primary" onClick={() => location.reload()}>Sign in again</button></>
        : <form className="stack" onSubmit={submit}>
            {error && <div className="alert" role="alert"><span>{error}</span></div>}
            <label className="field"><span>Current password</span>
              <input type="password" autoComplete="current-password" value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} /></label>
            <label className="field"><span>New password (at least 8 characters)</span>
              <input type="password" autoComplete="new-password" value={f.next} onChange={(e) => setF({ ...f, next: e.target.value })} /></label>
            <label className="field"><span>New password again</span>
              <input type="password" autoComplete="new-password" value={f.again} onChange={(e) => setF({ ...f, again: e.target.value })} /></label>
            <button className="btn primary" disabled={!f.current || f.next.length < 8 || f.next !== f.again}>Change password</button>
          </form>}
    </Modal>
  );
}

const ROLES: Role[] = ["faculty", "hod", "dean", "admin"];

export function UsersDialog({ me, onClose }: { me: User; onClose: () => void }) {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const blank = { username: "", display_name: "", password: "", role: "faculty" as Role, department: "" };
  const [f, setF] = useState(blank);
  const load = () => api.users().then(setUsers).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function run(p: Promise<unknown>, ok: string) {
    setError(null); setNote(null);
    try { await p; setNote(ok); await load(); return true; }
    catch (e) { setError((e as Error).message); return false; }
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    if (await run(api.addUser(f), `Added ${f.username}. Give them their password in person.`)) setF(blank);
  }

  function resetPassword(u: User) {
    const pw = prompt(`New password for ${u.display_name} (at least 8 characters):`);
    if (pw) run(api.editUser(u.id, { password: pw }), `Password for ${u.username} reset; they have been signed out.`);
  }

  return (
    <Modal title="Users" onClose={onClose}>
      {error && <div className="alert" role="alert"><span>{error}</span></div>}
      {note && <div className="note" role="status">{note}</div>}
      <table className="users">
        <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Department</th><th>Status</th><th /></tr></thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className={u.disabled ? "muted" : ""}>
              <td>{u.display_name}{u.id === me.id && <span className="muted"> (you)</span>}</td>
              <td>{u.username}</td>
              <td>
                <select aria-label={`Role of ${u.username}`} value={u.role}
                  onChange={(e) => run(api.editUser(u.id, { role: e.target.value as Role }), `${u.username} is now ${ROLE_LABELS[e.target.value as Role]}.`)}>
                  {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                </select>
              </td>
              <td>
                <input aria-label={`Department of ${u.username}`} defaultValue={u.department} key={u.department} size={8}
                  onBlur={(e) => e.target.value.trim() !== u.department &&
                    run(api.editUser(u.id, { department: e.target.value }), `${u.username} moved to ${e.target.value || "no department"}.`)} />
              </td>
              <td>{u.disabled ? "Disabled" : "Active"}</td>
              <td className="row">
                <button className="btn" onClick={() => resetPassword(u)}>Reset password</button>
                <button className="btn" onClick={() => run(api.editUser(u.id, { disabled: !u.disabled }),
                  `${u.username} ${u.disabled ? "enabled" : "disabled and signed out"}.`)}>{u.disabled ? "Enable" : "Disable"}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Add a user</h3>
      <form className="grid" onSubmit={add}>
        <label className="field"><span>Name</span><input value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></label>
        <label className="field"><span>Username</span><input autoComplete="off" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></label>
        <label className="field"><span>Role</span>
          <select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
            {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </select></label>
        <label className="field"><span>Department</span><input value={f.department} placeholder={f.role === "dean" || f.role === "admin" ? "(none)" : "e.g. CSE"}
          onChange={(e) => setF({ ...f, department: e.target.value })} /></label>
        <label className="field"><span>First password</span><input type="password" autoComplete="new-password" value={f.password}
          onChange={(e) => setF({ ...f, password: e.target.value })} /></label>
        <button className="btn primary" disabled={!f.username || !f.display_name || f.password.length < 8}>Add user</button>
      </form>
      <p className="hint">HODs review courses from their own department. The dean gives final approval. Administrators manage accounts and never approve.</p>
    </Modal>
  );
}
