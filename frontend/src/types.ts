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
export interface Outcome { code: string; text: string }

export interface Course {
  course_code: string; course_title: string; kind: Kind; category: string;
  offerings: SemesterOffering[]; hours: Hours; marks: Marks; prerequisite: string;
  overview: string; objectives: string[]; outcomes: Outcome[];
  modules: Module[]; exercises: Exercise[];
  text_books: string[]; reference_books: string[]; electronic_resources: string[]; materials_online: string[];
}

export interface Issue { rule: string; severity: "error" | "warning"; where: string; message: string }
export interface StructureProblem { where: string; message: string }

export interface CourseSummary {
  course_code: string; course_title: string; kind: Kind; updated_at: string; errors: number; warnings: number;
}
