import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, download } from "./api";
import {
  academicYear, clearDraft, countBySection, emptyCourse, loadDraft, same, saveDraft, sectionOf, tidy,
  type Draft,
} from "./courseops";
import { Editor, SECTIONS } from "./Editor";
import type { Course, CourseSummary, Issue, Kind, StructureProblem } from "./types";

/** What is open in the editor. `code` is the saved code (null = not saved yet). */
interface Open { code: string | null; saved: Course | null; course: Course }

export default function App() {
  const [list, setList] = useState<CourseSummary[]>([]);
  const [open, setOpen] = useState<Open | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [structure, setStructure] = useState<StructureProblem[]>([]);
  const [restorable, setRestorable] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => api.list().then(setList).catch((e) => setError(String(e.message ?? e))), []);
  useEffect(() => { refresh(); }, [refresh]);

  const dirty = open ? !same(tidy(open.course), open.saved && tidy(open.saved)) : false;

  // Warn before closing the tab with unsaved work (the draft is also kept in this browser).
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    addEventListener("beforeunload", h);
    return () => removeEventListener("beforeunload", h);
  }, [dirty]);

  // Live validation of the draft, debounced; also keep the draft in this browser.
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!open) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      if (dirty) saveDraft(open.code, open.course);
      api.validate(tidy(open.course))
        .then((r) => { setIssues(r.issues); setStructure(r.structure); })
        .catch(() => { /* the save will report it */ });
    }, 350);
    return () => window.clearTimeout(timer.current);
  }, [open, dirty]);

  function confirmLeave(): boolean {
    return !dirty || confirm("You have unsaved changes. A copy stays in this browser. Leave this course?");
  }

  async function select(code: string) {
    if (open?.code === code || !confirmLeave()) return;
    setError(null); setNote(null);
    try {
      const r = await api.get(code);
      setOpen({ code, saved: r.course, course: r.course });
      setIssues(r.issues); setStructure([]);
      const d = loadDraft(code);
      setRestorable(d && !same(tidy(d.course), tidy(r.course)) ? d : null);
    } catch (e) { setError((e as Error).message); }
  }

  function create(kind: Kind) {
    if (!confirmLeave()) return;
    setError(null); setNote(null);
    const d = loadDraft(null);
    setOpen({ code: null, saved: null, course: emptyCourse(kind) });
    setRestorable(d);
  }

  async function save() {
    if (!open) return;
    setBusy(true); setError(null); setNote(null);
    const body = tidy(open.course);
    try {
      const r = open.code ? await api.update(open.code, body) : await api.create(body);
      clearDraft(open.code);
      setOpen({ code: r.course.course_code, saved: r.course, course: r.course });
      setIssues(r.issues); setRestorable(null);
      setNote(`Saved ${r.course.course_code}.`);
      refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
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

  return (
    <div className="app">
      <header>
        <h1>AcadDoc</h1>
        <span className="muted">Course content in, institutional documents out</span>
      </header>

      <aside>
        <div className="row">
          <button className="btn primary" onClick={() => create("theory")}>+ Theory course</button>
          <button className="btn" onClick={() => create("laboratory")}>+ Lab</button>
        </div>
        <ul className="course-list">
          {list.map((c) => (
            <li key={c.course_code}>
              <button className={open?.code === c.course_code ? "active" : ""} onClick={() => select(c.course_code)}>
                <span><b>{c.course_code}</b> {c.course_title}</span>
                <small>
                  {c.kind === "laboratory" ? "Lab" : "Theory"}
                  {c.errors ? <span className="bad"> · {c.errors} error{c.errors > 1 ? "s" : ""}</span> : <span className="good"> · ready</span>}
                  {c.warnings ? ` · ${c.warnings} warning${c.warnings > 1 ? "s" : ""}` : ""}
                </small>
              </button>
            </li>
          ))}
          {!list.length && <li className="muted">No courses yet.</li>}
        </ul>
        <Handbook onError={setError} />
      </aside>

      <main>
        {error && <div className="alert" role="alert"><span>{error}</span><button aria-label="Dismiss" onClick={() => setError(null)}>×</button></div>}
        {note && <div className="note" role="status">{note}</div>}

        {!open && <div className="empty">
          <h2>Open a course on the left, or start a new one.</h2>
          <p className="muted">You type the content. The institution’s Word template decides how it looks.</p>
        </div>}

        {open && <>
          {restorable && (
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
            <span className="spacer" />
            <button className="btn primary" disabled={busy || !dirty || structure.length > 0} onClick={save}
              title={structure.length ? "Fix the problems listed on the right first" : undefined}>
              {busy ? "Saving…" : "Save"}
            </button>
            <button className="btn" disabled={!open.code || dirty || errors > 0} onClick={() => docx()}
              title={dirty ? "Save first" : errors ? "Fix the errors first" : "Download the Word document"}>
              Generate DOCX
            </button>
            {open.code && !dirty && errors > 0 &&
              <button className="btn link" onClick={() => docx(true)}>Generate anyway</button>}
            {open.code && <button className="btn danger" onClick={remove}>Delete</button>}
          </div>

          <div className="workspace">
            <Editor course={open.course} counts={counts} onChange={(course) => setOpen({ ...open, course })} />
            <Checks issues={issues} structure={structure} />
          </div>
        </>}
      </main>
    </div>
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
  return (
    <aside className="checks" aria-label="Checks">
      <h2>Checks</h2>
      {!issues.length && !structure.length && <p className="good">All institutional rules pass.</p>}
      {structure.length > 0 && <>
        <h3 className="bad">Cannot save yet</h3>
        <ul>{structure.map((s, i) => <li key={i}><button className="linkish" onClick={() => jump(s.where)}>{s.where}</button>: {s.message}</li>)}</ul>
      </>}
      {errs.length > 0 && <>
        <h3 className="bad">Errors (block the document)</h3>
        <ul>{errs.map((s, i) => <li key={i}><button className="linkish" onClick={() => jump(s.where)}>{s.where}</button>: {s.message}</li>)}</ul>
      </>}
      {warns.length > 0 && <>
        <h3 className="warn">Warnings</h3>
        <ul>{warns.map((s, i) => <li key={i}><button className="linkish" onClick={() => jump(s.where)}>{s.where}</button>: {s.message}</li>)}</ul>
      </>}
      <nav className="toc">
        {SECTIONS.map(([id, label]) => <a key={id} href={`#sec-${id}`}>{label}</a>)}
      </nav>
    </aside>
  );
}

function Handbook({ onError }: { onError: (m: string | null) => void }) {
  const [programmes, setProgrammes] = useState<string[]>([]);
  const [programme, setProgramme] = useState("");
  const [year, setYear] = useState(academicYear());
  const [all, setAll] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const load = () => api.programmes().then((p) => { setProgrammes(p); setProgramme((x) => x || p[0] || ""); }).catch(() => {});
  useEffect(() => { load(); }, []);

  async function go() {
    onError(null); setResult(null);
    try {
      const q = new URLSearchParams({ programme, year, include_invalid: String(all) });
      const h = await download(`/api/handbook?${q}`, `Handbook_${programme}_${year}.docx`);
      const ex = h.get("X-Excluded-Courses");
      setResult(ex ? `Left out (errors): ${ex.split(",").join(", ")}` : "All courses included.");
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
      <label className="check"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Include courses with errors</label>
      <button className="btn primary" disabled={!programme} onClick={go}>Generate handbook</button>
      {result && <p className="muted">{result}</p>}
    </div>
  );
}
