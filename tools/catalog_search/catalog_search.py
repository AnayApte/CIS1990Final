"""
Official UPenn catalog scraper.

This complements the Penn Course Review integration:
- PCR is better for live offerings, sections, and ratings
- The catalog is better for official descriptions, prerequisites,
  mutual exclusions, and cross-listings
"""

from __future__ import annotations

import html
import logging
import re

import requests

from .cache import _department_index_cache, _department_page_cache

logger = logging.getLogger(__name__)

BASE_URL = "https://catalog.upenn.edu"
COURSES_INDEX_URL = f"{BASE_URL}/courses/"
DEFAULT_TIMEOUT = 20

_COURSEBLOCK_RE = re.compile(r'<div class="courseblock">(.*?)</div>', re.DOTALL)
_TITLE_RE = re.compile(
    r'<p class="courseblocktitle noindent"><strong>(.*?)</strong></p>',
    re.DOTALL,
)
_EXTRA_RE = re.compile(
    r'<p class="courseblockextra noindent">(.*?)</p>',
    re.DOTALL,
)
_DEPARTMENT_LINK_RE = re.compile(
    r'<a href="(?P<href>/courses/[^"/]+/)">(?P<label>.*?)</a>',
    re.DOTALL,
)
_COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,5})[\s-]+([0-9][0-9A-Z]{3})\b")
_TOKEN_RE = re.compile(
    r"([A-Z]{2,5}[\s-]+[0-9][0-9A-Z]{3}|\bAND\b|\bOR\b|[\(\)\[\]])",
    re.IGNORECASE,
)


def _get(url: str) -> str:
    try:
        resp = requests.get(url, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Request timed out: {url}")
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.response.status_code} for {url}")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Request failed: {exc}")


def _strip_tags(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _normalize_department(department: str) -> str:
    return department.strip().upper()


def _normalize_course_code(course_code: str) -> str:
    cleaned = re.sub(r"\s+", " ", course_code.strip().upper().replace("-", " "))
    match = re.fullmatch(r"([A-Z]{2,5})\s+([0-9][0-9A-Z]{3})", cleaned)
    if not match:
        raise RuntimeError(f"Invalid course code: {course_code}")
    return f"{match.group(1)}-{match.group(2)}"


def _extract_course_codes(text: str) -> list[str]:
    seen: set[str] = set()
    codes: list[str] = []
    for dept, number in _COURSE_CODE_RE.findall(text):
        code = f"{dept}-{number}"
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def _serialize_logic(node: dict | None):
    if node is None:
        return None
    if node["type"] == "course":
        return node["code"]
    return {
        "type": node["type"],
        "children": [_serialize_logic(child) for child in node["children"]],
    }


def _normalize_logic_text(text: str) -> str:
    normalized = text.upper().replace("[", "(").replace("]", ")")
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _tokenize_prerequisite_text(text: str) -> list[str]:
    normalized = _normalize_logic_text(text)
    return [token.strip() for token in _TOKEN_RE.findall(normalized) if token.strip()]


def _parse_prerequisite_logic(text: str) -> dict | None:
    tokens = _tokenize_prerequisite_text(text)
    if not tokens:
        return None

    position = 0

    def parse_expression():
        return parse_or()

    def parse_or():
        nonlocal position
        node = parse_and()
        children = [node] if node else []
        while position < len(tokens) and tokens[position].upper() == "OR":
            position += 1
            rhs = parse_and()
            if rhs:
                children.append(rhs)
        if not children:
            return None
        if len(children) == 1:
            return children[0]
        return {"type": "or", "children": children}

    def parse_and():
        nonlocal position
        node = parse_primary()
        children = [node] if node else []
        while position < len(tokens) and tokens[position].upper() == "AND":
            position += 1
            rhs = parse_primary()
            if rhs:
                children.append(rhs)
        if not children:
            return None
        if len(children) == 1:
            return children[0]
        return {"type": "and", "children": children}

    def parse_primary():
        nonlocal position
        if position >= len(tokens):
            return None

        token = tokens[position]
        upper = token.upper()

        if token == "(":
            position += 1
            node = parse_expression()
            if position < len(tokens) and tokens[position] == ")":
                position += 1
            return node

        if token == ")":
            return None

        if upper in {"AND", "OR"}:
            position += 1
            return None

        position += 1
        return {"type": "course", "code": _normalize_course_code(token)}

    tree = parse_expression()
    return tree


def _collect_logic_course_codes(node: dict | None) -> list[str]:
    if node is None:
        return []
    if node["type"] == "course":
        return [node["code"]]
    seen: set[str] = set()
    codes: list[str] = []
    for child in node["children"]:
        for code in _collect_logic_course_codes(child):
            if code not in seen:
                seen.add(code)
                codes.append(code)
    return codes


def _evaluate_logic(node: dict | None, taken: set[str]) -> tuple[bool, list[str], list[list[str]]]:
    if node is None:
        return True, [], []

    if node["type"] == "course":
        if node["code"] in taken:
            return True, [], []
        return False, [node["code"]], [[node["code"]]]

    if node["type"] == "and":
        all_missing: list[str] = []
        options: list[list[str]] = []
        seen: set[str] = set()
        satisfied = True
        for child in node["children"]:
            child_ok, child_missing, child_options = _evaluate_logic(child, taken)
            if not child_ok:
                satisfied = False
            for code in child_missing:
                if code not in seen:
                    seen.add(code)
                    all_missing.append(code)
            if child_options:
                options.extend(child_options)
        return satisfied, all_missing, options

    if node["type"] == "or":
        alternatives: list[tuple[list[str], list[list[str]]]] = []
        for child in node["children"]:
            child_ok, child_missing, child_options = _evaluate_logic(child, taken)
            if child_ok:
                return True, [], []
            alternatives.append((child_missing, child_options))

        best_missing, best_options = min(
            alternatives,
            key=lambda item: (len(item[0]), item[0]),
        )
        option_sets = [missing for missing, _ in alternatives]
        return False, best_missing, option_sets or best_options

    raise RuntimeError(f"Unknown logic node type: {node['type']}")


def _split_inline_metadata(paragraph: str) -> list[str]:
    labels = ("Prerequisite:", "Mutually Exclusive:", "Also Offered As:")
    remaining = paragraph.strip()
    parts: list[str] = []

    while remaining:
        positions = [
            remaining.find(label)
            for label in labels
            if remaining.find(label) > 0
        ]
        if not positions:
            parts.append(remaining.strip())
            break

        split_at = min(positions)
        prefix = remaining[:split_at].strip()
        if prefix:
            parts.append(prefix)
        remaining = remaining[split_at:].strip()

        next_positions = [
            remaining.find(label)
            for label in labels
            if remaining.find(label) > 0
        ]
        if next_positions:
            next_split = min(next_positions)
            parts.append(remaining[:next_split].strip())
            remaining = remaining[next_split:].strip()
        else:
            parts.append(remaining.strip())
            break

    return [part for part in parts if part]


def _looks_like_offering_pattern(text: str) -> bool:
    if ":" in text:
        return False
    lowered = text.lower()
    keywords = (
        "fall",
        "spring",
        "summer",
        "not offered",
        "offered occasionally",
        "offered as needed",
        "usually offered",
    )
    return any(keyword in lowered for keyword in keywords) and len(text) <= 80


def _parse_course_block(block_html: str) -> dict:
    title_match = _TITLE_RE.search(block_html)
    if not title_match:
        raise RuntimeError("Could not parse course title block.")

    title_text = _strip_tags(title_match.group(1))
    title_match = re.match(r"^([A-Z]{2,5})\s+([0-9][0-9A-Z]{3})\s+(.*)$", title_text)
    if not title_match:
        raise RuntimeError(f"Unexpected course title format: {title_text}")

    department, number, title = title_match.groups()
    code = f"{department}-{number}"

    extras = [_strip_tags(match) for match in _EXTRA_RE.findall(block_html)]
    description_parts: list[str] = []
    prerequisite_text = ""
    mutually_exclusive_text = ""
    also_offered_as_text = ""
    offering_pattern = ""
    course_units = ""
    notes: list[str] = []

    for paragraph in extras:
        for segment in _split_inline_metadata(paragraph):
            if segment.startswith("Prerequisite:"):
                prerequisite_text = segment.removeprefix("Prerequisite:").strip()
            elif segment.startswith("Mutually Exclusive:"):
                mutually_exclusive_text = segment.removeprefix("Mutually Exclusive:").strip()
            elif segment.startswith("Also Offered As:"):
                also_offered_as_text = segment.removeprefix("Also Offered As:").strip()
            elif "Course Unit" in segment:
                course_units = segment
            elif _looks_like_offering_pattern(segment):
                offering_pattern = segment
            elif not prerequisite_text and not mutually_exclusive_text and not also_offered_as_text:
                description_parts.append(segment)
            else:
                notes.append(segment)

    description = " ".join(part for part in description_parts if part).strip()
    prerequisite_logic = _parse_prerequisite_logic(prerequisite_text)
    prerequisite_courses = _collect_logic_course_codes(prerequisite_logic)
    mutually_exclusive_courses = _extract_course_codes(mutually_exclusive_text)
    also_offered_as_courses = _extract_course_codes(also_offered_as_text)

    return {
        "code": code,
        "code_spaced": f"{department} {number}",
        "department": department,
        "number": number,
        "title": title.strip(),
        "description": description,
        "prerequisite_text": prerequisite_text,
        "prerequisite_courses": prerequisite_courses,
        "prerequisite_logic": _serialize_logic(prerequisite_logic),
        "mutually_exclusive_text": mutually_exclusive_text,
        "mutually_exclusive_courses": mutually_exclusive_courses,
        "also_offered_as_text": also_offered_as_text,
        "also_offered_as_courses": also_offered_as_courses,
        "offering_pattern": offering_pattern,
        "course_units": course_units,
        "notes": notes,
        "source": "upenn_catalog",
    }


def _department_index() -> dict[str, dict]:
    cached = _department_index_cache.get("department_index")
    if cached is not None:
        return cached

    html_text = _get(COURSES_INDEX_URL)
    index: dict[str, dict] = {}

    for match in _DEPARTMENT_LINK_RE.finditer(html_text):
        href = match.group("href")
        label = _strip_tags(match.group("label"))
        code_match = re.search(r"\(([A-Z]{2,5})\)$", label)
        if not code_match:
            continue

        code = code_match.group(1)
        index[code] = {
            "department": code,
            "name": label,
            "url": f"{BASE_URL}{href}",
            "slug": href.strip("/").split("/")[-1],
        }

    _department_index_cache.set("department_index", index)
    return index


def _department_info(department: str) -> dict:
    normalized = _normalize_department(department)
    info = _department_index().get(normalized)
    if info is None:
        raise RuntimeError(f"Unknown catalog department: {department}")
    return info


def _department_courses(department: str) -> list[dict]:
    info = _department_info(department)
    cache_key = f"department_page:{info['department']}"
    cached = _department_page_cache.get(cache_key)
    if cached is not None:
        return cached

    html_text = _get(info["url"])
    courses = [_parse_course_block(block) for block in _COURSEBLOCK_RE.findall(html_text)]
    _department_page_cache.set(cache_key, courses)
    return courses


def get_department_catalog(department: str) -> dict:
    info = _department_info(department)
    courses = _department_courses(department)

    return {
        "department": info["department"],
        "name": info["name"],
        "url": info["url"],
        "course_count": len(courses),
        "courses": courses,
    }


def get_catalog_course(course_code: str) -> dict:
    normalized = _normalize_course_code(course_code)
    department = normalized.split("-", 1)[0]
    courses = _department_courses(department)

    for course in courses:
        if course["code"] == normalized:
            return course

    raise RuntimeError(f"Course not found in official catalog: {normalized}")


def get_catalog_prereqs(course_code: str) -> dict:
    course = get_catalog_course(course_code)
    return {
        "code": course["code"],
        "title": course["title"],
        "prerequisite_text": course["prerequisite_text"],
        "prerequisite_courses": course["prerequisite_courses"],
        "prerequisite_logic": course["prerequisite_logic"],
        "source": course["source"],
    }


def get_catalog_restrictions(course_code: str) -> dict:
    course = get_catalog_course(course_code)
    return {
        "code": course["code"],
        "title": course["title"],
        "prerequisite_text": course["prerequisite_text"],
        "prerequisite_courses": course["prerequisite_courses"],
        "mutually_exclusive_text": course["mutually_exclusive_text"],
        "mutually_exclusive_courses": course["mutually_exclusive_courses"],
        "also_offered_as_text": course["also_offered_as_text"],
        "also_offered_as_courses": course["also_offered_as_courses"],
        "source": course["source"],
    }


def check_catalog_eligibility(
    course_code: str,
    classes_taken: list[str],
    current_schedule: list[str] | None = None,
) -> dict:
    course = get_catalog_course(course_code)
    taken = {code.strip().upper().replace(" ", "-") for code in classes_taken}
    scheduled = {
        code.strip().upper().replace(" ", "-")
        for code in (current_schedule or [])
    }

    missing_prereqs = [
        code for code in course["prerequisite_courses"]
        if code not in taken
    ]
    logic_tree = _parse_prerequisite_logic(course["prerequisite_text"])
    logic_satisfied, logic_missing, logic_options = _evaluate_logic(logic_tree, taken)
    conflicts = [
        code for code in course["mutually_exclusive_courses"]
        if code in taken or code in scheduled
    ]

    return {
        "code": course["code"],
        "title": course["title"],
        "eligible": logic_satisfied and len(conflicts) == 0,
        "missing_prereqs": logic_missing,
        "required_prereqs": course["prerequisite_courses"],
        "prerequisite_text": course["prerequisite_text"],
        "prerequisite_logic": course["prerequisite_logic"],
        "prerequisite_option_sets": logic_options,
        "all_missing_prereq_codes": missing_prereqs,
        "mutually_exclusive_text": course["mutually_exclusive_text"],
        "mutually_exclusive_courses": course["mutually_exclusive_courses"],
        "conflicting_courses": conflicts,
        "current_schedule": sorted(scheduled),
        "classes_taken": sorted(taken),
        "source": course["source"],
        "parser_note": (
            "Eligibility is based on a boolean parse of catalog course codes "
            "extracted from the official prerequisite and mutual exclusion text."
        ),
    }
