// Pure helpers for the editor: no React, no network. Tested in courseops.test.ts.
import type {
  Action, BloomLevel, Course, CourseSummary, Framework, Issue, Kind, Outcome, ProgrammeOutcome, Role, StructureProblem, User,
} from "./types";

export const SEMESTERS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"];

export function emptyCourse(kind: Kind): Course {
  const lab = kind === "laboratory";
  return {
    course_code: "", course_title: "", kind, category: "Core",
    offerings: [{ semester: "I", programmes: [] }],
    hours: {
      lecture: lab ? 0 : 3, tutorial: 0, practical: lab ? 2 : 0, credits: lab ? 1 : 3,
      contact_classes: lab ? 0 : 48, tutorial_classes: 0, practical_classes: lab ? 36 : 0, total_classes: lab ? 36 : 48,
    },
    marks: { cia: 40, see: 60, total: 100 },
    prerequisite: "", overview: "",
    objectives: ["", "", "", ""],
    outcomes: renumber(Array.from({ length: 6 }, () => ({ code: "", text: "", bloom: null, po: {} }))),
    po_programme: "",
    modules: lab ? [] : Array.from({ length: 5 }, () => ({ title: "", hours: null, parts: [{ text: "" }] })),
    exercises: lab ? [{ title: "", items: [{ text: "", subitems: [] }] }] : [],
    text_books: [""], reference_books: [], electronic_resources: [], materials_online: [],
  };
}

/** The system numbers outcomes; faculty never type "CO3". */
export function renumber(outcomes: Outcome[]): Outcome[] {
  return outcomes.map((o, i) => ({ ...o, code: `CO${i + 1}` }));
}

export function move<T>(list: T[], i: number, by: -1 | 1): T[] {
  const j = i + by;
  if (j < 0 || j >= list.length) return list;
  const out = list.slice();
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

export function removeAt<T>(list: T[], i: number): T[] {
  return list.filter((_, k) => k !== i);
}

export function replaceAt<T>(list: T[], i: number, value: T): T[] {
  return list.map((x, k) => (k === i ? value : x));
}

/** "CSE, CSE (AI & ML) , ECE" -> ["CSE", "CSE (AI & ML)", "ECE"] */
export function parseProgrammes(text: string): string[] {
  return text.split(",").map((s) => s.trim()).filter(Boolean);
}

/** Which editor section a backend location belongs to ("modules[2]", "hours.credits", "marks"). */
export function sectionOf(where: string): string {
  const head = where.split(/[.[]/)[0];
  if (head === "marks") return "hours";
  if (head === "course_code" || head === "course_title" || head === "category" || head === "kind" ||
      head === "prerequisite" || head === "offerings") return "basics";
  if (head === "references") return "books";
  if (head === "copo" || head === "po_programme") return "copo";
  if (["text_books", "reference_books", "electronic_resources", "materials_online"].includes(head)) return "books";
  return head;
}

export function countBySection(issues: Issue[], structure: StructureProblem[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const x of [...issues, ...structure]) {
    const s = sectionOf(x.where);
    out[s] = (out[s] ?? 0) + 1;
  }
  return out;
}

/** Remove blank list entries before saving, so an empty "add" row never reaches a document. */
export function tidy(c: Course): Course {
  const keep = (xs: string[]) => xs.map((s) => s.trim()).filter(Boolean);
  return {
    ...c,
    course_code: c.course_code.trim().toUpperCase(),
    objectives: keep(c.objectives),
    outcomes: renumber(c.outcomes.filter((o) => o.text.trim())),
    modules: c.modules.map((m) => ({ ...m, parts: m.parts.filter((p) => p.text.trim()) })),
    exercises: c.exercises.map((e) => ({
      ...e, items: e.items.map((it) => ({ ...it, subitems: keep(it.subitems) })),
    })),
    text_books: keep(c.text_books), reference_books: keep(c.reference_books),
    electronic_resources: keep(c.electronic_resources), materials_online: keep(c.materials_online),
  };
}

export function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

// --- unsaved drafts (per browser) ---------------------------------------------------

export interface Draft { course: Course; savedAt: string }

const key = (code: string | null) => `acaddoc.draft.${code ?? "(new)"}`;

export function saveDraft(code: string | null, course: Course, store: Storage | undefined = globalThis.localStorage): void {
  try { store?.setItem(key(code), JSON.stringify({ course, savedAt: new Date().toISOString() })); } catch { /* full or blocked */ }
}

export function loadDraft(code: string | null, store: Storage | undefined = globalThis.localStorage): Draft | null {
  try {
    const raw = store?.getItem(key(code));
    return raw ? (JSON.parse(raw) as Draft) : null;
  } catch { return null; }
}

export function clearDraft(code: string | null, store: Storage | undefined = globalThis.localStorage): void {
  try { store?.removeItem(key(code)); } catch { /* ignore */ }
}

export function academicYear(today = new Date()): string {
  const y = today.getMonth() >= 5 ? today.getFullYear() : today.getFullYear() - 1;   // years start in June
  return `${y}-${String((y + 1) % 100).padStart(2, "0")}`;
}

// --- people and workflow ------------------------------------------------------------


export const ROLE_LABELS: Record<Role, string> = { admin: "Administrator", faculty: "Faculty", hod: "HOD", dean: "Dean" };

/** Workflow buttons, in the order they appear. `comment` = the user must say why. */
export const ACTION_UI: { action: Action; label: string; primary?: boolean; comment?: boolean; confirm?: string }[] = [
  { action: "submit", label: "Submit for review", primary: true,
    confirm: "Submit for review? You cannot edit the course until it is sent back or approved." },
  { action: "hod_approve", label: "Approve (HOD)", primary: true },
  { action: "approve", label: "Final approval", primary: true,
    confirm: "Give final approval? This version becomes the one used in handbooks." },
  { action: "request_revision", label: "Send back for revision", comment: true },
  { action: "withdraw", label: "Withdraw submission" },
  { action: "reopen", label: "Start a new version",
    confirm: "Start a new version? The approved version stays in force until the new one is approved." },
];

export const EVENT_LABELS: Record<string, string> = {
  create: "created the course", submit: "submitted", withdraw: "withdrew the submission",
  hod_approve: "approved (HOD)", approve: "gave final approval", request_revision: "sent it back",
  reopen: "started a new version", reassign: "reassigned",
};

export type ListFilter = "all" | "mine" | "review";

export function filterCourses(list: CourseSummary[], filter: ListFilter, me: User): CourseSummary[] {
  if (filter === "mine") return list.filter((c) => c.owner_id === me.id);
  if (filter === "review") return list.filter((c) => c.awaiting_me);
  return list;
}

export const MAIL_STATUS_LABELS: Record<"queued" | "sent" | "failed" | "not_configured", string> = {
  queued: "Waiting", sent: "Sent", failed: "Failed", not_configured: "Not sent (email not set up)",
};

/** "#course=CSE205" -> "CSE205" (links in notification emails). */
export function courseFromHash(hash: string): string | null {
  const m = /^#course=([^&]+)$/.exec(hash);
  if (!m) return null;
  try { return decodeURIComponent(m[1]); } catch { return null; }
}

// --- course outcomes against programme outcomes ---------------------------------------

export const BLOOM: { id: BloomLevel; label: string }[] = [
  { id: "remember", label: "Remember" }, { id: "understand", label: "Understand" }, { id: "apply", label: "Apply" },
  { id: "analyse", label: "Analyse" }, { id: "evaluate", label: "Evaluate" }, { id: "create", label: "Create" },
];
export const STRENGTH_LABELS: Record<number, string> = { 1: "Low", 2: "Moderate", 3: "High" };

/** One click on a matrix cell: none -> 1 -> 2 -> 3 -> none. */
export function cycleStrength(v: number | undefined): number | undefined {
  return v === undefined ? 1 : v >= 3 ? undefined : v + 1;
}

/** Set one cell of an outcome's CO-PO row (undefined clears it). */
export function setLink(o: Outcome, code: string, v: number | undefined): Outcome {
  const po = { ...o.po };
  if (v === undefined) delete po[code]; else po[code] = v;
  return { ...o, po };
}

function codeKey(code: string): [string, number] {
  const m = /^([A-Z]+)(\d+)$/.exec(code);
  return m ? [m[1], Number(m[2])] : [code, 0];
}

/** Matrix columns: the framework's outcomes in order, then any other code the course still uses (as the server). */
export function copoColumns(c: Course, fw: Framework | null): string[] {
  const base = fw ? fw.outcomes.map((o) => o.code) : [];
  const extra = [...new Set(c.outcomes.flatMap((o) => Object.keys(o.po ?? {})))].filter((x) => !base.includes(x));
  extra.sort((a, b) => { const [pa, na] = codeKey(a); const [pb, nb] = codeKey(b); return pa < pb ? -1 : pa > pb ? 1 : na - nb; });
  return [...base, ...extra];
}

/** Whose outcomes the course is mapped to: po_programme, else the first programme offered (as the server). */
export function mappingProgramme(c: Course): string {
  if (c.po_programme) return c.po_programme;
  for (const o of c.offerings) if (o.programmes.length) return o.programmes[0];
  return "";
}

/** The next free code with this prefix: PO1..PO9 -> PO10; PSO1 -> PSO2. */
export function nextOutcomeCode(outcomes: ProgrammeOutcome[], prefix: string): string {
  const used = outcomes.map((o) => new RegExp(`^${prefix}(\\d+)$`).exec(o.code)).filter(Boolean).map((m) => Number(m![1]));
  return `${prefix}${used.length ? Math.max(...used) + 1 : 1}`;
}
