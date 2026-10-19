import { describe, expect, it } from "vitest";
import {
  ACTION_UI, copoColumns, courseFromHash, cycleStrength, EVENT_LABELS, filterCourses, mappingProgramme, nextOutcomeCode,
  setLink,
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
    const out = renumber(removeAt(renumber([{ code: "", text: "x", po: {} }, { code: "", text: "y", po: {} }, { code: "", text: "z", po: {} }]), 0));
    expect(out).toEqual([{ code: "CO1", text: "y", po: {} }, { code: "CO2", text: "z", po: {} }]);
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
    c.outcomes = renumber([{ code: "", text: "", po: {} }, { code: "", text: "Apply x.", po: {} }]);
    c.modules[0].parts = [{ text: "  " }, { text: "Topic" }];
    c.text_books = ["", "Book"];
    const t = tidy(c);
    expect(t.course_code).toBe("MTH101");
    expect(t.objectives).toEqual(["one", "two"]);
    expect(t.outcomes).toEqual([{ code: "CO1", text: "Apply x.", po: {} }]);
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
  const me: User = { id: "u1", username: "fac", display_name: "Fac", role: "faculty", department: "CSE", disabled: false, email: "" };
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

describe("courseFromHash", () => {
  it("reads the course code from an email link", () => {
    expect(courseFromHash("#course=CSE205")).toBe("CSE205");
    expect(courseFromHash("#course=AB%2D1")).toBe("AB-1");
    expect(courseFromHash("#course=")).toBeNull();
    expect(courseFromHash("#other=CSE205")).toBeNull();
    expect(courseFromHash("#course=%E0%A4")).toBeNull();
    expect(courseFromHash("")).toBeNull();
  });
});

describe("CO-PO helpers", () => {
  const fw = {
    programme: "CSE", source: "programme" as const, name: "", source_label: "",
    outcomes: [{ code: "PO1", title: "", text: "a" }, { code: "PO2", title: "", text: "b" }, { code: "PSO1", title: "", text: "c" }],
  };

  it("cycles a cell none -> 1 -> 2 -> 3 -> none", () => {
    expect([undefined, 1, 2, 3].map(cycleStrength)).toEqual([1, 2, 3, undefined]);
  });

  it("sets and clears one link without touching the others", () => {
    const o = { code: "CO1", text: "x", po: { PO1: 3 } };
    expect(setLink(o, "PO2", 2).po).toEqual({ PO1: 3, PO2: 2 });
    expect(setLink(o, "PO1", undefined).po).toEqual({});
    expect(o.po).toEqual({ PO1: 3 });
  });

  it("orders columns like the server: framework first, then stray codes", () => {
    const c = emptyCourse("theory");
    c.outcomes = [{ code: "CO1", text: "x", po: { PO12: 1, PO1: 2, GA2: 1, PO10: 1 } }];
    expect(copoColumns(c, fw)).toEqual(["PO1", "PO2", "PSO1", "GA2", "PO10", "PO12"]);
    expect(copoColumns(c, null)).toEqual(["GA2", "PO1", "PO10", "PO12"]);
  });

  it("copes with drafts saved before outcomes had a po field", () => {
    const c = emptyCourse("theory");
    c.outcomes = [{ code: "CO1", text: "x" } as never];
    expect(copoColumns(c, fw)).toEqual(["PO1", "PO2", "PSO1"]);
    expect(setLink(c.outcomes[0], "PO1", 1).po).toEqual({ PO1: 1 });
  });

  it("finds the mapping programme as the server does", () => {
    const c = emptyCourse("theory");
    c.offerings = [{ semester: "I", programmes: [] }, { semester: "II", programmes: ["ECE", "CSE"] }];
    expect(mappingProgramme(c)).toBe("ECE");
    expect(mappingProgramme({ ...c, po_programme: "CSE" })).toBe("CSE");
    expect(mappingProgramme({ ...c, offerings: [] })).toBe("");
  });

  it("numbers new programme outcomes after the highest", () => {
    const o = (code: string) => ({ code, title: "", text: "" });
    expect(nextOutcomeCode([o("PO1"), o("PO9"), o("PSO1")], "PO")).toBe("PO10");
    expect(nextOutcomeCode([o("PO1"), o("PSO1")], "PSO")).toBe("PSO2");
    expect(nextOutcomeCode([], "PSO")).toBe("PSO1");
  });

  it("sends CO-PO issues to the mapping section", () => {
    expect(sectionOf("copo")).toBe("copo");
    expect(sectionOf("copo.CO3")).toBe("copo");
    expect(sectionOf("po_programme")).toBe("copo");
    expect(sectionOf("outcomes")).toBe("outcomes");
  });

  it("keeps Bloom levels and links through tidy", () => {
    const c = emptyCourse("theory");
    c.outcomes = [{ code: "", text: " ", po: {} }, { code: "", text: "Apply it.", bloom: "apply", po: { PO1: 3 } }];
    expect(tidy(c).outcomes).toEqual([{ code: "CO1", text: "Apply it.", bloom: "apply", po: { PO1: 3 } }]);
  });
});
