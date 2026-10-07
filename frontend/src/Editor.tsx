// The course form. Every edit produces a new Course via onChange; nothing is saved here.
import type { ReactNode } from "react";
import { parseProgrammes, renumber, replaceAt, SEMESTERS } from "./courseops";
import { Area, Num, RowTools, Section, StringList, Text } from "./fields";
import type { Course, Exercise, ExerciseItem, Hours, Module, Table } from "./types";

const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
const arabic = (i: number) => `${i + 1}.`;
const letter = (i: number) => `${String.fromCharCode(97 + i)}.`;

export const SECTIONS: [string, string][] = [
  ["basics", "Course"], ["hours", "Hours & marks"], ["overview", "Overview"], ["objectives", "Objectives"],
  ["outcomes", "Outcomes"], ["content", "Content"], ["books", "Books & resources"],
];

export function Editor({ course: c, onChange, counts }: {
  course: Course; onChange: (c: Course) => void; counts: Record<string, number>;
}) {
  const set = <K extends keyof Course>(k: K, v: Course[K]) => onChange({ ...c, [k]: v });
  const setHours = (k: keyof Hours, v: number | null) => set("hours", { ...c.hours, [k]: v ?? 0 });
  const lab = c.kind === "laboratory";

  return (
    <div className="editor">
      <Section id="basics" title="Course" count={counts.basics}>
        <div className="grid">
          <Text label="Course code" value={c.course_code} placeholder="e.g. MTH101" onChange={(v) => set("course_code", v)} />
          <Text label="Course title" wide value={c.course_title} onChange={(v) => set("course_title", v)} />
          <Text label="Category" value={c.category} placeholder="Foundation / Core / Elective" onChange={(v) => set("category", v)} />
          <label className="field">
            <span>Type</span>
            <select value={c.kind} onChange={(e) => set("kind", e.target.value as Course["kind"])}>
              <option value="theory">Theory (modules)</option>
              <option value="laboratory">Laboratory (exercises)</option>
            </select>
          </label>
          <Text label="Prerequisite" wide value={c.prerequisite} placeholder="Leave blank for none" onChange={(v) => set("prerequisite", v)} />
        </div>
        <h3>Offered to</h3>
        <p className="hint">The same course can sit in different semesters for different programmes.</p>
        {c.offerings.map((o, i) => (
          <div className="list-row" key={i}>
            <select aria-label="Semester" value={o.semester}
              onChange={(e) => set("offerings", replaceAt(c.offerings, i, { ...o, semester: e.target.value }))}>
              {SEMESTERS.map((s) => <option key={s} value={s}>{s} Semester</option>)}
            </select>
            <ProgrammesInput value={o.programmes}
              onChange={(p) => set("offerings", replaceAt(c.offerings, i, { ...o, programmes: p }))} />
            <RowTools list={c.offerings} i={i} set={(l) => set("offerings", l)} what="offering" />
          </div>
        ))}
        <button type="button" className="add"
          onClick={() => set("offerings", [...c.offerings, { semester: "I", programmes: [] }])}>+ Add semester</button>
      </Section>

      <Section id="hours" title="Hours & marks" count={counts.hours}>
        <div className="grid tight">
          <Num label="L / week" value={c.hours.lecture} onChange={(v) => setHours("lecture", v)} />
          <Num label="T / week" value={c.hours.tutorial} onChange={(v) => setHours("tutorial", v)} />
          <Num label="P / week" value={c.hours.practical} onChange={(v) => setHours("practical", v)} />
          <Num label="Credits" value={c.hours.credits} onChange={(v) => setHours("credits", v)} />
        </div>
        <div className="grid tight">
          <Num label="Contact classes" value={c.hours.contact_classes} onChange={(v) => setHours("contact_classes", v)} />
          <Num label="Tutorial classes" value={c.hours.tutorial_classes} onChange={(v) => setHours("tutorial_classes", v)} />
          <Num label="Practical classes" value={c.hours.practical_classes} onChange={(v) => setHours("practical_classes", v)} />
          <Num label="Total classes" value={c.hours.total_classes} onChange={(v) => setHours("total_classes", v)} />
        </div>
        <div className="grid tight">
          <Num label="CIA" value={c.marks.cia} onChange={(v) => set("marks", { ...c.marks, cia: v ?? 0 })} />
          <Num label="SEE" value={c.marks.see} onChange={(v) => set("marks", { ...c.marks, see: v ?? 0 })} />
          <Num label="Total marks" value={c.marks.total} onChange={(v) => set("marks", { ...c.marks, total: v ?? 0 })} />
        </div>
      </Section>

      <Section id="overview" title="I. Course overview" count={counts.overview}>
        <Area rows={5} label="Course overview" value={c.overview} onChange={(v) => set("overview", v)}
          placeholder="What the course is about and why it matters (one paragraph)." />
      </Section>

      <Section id="objectives" title="II. Course objectives" count={counts.objectives}>
        <p className="hint">“The students will try to learn:” is added by the template.</p>
        <StringList items={c.objectives} onChange={(l) => set("objectives", l)} mark={(i) => `${ROMAN[i] ?? i + 1}.`}
          placeholder="e.g. The rank of a matrix and the solution of linear systems." what="objective" rows={2} />
      </Section>

      <Section id="outcomes" title="III. Course outcomes" count={counts.outcomes}>
        <p className="hint">Start each outcome with one measurable action verb. Numbering is automatic.</p>
        <StringList items={c.outcomes.map((o) => o.text)}
          onChange={(l) => set("outcomes", renumber(l.map((text) => ({ code: "", text }))))}
          mark={(i) => `CO ${i + 1}`} placeholder="e.g. Determine the rank of a matrix …" what="outcome" rows={2} />
      </Section>

      <Section id="content" title={lab ? "IV. Exercises" : "IV. Modules"}
        count={(counts.modules ?? 0) + (counts.exercises ?? 0) || undefined}>
        {lab
          ? <Exercises list={c.exercises} onChange={(l) => set("exercises", l)} />
          : <Modules list={c.modules} onChange={(l) => set("modules", l)} />}
      </Section>

      <Section id="books" title="V–VIII. Books & resources" count={counts.books}>
        <h3>V. Text books</h3>
        <StringList items={c.text_books} onChange={(l) => set("text_books", l)} mark={arabic}
          placeholder="Author, Title, Publisher, edition, year." what="text book" />
        <h3>VI. Reference books</h3>
        <StringList items={c.reference_books} onChange={(l) => set("reference_books", l)} mark={arabic}
          placeholder="Author, Title, Publisher, edition, year." what="reference book" />
        <h3>VII. Electronic resources</h3>
        <StringList items={c.electronic_resources} onChange={(l) => set("electronic_resources", l)} mark={arabic}
          placeholder="https://…" what="resource" />
        <h3>VIII. Materials online</h3>
        <StringList items={c.materials_online} onChange={(l) => set("materials_online", l)} mark={arabic}
          placeholder="e.g. Lecture notes" what="material" />
      </Section>
    </div>
  );
}

/** Comma-separated programmes. Kept as raw text while typing so commas and spaces don't vanish. */
function ProgrammesInput({ value, onChange }: { value: string[]; onChange: (p: string[]) => void }) {
  return (
    <input aria-label="Programmes" className="grow" defaultValue={value.join(", ")}
      key={value.join("|")}
      placeholder="Programmes, comma separated: CSE, ECE, CSE (AI & ML)"
      onBlur={(e) => onChange(parseProgrammes(e.target.value))} />
  );
}

function Modules({ list, onChange }: { list: Module[]; onChange: (l: Module[]) => void }) {
  return (
    <div className="stack">
      {list.map((m, i) => {
        const setM = (patch: Partial<Module>) => onChange(replaceAt(list, i, { ...m, ...patch }));
        return (
          <div className="sub" key={i}>
            <div className="sub-head">
              <strong>Module {ROMAN[i] ?? i + 1}</strong>
              <RowTools list={list} i={i} set={onChange} what="module" />
            </div>
            <div className="grid">
              <Text label="Title" wide value={m.title} placeholder="e.g. Matrices" onChange={(v) => setM({ title: v })} />
              <Num label="Hours" optional value={m.hours} onChange={(v) => setM({ hours: v })} />
            </div>
            {m.parts.map((p, j) => (
              <div className="list-row" key={j}>
                <input className="label-in" aria-label="Paragraph label" value={p.label ?? ""} placeholder="Label (optional)"
                  onChange={(e) => setM({ parts: replaceAt(m.parts, j, { ...p, label: e.target.value || null }) })} />
                <Area rows={3} label={`Module ${i + 1} paragraph ${j + 1}`} value={p.text}
                  placeholder="Topics, separated by commas or semicolons."
                  onChange={(v) => setM({ parts: replaceAt(m.parts, j, { ...p, text: v }) })} />
                <RowTools list={m.parts} i={j} set={(l) => setM({ parts: l })} what="paragraph" />
              </div>
            ))}
            <button type="button" className="add" onClick={() => setM({ parts: [...m.parts, { text: "" }] })}>+ Add paragraph</button>
          </div>
        );
      })}
      <button type="button" className="add" onClick={() => onChange([...list, { title: "", hours: null, parts: [{ text: "" }] }])}>
        + Add module
      </button>
    </div>
  );
}

function Exercises({ list, onChange }: { list: Exercise[]; onChange: (l: Exercise[]) => void }) {
  return (
    <div className="stack">
      {list.map((ex, i) => {
        const setEx = (patch: Partial<Exercise>) => onChange(replaceAt(list, i, { ...ex, ...patch }));
        return (
          <div className="sub" key={i}>
            <div className="sub-head">
              <strong>Exercise {i + 1}</strong>
              <RowTools list={list} i={i} set={onChange} what="exercise" />
            </div>
            <Text label="Title" wide value={ex.title} placeholder="e.g. Stacks and Queues" onChange={(v) => setEx({ title: v })} />
            {ex.items.map((it, j) => (
              <Item key={j} n={j} item={it} onChange={(v) => setEx({ items: replaceAt(ex.items, j, v) })}
                tools={<RowTools list={ex.items} i={j} set={(l) => setEx({ items: l })} what="task" />} />
            ))}
            <button type="button" className="add" onClick={() => setEx({ items: [...ex.items, { text: "", subitems: [] }] })}>+ Add task</button>
          </div>
        );
      })}
      <button type="button" className="add" onClick={() => onChange([...list, { title: "", items: [{ text: "", subitems: [] }] }])}>
        + Add exercise
      </button>
    </div>
  );
}

function Item({ n, item, onChange, tools }: {
  n: number; item: ExerciseItem; onChange: (i: ExerciseItem) => void; tools: ReactNode;
}) {
  return (
    <div className="item">
      <div className="list-row">
        <span className="mark">{n + 1}.</span>
        <Area rows={2} label={`Task ${n + 1}`} value={item.text} placeholder="Task statement (may be blank if it only has parts a, b, c…)"
          onChange={(v) => onChange({ ...item, text: v })} />
        {tools}
      </div>
      <div className="indent">
        {item.table
          ? <TableEditor table={item.table} onChange={(t) => onChange({ ...item, table: t })} />
          : <button type="button" className="add"
              onClick={() => onChange({ ...item, table: { header: ["Name", "Type"], rows: [["", ""]] } })}>+ Add table</button>}
        <StringList items={item.subitems} onChange={(l) => onChange({ ...item, subitems: l })} mark={letter}
          placeholder="Sub-task" what="sub-task" />
      </div>
    </div>
  );
}

function TableEditor({ table, onChange }: { table: Table | null; onChange: (t: Table | null) => void }) {
  if (!table) return null;
  const cols = table.header.length;
  const setCell = (r: number, k: number, v: string) =>
    onChange({ ...table, rows: replaceAt(table.rows, r, replaceAt(table.rows[r], k, v)) });
  return (
    <div className="table-ed">
      <table>
        <thead>
          <tr>{table.header.map((h, k) => (
            <th key={k}><input aria-label={`Column ${k + 1} heading`} value={h}
              onChange={(e) => onChange({ ...table, header: replaceAt(table.header, k, e.target.value) })} /></th>
          ))}<th /></tr>
        </thead>
        <tbody>
          {table.rows.map((row, r) => (
            <tr key={r}>
              {Array.from({ length: cols }, (_, k) => (
                <td key={k}><input aria-label={`Row ${r + 1} column ${k + 1}`} value={row[k] ?? ""}
                  onChange={(e) => setCell(r, k, e.target.value)} /></td>
              ))}
              <td><button type="button" className="danger" aria-label={`Remove row ${r + 1}`}
                onClick={() => onChange({ ...table, rows: table.rows.filter((_, x) => x !== r) })}>✕</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row">
        <button type="button" className="add" onClick={() => onChange({ ...table, rows: [...table.rows, Array(cols).fill("")] })}>+ Row</button>
        <button type="button" className="add"
          onClick={() => onChange({ header: [...table.header, ""], rows: table.rows.map((r) => [...r, ""]) })}>+ Column</button>
        <button type="button" className="add danger" onClick={() => onChange(null)}>Remove table</button>
      </div>
    </div>
  );
}
