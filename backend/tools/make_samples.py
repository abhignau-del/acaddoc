"""Write the fictional sample courses in samples/ (safe to publish).

    python tools/make_samples.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from acaddoc.schema import Course  # noqa: E402
from acaddoc.validate import validate  # noqa: E402

MAT = ["Course template", "Tutorial question bank", "Definitions and terminology", "Assignments",
       "Model question paper", "Lecture notes"]


def mod(title, hours, *parts):
    return {"title": title, "hours": hours,
            "parts": [p if isinstance(p, dict) else {"text": p} for p in parts]}


def cos(*texts):
    return [{"code": f"CO{i}", "text": t} for i, t in enumerate(texts, 1)]


def hours(L, T, P, C, contact, tut, prac):
    return {"lecture": L, "tutorial": T, "practical": P, "credits": C, "contact_classes": contact,
            "tutorial_classes": tut, "practical_classes": prac, "total_classes": contact + tut + prac}


MARKS = {"cia": 40, "see": 60, "total": 100}

COURSES = [
    {
        "course_code": "MTH101", "course_title": "Linear Algebra and Calculus", "kind": "theory",
        "category": "Foundation", "offerings": [{"semester": "I", "programmes": ["CSE", "ECE", "ME"]}],
        "hours": hours(3, 1, 0, 4, 48, 16, 0), "marks": MARKS,
        "prerequisite": "School-level algebra and calculus",
        "overview": "This foundation course introduces the linear algebra and calculus used throughout "
                    "engineering: matrices and linear systems, eigenvalues, functions of one and several "
                    "variables, and multiple integrals. Each topic is developed with worked engineering "
                    "applications.",
        "objectives": ["The rank of a matrix and the solution of systems of linear equations.",
                       "Eigenvalues and eigenvectors and their use in diagonalisation.",
                       "Mean value theorems and the behaviour of functions of several variables.",
                       "Evaluation of multiple integrals and their applications to area and volume."],
        "outcomes": cos("Determine the rank of a matrix and solve systems of linear equations.",
                        "Compute eigenvalues and eigenvectors and diagonalise square matrices.",
                        "Apply the Cayley-Hamilton theorem to find inverses and powers of matrices.",
                        "Apply mean value theorems to problems involving derivatives.",
                        "Find maxima and minima of functions of several variables.",
                        "Evaluate double and triple integrals to find areas and volumes."),
        "modules": [
            mod("Matrices", 10, "Rank of a matrix by echelon and normal form; inverse by Gauss-Jordan "
                "elimination; consistency and solution of homogeneous and non-homogeneous systems; "
                "Gauss-Seidel iteration."),
            mod("Eigenvalues and Eigenvectors", 10, "Eigenvalues, eigenvectors and their properties; "
                "diagonalisation; Cayley-Hamilton theorem; quadratic forms and their reduction to "
                "canonical form."),
            mod("Single Variable Calculus", 9, "Rolle's theorem, Lagrange's and Cauchy's mean value "
                "theorems with geometrical interpretation.",
                "Taylor's and Maclaurin's series; curve tracing in Cartesian coordinates."),
            mod("Multivariable Calculus", 10, "Partial differentiation, Euler's theorem, total derivative, "
                "Jacobians; maxima and minima of functions of two variables; Lagrange multipliers."),
            mod("Multiple Integrals", 9, "Double integrals in Cartesian and polar coordinates; change of "
                "order of integration; triple integrals; areas and volumes."),
        ],
        "text_books": ["B. S. Grewal, Higher Engineering Mathematics, Khanna Publishers, 44th edition, 2017.",
                       "Erwin Kreyszig, Advanced Engineering Mathematics, John Wiley & Sons, 10th edition, 2011."],
        "reference_books": ["George B. Thomas, Maurice D. Weir, Joel Hass, Thomas' Calculus, Pearson, "
                            "13th edition, 2013.",
                            "Gilbert Strang, Introduction to Linear Algebra, Wellesley-Cambridge Press, "
                            "5th edition, 2016."],
        "electronic_resources": ["https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/",
                                 "https://ocw.mit.edu/courses/18-02-multivariable-calculus-fall-2007/"],
        "materials_online": MAT,
    },
    {
        "course_code": "ENG103", "course_title": "Technical Communication", "kind": "theory",
        "category": "Foundation",
        "offerings": [{"semester": "I", "programmes": ["ECE", "ME"]}, {"semester": "II", "programmes": ["CSE"]}],
        "hours": hours(2, 0, 0, 2, 32, 0, 0), "marks": MARKS, "prerequisite": "",
        "overview": "The course builds the listening, speaking, reading and writing skills engineers need "
                    "at work. Each module pairs a short reading with focused practice in vocabulary, "
                    "grammar, reading strategy and a writing task.",
        "objectives": ["Clear pronunciation and appropriate stress and intonation in spoken English.",
                       "Accurate grammar and punctuation in professional writing.",
                       "Reading strategies for technical and general texts.",
                       "The structure and conventions of letters, emails and reports."],
        "outcomes": cos("Demonstrate active listening in academic and professional settings.",
                        "Explain technical ideas orally with fluency and accuracy.",
                        "Interpret grammatical forms and apply them in context.",
                        "Apply skimming and scanning to extract information from texts.",
                        "Develop well-structured paragraphs, letters and emails.",
                        "Construct a short technical report in a standard format."),
        "modules": [
            mod("Listening and Speaking", 6, "Reading: an essay on effective listening.",
                {"label": "Vocabulary", "text": "Word formation, prefixes and suffixes."},
                {"label": "Grammar", "text": "Articles and prepositions."},
                {"label": "Writing", "text": "Sentence structure and punctuation."}),
            mod("Reading Strategies", 7, "Reading: an article on emerging technologies.",
                {"label": "Vocabulary", "text": "Homophones and homonyms."},
                {"label": "Reading", "text": "Skimming, scanning and guessing meaning from context."},
                {"label": "Writing", "text": "Paragraph structure, coherence and linkers."}),
            mod("Professional Correspondence", 6,
                {"label": "Grammar", "text": "Tenses and subject-verb agreement."},
                {"label": "Writing", "text": "Formal letters, emails and email etiquette."}),
            mod("Presentations", 7,
                {"label": "Speaking", "text": "Planning and delivering a short technical presentation."},
                {"label": "Vocabulary", "text": "Technical vocabulary and collocations."}),
            mod("Report Writing", 6,
                {"label": "Reading", "text": "The SQ3R method."},
                {"label": "Writing", "text": "Types and structure of technical reports."}),
        ],
        "text_books": ["Michael Swan, Practical English Usage, Oxford University Press, 4th edition, 2016."],
        "reference_books": ["Raymond Murphy, English Grammar in Use, Cambridge University Press, 5th edition, 2019."],
        "electronic_resources": ["https://learnenglish.britishcouncil.org/"],
        "materials_online": MAT,
    },
    {
        "course_code": "CSE205", "course_title": "Data Structures", "kind": "theory", "category": "Core",
        "offerings": [{"semester": "III", "programmes": ["CSE"]}],
        "hours": hours(3, 0, 0, 3, 48, 0, 0), "marks": MARKS, "prerequisite": "Programming for Problem Solving",
        "overview": "The course covers the design, implementation and analysis of fundamental data "
                    "structures (lists, stacks, queues, trees, graphs and hash tables) and the algorithms "
                    "that use them.",
        "objectives": ["Asymptotic analysis of algorithms and data structures.",
                       "Linear data structures and their applications.",
                       "Trees, heaps and search structures.",
                       "Graphs, hashing and their applications."],
        "outcomes": cos("Analyse the time and space complexity of simple algorithms.",
                        "Implement stacks and queues using arrays and linked lists.",
                        "Apply linked lists to problems such as polynomial arithmetic.",
                        "Construct binary search trees and balanced trees.",
                        "Implement graph traversals and shortest-path algorithms.",
                        "Compare hashing techniques and collision-resolution methods."),
        "modules": [
            mod("Introduction and Linear Structures", 10, "Asymptotic notation; arrays; stacks and queues "
                "with applications such as expression evaluation."),
            mod("Linked Lists", 9, "Singly, doubly and circular linked lists; operations; polynomial "
                "representation."),
            mod("Trees", 10, "Binary trees and traversals; binary search trees; AVL trees; heaps and "
                "priority queues."),
            mod("Graphs", 10, "Representations; breadth-first and depth-first search; minimum spanning "
                "trees; Dijkstra's algorithm."),
            mod("Searching, Sorting and Hashing", 9, "Linear and binary search; insertion, merge, quick and "
                "heap sort; hash functions and collision resolution."),
        ],
        "text_books": ["Ellis Horowitz, Sartaj Sahni, Susan Anderson-Freed, Fundamentals of Data Structures "
                       "in C, Universities Press, 2nd edition, 2008."],
        "reference_books": ["Thomas H. Cormen, Charles E. Leiserson, Ronald L. Rivest, Clifford Stein, "
                            "Introduction to Algorithms, MIT Press, 4th edition, 2022.",
                            "Mark Allen Weiss, Data Structures and Algorithm Analysis in C, Pearson, "
                            "2nd edition, 1997."],
        "electronic_resources": ["https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/"],
        "materials_online": MAT,
    },
    {
        "course_code": "CSE206", "course_title": "Data Structures Laboratory", "kind": "laboratory",
        "category": "Core", "offerings": [{"semester": "III", "programmes": ["CSE"]}],
        "hours": hours(0, 0, 2, 1, 0, 0, 36), "marks": MARKS, "prerequisite": "Programming for Problem Solving",
        "overview": "Hands-on implementation of the data structures studied in Data Structures, with "
                    "emphasis on correctness, testing and measuring performance.",
        "objectives": ["Implementation of linear data structures in C.",
                       "Implementation of trees and graphs.",
                       "Searching and sorting with measured running times.",
                       "Choice of a data structure for a given problem."],
        "outcomes": cos("Implement stacks and queues using arrays and linked lists.",
                        "Develop programs that use singly and doubly linked lists.",
                        "Construct binary search trees and perform traversals.",
                        "Implement breadth-first and depth-first graph traversals.",
                        "Compare sorting algorithms by measured running time.",
                        "Design a solution to a case study using suitable data structures."),
        "exercises": [
            {"title": "Stacks and Queues", "items": [
                {"text": "Implement a stack using an array.",
                 "subitems": ["Push and pop with overflow checks.", "Convert an infix expression to postfix.",
                              "Evaluate a postfix expression."]},
                {"text": "Implement a circular queue using an array.",
                 "subitems": ["Insert and delete elements.", "Display the queue after each operation."]}]},
            {"title": "Linked Lists", "items": [
                {"text": "Create a singly linked list of student records with the following structure.",
                 "table": {"header": ["Field", "Type"],
                           "rows": [["roll_no", "int"], ["name", "char[30]"], ["cgpa", "float"]]},
                 "subitems": ["Insert at the beginning, end and a given position.",
                              "Delete a record by roll number.", "Display the records sorted by CGPA."]}]},
            {"title": "Trees", "items": [
                {"text": "Build a binary search tree from a list of integers.",
                 "subitems": ["Print the inorder, preorder and postorder traversals.", "Search for a key.",
                              "Delete a node with two children."]}]},
            {"title": "Case Study: Library Catalogue", "items": [
                {"text": "Design and implement a catalogue that supports search by title, author and ISBN. "
                         "Justify the data structures chosen and measure search times for 10,000 records.",
                 "subitems": []}]},
        ],
        "text_books": ["Ellis Horowitz, Sartaj Sahni, Susan Anderson-Freed, Fundamentals of Data Structures "
                       "in C, Universities Press, 2nd edition, 2008."],
        "reference_books": [],
        "electronic_resources": ["https://visualgo.net/"],
        "materials_online": ["Lab manual", "Lab exercises"],
    },
]

if __name__ == "__main__":
    out = ROOT / "samples"
    out.mkdir(exist_ok=True)
    for d in COURSES:
        c = Course.model_validate(d)
        issues = validate(c)
        print(c.course_code, [str(i) for i in issues] or "OK")
        (out / f"{c.course_code}.json").write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                                                   encoding="utf-8")
