import { describe, expect, it } from "vitest";
import {
  ACTION_UI, EVENT_LABELS, filterCourses,
  academicYear, clearDraft, countBySection, emptyCourse, loadDraft, move, parseProgrammes, removeAt, renumber,
  saveDraft, sectionOf, tidy,
} from "./courseops";
import type { CourseSummary, User } from "./types";

class MemoryStorage implements Storage {
  private m = new Map<string, string>();
  get length() { return this.m.size; }
  clear() { this.m.clear(); }
  getItem(k: string) { return this.m.get(k) ?? null; }
  key(i: number) { return [...this.m.keys()][i] ?? null; }
  removeItem(k: string) { this.m.delete(k); }
  setItem(k: string, v: string) { this.m.set(k, v); }
}

describe("emptyCourse", () => {
  it("starts a theory course with 5 modules and 6 numbered outcomes", () => {
    const c = emptyCourse("theory");
    expect(c.modules).toHaveLength(5);
    expect(c.exercises).toHaveLength(0);
    expect(c.outcomes.map((o) => o.code)).toEqual(["CO1", "CO2", "CO3", "CO4", "CO5", "CO6"]);
  });
  it("starts a lab with exercises and practical hours only", () => {
    const c = emptyCourse("laboratory");
    expect(c.modules).toHaveLength(0);
    expect(c.exercises).toHaveLength(1);
    expect(c.hours.lecture).toBe(0);
    expect(c.hours.total_classes).toBe(c.hours.practical_classes);
  });
});

describe("list editing", () => {
  it("moves within bounds and ignores moves past the ends", () => {
    expect(move(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
    expect(move(["a", "b", "c"], 2, -1)).toEqual(["a", "c", "b"]);
    const l = ["a", "b"];
    expect(move(l, 0, -1)).toBe(l);
    expect(move(l, 1, 1)).toBe(l);
  });
  it("removes by index", () => expect(removeAt(["a", "b", "c"], 1)).toEqual(["a", "c"]));
  it("renumbers outcomes after a removal", () => {
    const out = renumber(removeAt(renumber([{ code: "", text: "x" }, { code: "", text: "y" }, { code: "", text: "z" }]), 0));
    expect(out).toEqual([{ code: "CO1", text: "y" }, { code: "CO2", text: "z" }]);
  });
});

describe("parseProgrammes", () => {
  it("splits on commas and keeps ampersands and brackets", () => {
    expect(parseProgrammes(" CSE, CSE (AI & ML) ,, ECE ")).toEqual(["CSE", "CSE (AI & ML)", "ECE"]);
  });
});

describe("sectionOf / countBySection", () => {
  it("maps backend locations to editor sections", () => {
    expect(sectionOf("modules")).toBe("modules");
    expect(sectionOf("outcomes[3]")).toBe("outcomes");
    expect(sectionOf("hours.credits")).toBe("hours");
    expect(sectionOf("marks")).toBe("hours");
    expect(sectionOf("course_code")).toBe("basics");
    expect(sectionOf("offerings.0.programmes")).toBe("basics");
    expect(sectionOf("electronic_resources[2]")).toBe("books");
    expect(sectionOf("references")).toBe("books");
  });
  it("counts issues and structure problems together", () => {
    const counts = countBySection(
      [{ rule: "A", severity: "error", where: "marks", message: "" },
       { rule: "B", severity: "warning", where: "hours", message: "" }],
      [{ where: "outcomes.1.text", message: "" }],
    );
    expect(counts).toEqual({ hours: 2, outcomes: 1 });
  });
});

describe("tidy", () => {
  it("drops blank rows, upper-cases the code and renumbers outcomes", () => {
    const c = emptyCourse("theory");
    c.course_code = " mth101 ";
    c.objectives = ["one", " ", "two"];
    c.outcomes = renumber([{ code: "", text: "" }, { code: "", text: "Apply x." }]);
    c.modules[0].parts = [{ text: "  " }, { text: "Topic" }];
    c.text_books = ["", "Book"];
    const t = tidy(c);
    expect(t.course_code).toBe("MTH101");
    expect(t.objectives).toEqual(["one", "two"]);
    expect(t.outcomes).toEqual([{ code: "CO1", text: "Apply x." }]);
    expect(t.modules[0].parts).toEqual([{ text: "Topic" }]);
    expect(t.text_books).toEqual(["Book"]);
  });
  it("does not change the input", () => {
    const c = emptyCourse("theory");
    const before = JSON.stringify(c);
    tidy(c);
    expect(JSON.stringify(c)).toBe(before);
  });
});

describe("drafts", () => {
  it("round-trips per course and clears", () => {
    const s = new MemoryStorage();
    const c = emptyCourse("theory"); c.course_title = "Draft";
    saveDraft("MTH101", c, s);
    saveDraft(null, emptyCourse("laboratory"), s);
    expect(loadDraft("MTH101", s)?.course.course_title).toBe("Draft");
    expect(loadDraft(null, s)?.course.kind).toBe("laboratory");
    clearDraft("MTH101", s);
    expect(loadDraft("MTH101", s)).toBeNull();
  });
  it("survives storage that throws or holds junk", () => {
    const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("full"); } } as unknown as Storage;
    expect(() => saveDraft("X", emptyCourse("theory"), broken)).not.toThrow();
    expect(loadDraft("X", broken)).toBeNull();
    const s = new MemoryStorage(); s.setItem("acaddoc.draft.X", "{not json");
    expect(loadDraft("X", s)).toBeNull();
  });
});

describe("academicYear", () => {
  it("rolls over in June", () => {
    expect(academicYear(new Date(2026, 4, 31))).toBe("2025-26");
    expect(academicYear(new Date(2026, 5, 1))).toBe("2026-27");
    expect(academicYear(new Date(2099, 11, 1))).toBe("2099-00");
  });
});


describe("workflow helpers", () => {
  const me: User = { id: "u1", username: "fac", display_name: "Fac", role: "faculty", department: "CSE", disabled: false };
  const row = (code: string, owner: string | null, awaiting = false): CourseSummary => ({
    course_code: code, course_title: code, kind: "theory", updated_at: "", errors: 0, warnings: 0, awaiting_me: awaiting,
    department: "CSE", owner_id: owner, owner_name: "", status: "draft", status_label: "Draft", version: 0, approved_version: null,
  });
  const list = [row("A1", "u1"), row("B1", "u2", true), row("C1", null)];

  it("filters by owner and by review queue", () => {
    expect(filterCourses(list, "all", me).map((c) => c.course_code)).toEqual(["A1", "B1", "C1"]);
    expect(filterCourses(list, "mine", me).map((c) => c.course_code)).toEqual(["A1"]);
    expect(filterCourses(list, "review", me).map((c) => c.course_code)).toEqual(["B1"]);
  });

  it("has a button for every server action and a label for every event", () => {
    const actions = ["submit", "withdraw", "hod_approve", "approve", "request_revision", "reopen"];
    expect(ACTION_UI.map((a) => a.action).sort()).toEqual([...actions].sort());
    for (const a of [...actions, "create", "reassign"]) expect(EVENT_LABELS[a]).toBeTruthy();
    expect(ACTION_UI.find((a) => a.action === "request_revision")?.comment).toBe(true);
  });
});
