import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, download } from "./api";
import { useSession } from "./auth";
import {
  academicYear, ACTION_UI, clearDraft, countBySection, emptyCourse, EVENT_LABELS, filterCourses, loadDraft,
  ROLE_LABELS, same, saveDraft, sectionOf, tidy, type Draft, type ListFilter,
} from "./courseops";
import { Editor, SECTIONS } from "./Editor";
import { Modal, PasswordDialog, UsersDialog } from "./people";
import type {
  Action, Course, CourseFull, CourseSummary, HistoryEvent, Issue, Kind, StructureProblem, User, VersionInfo,
} from "./types";

/** What is open in the editor. `code` is the saved code (null = not saved yet); `full` is the server's view. */
interface Open { code: string | null; full: CourseFull | null; course: Course }

export default function App() {
  const { user, signOut } = useSession();
  const [list, setList] = useState<CourseSummary[]>([]);
  const [filter, setFilter] = useState<ListFilter>(user.role === "hod" || user.role === "dean" ? "review" : "all");
  const [open, setOpen] = useState<Open | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [structure, setStructure] = useState<StructureProblem[]>([]);
  const [restorable, setRestorable] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<null | "users" | "password">(null);
  const [asking, setAsking] = useState<Action | null>(null);
  const [historyTick, setHistoryTick] = useState(0);

  const refresh = useCallback(() => api.list().then(setList).catch((e) => setError(String(e.message ?? e))), []);
  useEffect(() => { refresh(); }, [refresh]);

  const editable = !!open && (open.code === null || !!open.full?.can.edit);
  const dirty = !!open && editable && !same(tidy(open.course), open.full && tidy(open.full.course));

  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    addEventListener("beforeunload", h);
    return () => removeEventListener("beforeunload", h);
  }, [dirty]);

  // Live validation of the draft, debounced; also keep the draft in this browser.
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!open || !editable) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      if (dirty) saveDraft(open.code, open.course);
      api.validate(tidy(open.course))
        .then((r) => { setIssues(r.issues); setStructure(r.structure); })
        .catch(() => { /* the save will report it */ });
    }, 350);
    return () => window.clearTimeout(timer.current);
  }, [open, dirty, editable]);

  function confirmLeave(): boolean {
    return !dirty || confirm("You have unsaved changes. A copy stays in this browser. Leave this course?");
  }

  function show(full: CourseFull) {
    setOpen({ code: full.course.course_code, full, course: full.course });
    setIssues(full.issues); setStructure([]);
    setHistoryTick((t) => t + 1);
  }

  async function select(code: string) {
    if (open?.code === code || !confirmLeave()) return;
    setError(null); setNote(null);
    try {
      const full = await api.get(code);
      show(full);
      const d = full.can.edit ? loadDraft(code) : null;
      setRestorable(d && !same(tidy(d.course), tidy(full.course)) ? d : null);
    } catch (e) { setError((e as Error).message); }
  }

  function create(kind: Kind) {
    if (!confirmLeave()) return;
    setError(null); setNote(null);
    setOpen({ code: null, full: null, course: emptyCourse(kind) });
    setIssues([]); setStructure([]);
    setRestorable(loadDraft(null));
  }

  async function save() {
    if (!open) return;
    setBusy(true); setError(null); setNote(null);
    try {
      const body = tidy(open.course);
      const full = open.code ? await api.update(open.code, body) : await api.create(body);
      clearDraft(open.code);
      show(full); setRestorable(null);
      setNote(`Saved ${full.course.course_code}.`);
      refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function act(action: Action, comment = "") {
    if (!open?.code) return;
    const ui = ACTION_UI.find((a) => a.action === action)!;
    if (ui.confirm && !confirm(ui.confirm)) return;
    setBusy(true); setError(null); setNote(null);
    try {
      const full = await api.act(open.code, action, comment);
      show(full); setAsking(null);
      setNote(`${full.course.course_code}: ${full.status_label}.`);
      refresh();
    } catch (e) {
      const ae = e as ApiError;
      setError(ae.issues?.length ? `${ae.message}: ${ae.issues.map((i) => i.message).join("; ")}` : ae.message);
    } finally { setBusy(false); }
  }

  async function remove() {
    if (!open?.code || !confirm(`Delete ${open.code}? This cannot be undone.`)) return;
    try {
      await api.remove(open.code);
      clearDraft(open.code);
      setOpen(null); refresh();
    } catch (e) { setError((e as Error).message); }
  }

  async function docx(force = false) {
    if (!open?.code) return;
    setError(null);
    try { await download(`/api/courses/${encodeURIComponent(open.code)}/docx${force ? "?force=true" : ""}`, `${open.code}.docx`); }
    catch (e) {
      const ae = e as ApiError;
      setError(ae.issues?.length ? `Not generated: ${ae.issues.map((i) => i.message).join("; ")}` : ae.message);
    }
  }

  const counts = useMemo(() => countBySection(issues, structure), [issues, structure]);
  const errors = issues.filter((i) => i.severity === "error").length;
  const shown = filterCourses(list, filter, user);
  const reviewCount = list.filter((c) => c.awaiting_me).length;
  const can = open?.full?.can;

  return (
    <div className="app">
      <header>
        <h1>AcadDoc</h1>
        <span className="muted">Course content in, institutional documents out</span>
        <span className="spacer" />
        <span className="who">{user.display_name} · {ROLE_LABELS[user.role]}{user.department ? ` · ${user.department}` : ""}</span>
        {user.role === "admin" && <button className="btn on-accent" onClick={() => setDialog("users")}>Users</button>}
        <button className="btn on-accent" onClick={() => setDialog("password")}>Password</button>
        <button className="btn on-accent" onClick={() => { if (confirmLeave()) signOut(); }}>Sign out</button>
      </header>

      <aside>
        {user.role !== "dean" && (
          <div className="row">
            <button className="btn primary" onClick={() => create("theory")}>+ Theory course</button>
            <button className="btn" onClick={() => create("laboratory")}>+ Lab</button>
          </div>
        )}
        <div className="tabs" role="tablist" aria-label="Show">
          {([["all", "All"], ["mine", "Mine"], ["review", `To review${reviewCount ? ` (${reviewCount})` : ""}`]] as [ListFilter, string][])
            .map(([k, label]) => (
              <button key={k} role="tab" aria-selected={filter === k} className={filter === k ? "active" : ""}
                onClick={() => setFilter(k)}>{label}</button>
            ))}
        </div>
        <ul className="course-list">
          {shown.map((c) => (
            <li key={c.course_code}>
              <button className={open?.code === c.course_code ? "active" : ""} onClick={() => select(c.course_code)}>
                <span><b>{c.course_code}</b> {c.course_title}</span>
                <small>
                  <span className={`chip ${c.status}`}>{c.status_label}</span>
                  {c.department && ` ${c.department}`}
                  {c.owner_name && ` · ${c.owner_name}`}
                  {c.errors ? <span className="bad"> · {c.errors} error{c.errors > 1 ? "s" : ""}</span> : null}
                </small>
              </button>
            </li>
          ))}
          {!shown.length && <li className="muted">{filter === "review" ? "Nothing is waiting for you." : "No courses here."}</li>}
        </ul>
        <Handbook onError={setError} />
      </aside>

      <main>
        {error && <div className="alert" role="alert"><span>{error}</span><button aria-label="Dismiss" onClick={() => setError(null)}>×</button></div>}
        {note && <div className="note" role="status">{note}</div>}

        {!open && <div className="empty">
          <h2>Open a course on the left{user.role !== "dean" ? ", or start a new one" : ""}.</h2>
          <p className="muted">You type the content. The institution’s Word template decides how it looks.</p>
        </div>}

        {open && <>
          {restorable && editable && (
            <div className="note">
              Unsaved changes from {new Date(restorable.savedAt).toLocaleString()} were found in this browser.
              <span className="row">
                <button className="btn" onClick={() => { setOpen({ ...open, course: restorable.course }); setRestorable(null); }}>Restore</button>
                <button className="btn" onClick={() => { clearDraft(open.code); setRestorable(null); }}>Discard</button>
              </span>
            </div>
          )}

          <div className="toolbar">
            <h2>{open.code ?? "New course"}{dirty && <span className="muted"> · unsaved</span>}</h2>
            {open.full && <span className={`chip ${open.full.status}`}>{open.full.status_label}</span>}
            {open.full?.approved_version != null &&
              <span className="muted">v{open.full.approved_version} in force</span>}
            <span className="spacer" />
            {editable && <button className="btn primary" disabled={busy || !dirty || structure.length > 0} onClick={save}
              title={structure.length ? "Fix the problems listed on the right first" : undefined}>
              {busy ? "Saving…" : "Save"}
            </button>}
            {can && ACTION_UI.filter((a) => can[a.action]).map((a) => (
              <button key={a.action} className={a.primary ? "btn primary" : "btn"} disabled={busy || dirty}
                title={dirty ? "Save first" : undefined}
                onClick={() => (a.comment ? setAsking(a.action) : act(a.action))}>{a.label}</button>
            ))}
            <button className="btn" disabled={!open.code || dirty || errors > 0} onClick={() => docx()}
              title={dirty ? "Save first" : errors ? "Fix the errors first" : "Download the Word document"}>
              DOCX
            </button>
            {open.code && !dirty && errors > 0 &&
              <button className="btn link" onClick={() => docx(true)}>DOCX anyway</button>}
            {can?.delete && <button className="btn danger" onClick={remove}>Delete</button>}
          </div>

          {open.full && !editable && (
            <div className="note">{readOnlyReason(open.full, user)}</div>
          )}

          <div className="workspace">
            <fieldset className="plain" disabled={!editable}>
              <Editor course={open.course} counts={editable ? counts : {}} onChange={(course) => setOpen({ ...open, course })} />
            </fieldset>
            <div className="side">
              {editable && <Checks issues={issues} structure={structure} />}
              {open.full && <Record full={open.full} me={user} onChanged={(f) => { show(f); refresh(); }} onError={setError} />}
              {open.code && <History code={open.code} tick={historyTick} />}
            </div>
          </div>
        </>}
      </main>

      {asking && <Modal title="Send back for revision" onClose={() => setAsking(null)}>
        <RevisionForm busy={busy} onSend={(c) => act(asking, c)} />
      </Modal>}
      {dialog === "users" && <UsersDialog me={user} onClose={() => { setDialog(null); refresh(); }} />}
      {dialog === "password" && <PasswordDialog onClose={() => setDialog(null)} />}
    </div>
  );
}

function readOnlyReason(f: CourseFull, me: User): string {
  if (f.status === "submitted") return f.can.hod_approve
    ? "Waiting for your review as HOD. Approve it or send it back with a note."
    : "Submitted: waiting for the HOD. It cannot be edited while in review.";
  if (f.status === "hod_approved") return f.can.approve
    ? "Approved by the HOD and waiting for your final approval."
    : "Approved by the HOD: waiting for the dean. It cannot be edited while in review.";
  if (f.status === "approved") return f.can.reopen
    ? "Approved. To change it, start a new version; this one stays in force until the new one is approved."
    : "Approved. This is the version used in handbooks.";
  return f.owner_id === me.id ? "You cannot edit this course." : `Read only: this course belongs to ${f.owner_name || "nobody yet"}.`;
}

function RevisionForm({ busy, onSend }: { busy: boolean; onSend: (comment: string) => void }) {
  const [text, setText] = useState("");
  return (
    <form className="stack" onSubmit={(e) => { e.preventDefault(); onSend(text); }}>
      <p className="hint">The author sees this note in the course history. Be specific about what to change.</p>
      <textarea autoFocus rows={5} aria-label="What needs to change" value={text} onChange={(e) => setText(e.target.value)} />
      <button className="btn primary" disabled={busy || !text.trim()}>Send back</button>
    </form>
  );
}

function Checks({ issues, structure }: { issues: Issue[]; structure: StructureProblem[] }) {
  const errs = issues.filter((i) => i.severity === "error");
  const warns = issues.filter((i) => i.severity === "warning");
  const jump = (where: string) => {
    const s = sectionOf(where);
    const id = s === "modules" || s === "exercises" ? "content" : s;
    document.getElementById(`sec-${SECTIONS.some(([k]) => k === id) ? id : "basics"}`)?.scrollIntoView({ behavior: "smooth" });
  };
  const item = (s: { where: string; message: string }, i: number) =>
    <li key={i}><button className="linkish" onClick={() => jump(s.where)}>{s.where}</button>: {s.message}</li>;
  return (
    <section className="panel" aria-label="Checks">
      <h2>Checks</h2>
      {!issues.length && !structure.length && <p className="good">All institutional rules pass.</p>}
      {structure.length > 0 && <><h3 className="bad">Cannot save yet</h3><ul>{structure.map(item)}</ul></>}
      {errs.length > 0 && <><h3 className="bad">Errors (block submitting)</h3><ul>{errs.map(item)}</ul></>}
      {warns.length > 0 && <><h3 className="warn">Warnings</h3><ul>{warns.map(item)}</ul></>}
      <nav className="toc">{SECTIONS.map(([id, label]) => <a key={id} href={`#sec-${id}`}>{label}</a>)}</nav>
    </section>
  );
}

/** Owner and department; administrators can reassign them. */
function Record({ full, me, onChanged, onError }: {
  full: CourseFull; me: User; onChanged: (f: CourseFull) => void; onError: (m: string) => void;
}) {
  const [users, setUsers] = useState<User[]>([]);
  useEffect(() => { if (me.role === "admin") api.users().then(setUsers).catch(() => {}); }, [me.role]);
  const code = full.course.course_code;
  const change = (patch: { department?: string; owner_id?: string }) =>
    api.setMeta(code, patch).then(onChanged).catch((e) => onError(e.message));
  return (
    <section className="panel" aria-label="Course record">
      <h2>Record</h2>
      {me.role === "admin" ? <>
        <label className="field"><span>Owner</span>
          <select value={full.owner_id ?? ""} onChange={(e) => e.target.value && change({ owner_id: e.target.value })}>
            {!full.owner_id && <option value="">(nobody)</option>}
            {users.filter((u) => !u.disabled).map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select></label>
        <label className="field"><span>Department</span>
          <input defaultValue={full.department} key={full.department}
            onBlur={(e) => e.target.value.trim() !== full.department && change({ department: e.target.value.trim() })} /></label>
      </> : <p>Owner: <b>{full.owner_name || "nobody"}</b><br />Department: <b>{full.department || "none"}</b></p>}
      <p className="muted">
        {full.version ? `Submitted versions: ${full.version}` : "Not submitted yet"}
        {full.approved_version != null && ` · v${full.approved_version} approved`}
      </p>
    </section>
  );
}

function History({ code, tick }: { code: string; tick: number }) {
  const [h, setH] = useState<{ events: HistoryEvent[]; versions: VersionInfo[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.history(code).then(setH).catch((e) => setError(e.message)); }, [code, tick]);
  if (error) return <section className="panel"><h2>History</h2><p className="bad">{error}</p></section>;
  if (!h) return null;
  return (
    <section className="panel" aria-label="History">
      <h2>History</h2>
      <ol className="history">
        {[...h.events].reverse().map((e, i) => (
          <li key={i}>
            <b>{e.user_name}</b> {EVENT_LABELS[e.action] ?? e.action}{e.version ? ` v${e.version}` : ""}
            <div className="muted">{new Date(e.at).toLocaleString()}</div>
            {e.comment && <blockquote>{e.comment}</blockquote>}
          </li>
        ))}
      </ol>
      {h.versions.length > 0 && <>
        <h3>Frozen versions</h3>
        <ul className="versions">
          {h.versions.map((v) => (
            <li key={v.version}>
              <button className="linkish" onClick={() => download(`/api/courses/${encodeURIComponent(code)}/versions/${v.version}/docx`, `${code}_v${v.version}.docx`)}>
                v{v.version} DOCX</button>
              <span className="muted"> {new Date(v.created_at).toLocaleDateString()} · {v.created_by}</span>
            </li>
          ))}
        </ul>
      </>}
    </section>
  );
}

function Handbook({ onError }: { onError: (m: string | null) => void }) {
  const [programmes, setProgrammes] = useState<string[]>([]);
  const [programme, setProgramme] = useState("");
  const [year, setYear] = useState(academicYear());
  const [preview, setPreview] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const load = () => api.programmes().then((p) => { setProgrammes(p); setProgramme((x) => x || p[0] || ""); }).catch(() => {});
  useEffect(() => { load(); }, []);

  async function go() {
    onError(null); setResult(null);
    try {
      const q = new URLSearchParams({ programme, year, include_unapproved: String(preview) });
      const h = await download(`/api/handbook?${q}`, `Handbook_${programme}_${year}.docx`);
      const missing = h.get("X-Unapproved-Courses");
      const errs = h.get("X-Excluded-Courses");
      setResult([missing && `Not approved yet, so left out: ${missing.split(",").join(", ")}`,
                 errs && `Left out (errors): ${errs.split(",").join(", ")}`].filter(Boolean).join(". ")
                || (preview ? "Preview with current drafts." : "All courses included."));
    } catch (e) { onError((e as Error).message); }
  }

  return (
    <div className="handbook card">
      <h2>Programme handbook</h2>
      <label className="field"><span>Programme</span>
        <select value={programme} onFocus={load} onChange={(e) => setProgramme(e.target.value)}>
          {programmes.map((p) => <option key={p}>{p}</option>)}
        </select>
      </label>
      <label className="field"><span>Academic year</span><input value={year} onChange={(e) => setYear(e.target.value)} /></label>
      <label className="check"><input type="checkbox" checked={preview} onChange={(e) => setPreview(e.target.checked)} /> Preview with unapproved drafts</label>
      <button className="btn primary" disabled={!programme} onClick={go}>Generate handbook</button>
      {result && <p className="muted">{result}</p>}
    </div>
  );
}
