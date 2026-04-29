"""
Penn unofficial transcript parser.

Supports raw text (pasted or pre-extracted) and PDF (via pdfplumber).
PDF import is deferred so the module loads even when pdfplumber isn't installed.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ── Old → new course number map (pre-2022 3-digit → current 4-digit) ─────────
#
# Penn renumbered most courses in Fall 2022.  Students who completed courses
# before the switch will have 3-digit codes on their transcripts.

OLD_TO_NEW: dict[str, str] = {
    # CIS
    "CIS-110":  "CIS-1100",
    "CIS-120":  "CIS-1200",
    "CIS-121":  "CIS-1210",
    "CIS-160":  "CIS-1600",
    "CIS-240":  "CIS-2400",
    "CIS-262":  "CIS-2620",
    "CIS-320":  "CIS-3200",
    "CIS-341":  "CIS-3410",
    "CIS-380":  "CIS-3800",
    "CIS-471":  "CIS-4710",
    "CIS-520":  "CIS-5200",
    "CIS-521":  "CIS-5210",
    # MATH
    "MATH-114": "MATH-1410",
    "MATH-240": "MATH-2410",
    "MATH-241": "MATH-2400",
    "MATH-312": "MATH-3120",
    # PHYS — Path@Penn exports leading-zero form (e.g. "PHYS 0150") and some
    # older exports drop the zero; both variants are mapped.
    "PHYS-0140": "PHYS-1400",
    "PHYS-0141": "PHYS-1410",
    "PHYS-0150": "PHYS-1500",
    "PHYS-0151": "PHYS-1510",
    "PHYS-140":  "PHYS-1400",
    "PHYS-141":  "PHYS-1410",
    "PHYS-150":  "PHYS-1500",
    "PHYS-151":  "PHYS-1510",
    # ESE
    "ESE-112":  "ESE-1120",
    "ESE-215":  "ESE-2150",
    "ESE-301":  "ESE-3010",
    "ESE-330":  "ESE-3300",
    "ESE-350":  "ESE-3500",
}

# Grades that mean the course was not completed (skip these).
_SKIP_GRADES: frozenset[str] = frozenset({"W", "I", "AU", "IN PROGRESS"})

# ── Compiled regexes ──────────────────────────────────────────────────────────

# Semester header — matches "Fall 2023", "Spring 2022", "2021 Fall", etc.
_SEMESTER_RE = re.compile(
    r"\b(Fall|Spring|Summer)\s+(\d{4})\b"
    r"|\b(\d{4})\s+(Fall|Spring|Summer)\b",
    re.IGNORECASE,
)

_SPECIAL_SECTION_RE = re.compile(
    r"\b(?P<term>Fall|Spring|Summer)\s+(?P<year>\d{4})\s+"
    r"(?P<section>Advanced Placement Credit|Dept Internal Examination|Transfer Credit|Advanced Standing)\b",
    re.IGNORECASE,
)
_AP_LINE_RE = re.compile(r"\bAP\b", re.IGNORECASE)

# Match a transcript course entry anywhere in the line. This is intentionally
# not anchored because Path@Penn PDF text extraction often interleaves the left
# and right columns onto the same line.
_COURSE_ENTRY_RE = re.compile(
    r"(?P<dept>[A-Z]{2,5})\s{1,4}(?P<number>\d{3,4})\s+"
    r"(?P<title>.+?)\s+"
    r"(?P<credits>\d+\.\d+)\s+"
    r"(?P<grade>IN PROGRESS|A[+-]?|B[+-]?|C[+-]?|D[+-]?|F|W|I|AU|P|NP|TR|CR|S|U)"
)

# Student info — tolerant of varying label spellings and separators.
# "Record of:" is the label Path@Penn uses for the student name.
# "Major :" (space before colon) is how it appears in the PDF extraction.
# Avoiding "Program:" here because that line contains the school/degree name.
_NAME_RE   = re.compile(r"(?:(?:Student\s+)?Name|Record\s+of)\s*[:\-]\s*(.+)", re.IGNORECASE)
_SCHOOL_RE = re.compile(r"(?:School|College|Faculty)\s*[:\-]\s*(.+)",           re.IGNORECASE)
_MAJOR_RE  = re.compile(r"(?:Major|Plan)\s*[:\-]\s*(.+)",                       re.IGNORECASE)
_AP_SECTION_RE = re.compile(r"\b(advanced placement|ap credit|ap credits|advanced standing)\b", re.IGNORECASE)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_code(dept: str, number: str) -> str:
    """Return DEPT-NNNN, applying the old→new mapping and zero-padding to 4 digits."""
    raw = f"{dept.upper()}-{number}"
    mapped = OLD_TO_NEW.get(raw)
    if mapped:
        return mapped
    # Zero-pad numeric-only suffixes shorter than 4 digits (e.g. "039" → "0390").
    if number.isdigit() and len(number) < 4:
        number = number.ljust(4, "0")
    return f"{dept.upper()}-{number}"


def _extract_semester(line: str) -> str | None:
    """Return 'Fall 2023' style string if the line contains a semester marker."""
    m = _SEMESTER_RE.search(line)
    if not m:
        return None
    if m.group(1):                          # "Fall 2023" form
        return f"{m.group(1).capitalize()} {m.group(2)}"
    return f"{m.group(4).capitalize()} {m.group(3)}"   # "2023 Fall" form


def _extract_special_term(line: str) -> str | None:
    """Return a synthetic term label for transcript sections like AP credit."""
    match = _SPECIAL_SECTION_RE.search(line)
    if not match:
        if _AP_SECTION_RE.search(line):
            return "AP Credit"
        return None

    semester = f"{match.group('term').capitalize()} {match.group('year')}"
    section = match.group("section").lower()
    if "advanced placement" in section:
        return f"AP Credit ({semester})"
    if "dept internal examination" in section:
        return f"Dept Internal Exam ({semester})"
    if "transfer credit" in section:
        return f"Transfer Credit ({semester})"
    if "advanced standing" in section:
        return f"Advanced Standing ({semester})"
    return None


def _course_source(current_semester: str) -> str:
    if current_semester.startswith("AP Credit"):
        return "ap_credit"
    if current_semester.startswith("Dept Internal Exam"):
        return "dept_internal_exam"
    if current_semester.startswith("Transfer Credit"):
        return "transfer_credit"
    if current_semester.startswith("Advanced Standing"):
        return "advanced_standing"
    return "transcript"


def _parse_course_lines(line: str, current_semester: str) -> list[dict]:
    """Extract all course entries found anywhere in a transcript line."""
    effective_semester = current_semester
    if not effective_semester and _AP_LINE_RE.search(line):
        effective_semester = "AP Credit"

    courses: list[dict] = []
    for match in _COURSE_ENTRY_RE.finditer(line):
        dept = match.group("dept")
        number = match.group("number")
        grade = match.group("grade").upper()
        credits = float(match.group("credits"))
        title = match.group("title").strip()

        if grade in _SKIP_GRADES:
            logger.debug("Skipping %s %s — grade %s", dept, number, grade)
            continue

        courses.append({
            "code": _normalize_code(dept, number),
            "title": title,
            "grade": grade,
            "credits": credits,
            "semester": effective_semester,
            "source": _course_source(effective_semester),
        })
    return courses


# ── Public API ────────────────────────────────────────────────────────────────

def parse_transcript_text(text: str) -> dict:
    """
    Parse raw transcript text and return extracted course records.

    Args:
        text: Full text of a Penn unofficial transcript (may be multi-page).

    Returns:
        {
            "courses": [{"code", "title", "grade", "credits", "semester"}, ...],
            "student_info": {"name", "school", "major"},
        }

    Courses with grades W (withdrawn), I (incomplete), or AU (audit) are omitted.
    Old 3-digit course numbers are remapped to current 4-digit equivalents.
    """
    student_info: dict[str, str] = {"name": "", "school": "", "major": ""}
    courses: list[dict] = []
    current_semester = ""

    if not text or not isinstance(text, str):
        return {"courses": courses, "student_info": student_info}

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        # Semester header detection — must come before course-line check so
        # semester lines that happen to start with a dept code are handled first.
        special_term = _extract_special_term(line)
        if special_term:
            current_semester = special_term
        else:
            sem = _extract_semester(line)
            if sem:
                current_semester = sem

        # Student metadata (only capture first non-empty match for each field).
        if not student_info["name"]:
            m = _NAME_RE.search(line)
            if m:
                student_info["name"] = m.group(1).strip()

        if not student_info["school"]:
            m = _SCHOOL_RE.search(line)
            if m:
                student_info["school"] = m.group(1).strip()

        if not student_info["major"]:
            m = _MAJOR_RE.search(line)
            if m:
                student_info["major"] = m.group(1).strip()

        courses.extend(_parse_course_lines(line, current_semester))

    return {"courses": courses, "student_info": student_info}


def parse_transcript_pdf(filepath: str) -> dict:
    """
    Extract text from a Penn transcript PDF and parse it.

    Requires pdfplumber (pip install pdfplumber).  Handles multi-page PDFs.

    Args:
        filepath: Path to the PDF file.

    Returns:
        Same structure as parse_transcript_text().
    """
    try:
        import pdfplumber  # noqa: PLC0415 — intentional deferred import
    except ImportError as exc:
        raise RuntimeError(
            "pdfplumber is required for PDF parsing. "
            "Install it with: pip install pdfplumber"
        ) from exc

    pages: list[str] = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                pages.append(page_text)

    return parse_transcript_text("\n".join(pages))
