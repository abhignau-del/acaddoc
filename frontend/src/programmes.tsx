// Programme outcomes (POs and PSOs): one list per programme, kept by an administrator or the HOD,
// and how the courses mapped to it cover each outcome.
import { useEffect, useState } from "react";
import { api } from "./api";
import { useSession } from "./auth";
import { move, nextOutcomeCode, removeAt, replaceAt, STRENGTH_LABELS } from "./courseops";
import { Modal } from "./people";
import type { ProgrammeDetail, ProgrammeOutcome, ProgrammeRecord, ProgrammeSummary } from "./types";

export function ProgrammesDialog({ onClose }: { onClose: () => void }) {
  const [list, setList] = useState<ProgrammeSummary[]>([]);
  const [code, setCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => api.programmeList().then((l) => { setList(l); setCode((c) => c ?? l[0]?.code ?? null); })
    .catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  return (
    <Modal title="Programme outcomes" onClose={onClose}>
      {error && <div className="alert" role="alert"><span>{error}</span></div>}
      <div className="prog-layout">
        <ul className="course-list" aria-label="Programmes">
          {list.map((p) => (
            <li key={p.code}>
              <button className={p.code === code ? "active" : ""} onClick={() => setCode(p.code)}>
                <span><b>{p.code}</b> {p.name}</span>
                <small>{p.own ? `${p.outcomes} outcomes` : "UGC LOCF default"} · {p.courses} course{p.courses === 1 ? "" : "s"} mapped</small>
              </button>
            </li>
          ))}
          {!list.length && <li className="muted">No programmes yet: they appear once a course is offered to one.</li>}
        </ul>
        {code && <ProgrammeEditor key={code} code={code} onSaved={load} />}
      </div>
    </Modal>
  );
}

function ProgrammeEditor({ code, onSaved }: { code: string; onSaved: () => void }) {
  const { user } = useSession();
  // a new programme set up by an HOD belongs to the HOD's department
  const blank: ProgrammeRecord = { code, name: "", department: user.role === "hod" ? user.department : "", outcomes: [] };
  const [detail, setDetail] = useState<ProgrammeDetail | null>(null);
  const [rec, setRec] = useState<ProgrammeRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  function take(d: ProgrammeDetail) {
    setDetail(d);
    setRec(d.record ?? blank);
  }
  useEffect(() => { api.programmeGet(code).then(take).catch((e) => setError(e.message)); }, [code]);
  if (!detail || !rec) return <div className="muted">Loading…</div>;

  const dirty = JSON.stringify(rec) !== JSON.stringify(detail.record ?? blank);
  const setOut = (outcomes: ProgrammeOutcome[]) => setRec({ ...rec, outcomes });
  async function save() {
    setError(null); setNote(null);
    try { take(await api.programmeSave(rec!)); setNote("Saved."); onSaved(); }
    catch (e) { setError((e as Error).message); }
  }
  async function fromLocf() {
    try { setOut((await api.locf()).outcomes); setNote("Started from the UGC LOCF graduate attributes. Edit them, then save."); }
    catch (e) { setError((e as Error).message); }
  }
  const cols = detail.framework.outcomes.map((o) => o.code);

  return (
    <div className="stack">
      {error && <div className="alert" role="alert"><span>{error}</span></div>}
      {note && <div className="note" role="status">{note}</div>}
      {!detail.can_edit && <p className="note"><span>Read only. An administrator or the HOD of the programme's department edits its outcomes.</span></p>}
      {detail.framework.source === "locf" && (
        <p className="note"><span>{code} has no outcomes of its own, so courses mapped to it use the UGC LOCF graduate attributes.</span></p>
      )}
      <fieldset className="plain stack" disabled={!detail.can_edit}>
        <div className="grid">
          <label className="field wide"><span>Programme name</span>
            <input value={rec.name} placeholder="e.g. B.Tech. Computer Science and Engineering"
              onChange={(e) => setRec({ ...rec, name: e.target.value })} /></label>
          <label className="field"><span>Department</span>
            <input value={rec.department} onChange={(e) => setRec({ ...rec, department: e.target.value })} /></label>
        </div>
        <h3>Outcomes</h3>
        {!rec.outcomes.length && (
          <div className="row">
            <button type="button" className="btn" onClick={fromLocf}>Start from the UGC LOCF graduate attributes</button>
            <span className="muted">or add your own below.</span>
          </div>
        )}
        <div className="list">
          {rec.outcomes.map((o, i) => (
            <div className="list-row" key={i}>
              <input className="code-in" aria-label={`Code of outcome ${i + 1}`} value={o.code}
                onChange={(e) => setOut(replaceAt(rec.outcomes, i, { ...o, code: e.target.value.toUpperCase().replace(/\s/g, "") }))} />
              <input className="label-in" aria-label={`Title of ${o.code}`} value={o.title} placeholder="Short title"
                onChange={(e) => setOut(replaceAt(rec.outcomes, i, { ...o, title: e.target.value }))} />
              <textarea rows={2} aria-label={`Text of ${o.code}`} value={o.text} placeholder="What graduates are able to do"
                onChange={(e) => setOut(replaceAt(rec.outcomes, i, { ...o, text: e.target.value }))} />
              <span className="rowtools">
                <button type="button" aria-label={`Move ${o.code} up`} disabled={i === 0} onClick={() => setOut(move(rec.outcomes, i, -1))}>↑</button>
                <button type="button" aria-label={`Move ${o.code} down`} disabled={i === rec.outcomes.length - 1} onClick={() => setOut(move(rec.outcomes, i, 1))}>↓</button>
                <button type="button" aria-label={`Remove ${o.code}`} className="danger" onClick={() => setOut(removeAt(rec.outcomes, i))}>✕</button>
              </span>
            </div>
          ))}
        </div>
        <div className="row">
          <button type="button" className="add" onClick={() => setOut([...rec.outcomes, { code: nextOutcomeCode(rec.outcomes, "PO"), title: "", text: "" }])}>+ Add PO</button>
          <button type="button" className="add" onClick={() => setOut([...rec.outcomes, { code: nextOutcomeCode(rec.outcomes, "PSO"), title: "", text: "" }])}>+ Add PSO</button>
        </div>
        {detail.can_edit && <div className="row">
          <button type="button" className="btn primary" disabled={!dirty || rec.outcomes.some((o) => !o.text.trim() || !o.code)} onClick={save}>Save outcomes</button>
          <span className="hint">Changing or removing a code flags courses still mapped to the old one.</span>
        </div>}
      </fieldset>

      <h3>How the courses cover them</h3>
      {!detail.courses.length ? <p className="muted">No course is mapped to {code}'s outcomes yet.</p> : (
        <div className="copo-wrap">
          <table className="copo">
            <thead><tr><th>Course</th>{cols.map((c) => <th key={c} className={detail.gaps.includes(c) ? "gap" : ""}>{c}</th>)}</tr></thead>
            <tbody>
              {detail.courses.map((r) => (
                <tr key={r.course_code}>
                  <th title={`${r.course_title} (${r.status_label})`}>{r.course_code}</th>
                  {cols.map((c) => <td key={c}><span className={`cell s${r.levels[c] ?? 0}`}>{r.levels[c] ?? "–"}</span></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="hint">Each cell is the rounded average of the course's CO links (3 = {STRENGTH_LABELS[3]}, 2 = {STRENGTH_LABELS[2]},
        1 = {STRENGTH_LABELS[1]}). Current drafts are included.</p>
      {detail.gaps.length > 0 && detail.courses.length > 0 &&
        <p className="warn">Not addressed by any course: {detail.gaps.join(", ")}.</p>}
      {detail.courses.some((r) => !r.mapped) &&
        <p className="muted">Not mapped yet: {detail.courses.filter((r) => !r.mapped).map((r) => r.course_code).join(", ")}.</p>}
    </div>
  );
}
