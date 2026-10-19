// Mirrors backend/src/acaddoc/schema.py. The backend is the authority; keep in step.

export type Kind = "theory" | "laboratory";

export interface SemesterOffering { semester: string; programmes: string[] }
export interface Marks { cia: number; see: number; total: number }
export interface Hours {
  lecture: number; tutorial: number; practical: number; credits: number;
  contact_classes: number; tutorial_classes: number; practical_classes: number; total_classes: number;
}
export interface Part { text: string; label?: string | null }
export interface Module { title: string; hours?: number | null; parts: Part[] }
export interface Table { header: string[]; rows: string[][] }
export interface ExerciseItem { text: string; table?: Table | null; subitems: string[] }
export interface Exercise { title: string; items: ExerciseItem[] }
export type BloomLevel = "remember" | "understand" | "apply" | "analyse" | "evaluate" | "create";

/** A course outcome; `po` is its row of the CO-PO matrix (programme outcome code -> 1..3). */
export interface Outcome { code: string; text: string; bloom?: BloomLevel | null; po: Record<string, number> }

export interface Course {
  course_code: string; course_title: string; kind: Kind; category: string;
  offerings: SemesterOffering[]; hours: Hours; marks: Marks; prerequisite: string;
  overview: string; objectives: string[]; outcomes: Outcome[]; po_programme: string;
  modules: Module[]; exercises: Exercise[];
  text_books: string[]; reference_books: string[]; electronic_resources: string[]; materials_online: string[];
}

export interface Issue { rule: string; severity: "error" | "warning"; where: string; message: string }
export interface StructureProblem { where: string; message: string }

export type Status = "draft" | "submitted" | "hod_approved" | "approved" | "revision_required";
export type Role = "admin" | "faculty" | "hod" | "dean";
export type Action = "submit" | "withdraw" | "hod_approve" | "approve" | "request_revision" | "reopen";

export interface User {
  id: string; username: string; display_name: string; role: Role; department: string; disabled: boolean; email: string;
}

export interface MailRow {
  id: number; created_at: string; to_addr: string; subject: string;
  status: "queued" | "sent" | "failed" | "not_configured"; error: string; sent_at: string | null;
}
export interface MailStatus {
  configured: boolean; host?: string; port?: number; security?: string; sender?: string;
  public_url: string; outbox: MailRow[];
}

/** Workflow facts the server keeps beside the content. */
export interface CourseMeta {
  department: string; owner_id: string | null; owner_name: string;
  status: Status; status_label: string; version: number; approved_version: number | null;
}

export interface CourseSummary extends CourseMeta {
  course_code: string; course_title: string; kind: Kind; updated_at: string;
  errors: number; warnings: number; awaiting_me: boolean;
}

export type Permissions = Record<"edit" | "delete" | Action, boolean>;

export interface ProgrammeOutcome { code: string; title: string; text: string }

/** The programme outcomes a course is mapped against: the programme's own, or the UGC LOCF default. */
export interface Framework {
  programme: string; source: "programme" | "locf"; name: string; source_label: string; outcomes: ProgrammeOutcome[];
}

export interface CourseFull extends CourseMeta {
  course: Course; updated_at: string; issues: Issue[]; can: Permissions;
  framework: Framework; bloom_suggestions: (BloomLevel | null)[];
}

export interface ProgrammeRecord { code: string; name: string; department: string; outcomes: ProgrammeOutcome[] }

export interface ProgrammeSummary {
  code: string; name: string; department: string; own: boolean; outcomes: number;
  updated_at: string; updated_by: string; courses: number; can_edit: boolean;
}

export interface ProgrammeDetail {
  code: string; record: ProgrammeRecord | null; framework: Framework; can_edit: boolean;
  courses: { course_code: string; course_title: string; status_label: string; mapped: boolean; levels: Record<string, number> }[];
  gaps: string[];
}

export interface HistoryEvent {
  at: string; user_name: string; action: string; from_status: Status | null; to_status: Status | null;
  version: number | null; comment: string;
}
export interface VersionInfo { version: number; created_at: string; created_by: string }
