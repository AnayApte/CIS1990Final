"""
Scraper and normalizer for SEAS undergraduate degree requirements.
"""

from __future__ import annotations

import html
import re

import requests

from .cache import _majors_index_cache, _program_page_cache

BASE_URL = "https://catalog.upenn.edu"
SEAS_MAJORS_URL = f"{BASE_URL}/undergraduate/engineering-applied-science/majors/"
DEFAULT_TIMEOUT = 20

_MAJOR_LINK_RE = re.compile(
    r'<li>\s*<a href="(?P<href>/undergraduate/programs/[^"]+/)">(?P<label>.*?)</a>\s*</li>',
    re.DOTALL,
)
_COURSE_TABLE_RE = re.compile(
    r"<table class=\"sc_courselist\".*?<caption[^>]*>(?P<caption>.*?)</caption>(?P<body>.*?)</table>",
    re.DOTALL,
)
_ROW_RE = re.compile(r"<tr[^>]*?(?P<class>class=\"(?P<class_value>[^\"]*)\")?[^>]*>(?P<body>.*?)</tr>", re.DOTALL)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL)
_COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,5})\s+([0-9][0-9A-Z]{3})(?:/([0-9][0-9A-Z]{3}))?\b")
_TOTAL_CU_RE = re.compile(r"Total Course Units\s*([0-9]+(?:\.[0-9]+)?)")
_PROGRAM_TITLE_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL)


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
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(span|sup)[^>]*>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def _normalize_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _normalize_course_code(course_code: str) -> str:
    cleaned = course_code.strip().upper().replace("-", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    match = re.fullmatch(r"([A-Z]{2,5})\s+([0-9][0-9A-Z]{3})", cleaned)
    if not match:
        raise RuntimeError(f"Invalid course code: {course_code}")
    return f"{match.group(1)}-{match.group(2)}"


def _extract_codes(cell_text: str) -> list[str]:
    seen: set[str] = set()
    codes: list[str] = []
    normalized = re.sub(r"\s+", " ", cell_text.upper())
    for dept, first, second in _COURSE_CODE_RE.findall(normalized):
        for number in [first, second] if second else [first]:
            code = f"{dept}-{number}"
            if code not in seen:
                seen.add(code)
                codes.append(code)
    return codes


def _majors_index() -> list[dict]:
    cached = _majors_index_cache.get("seas_majors")
    if cached is not None:
        return cached

    html_text = _get(SEAS_MAJORS_URL)
    majors = []
    for match in _MAJOR_LINK_RE.finditer(html_text):
        label = _strip_tags(match.group("label"))
        href = match.group("href")
        if ", BSE" not in label and ", BAS" not in label:
            continue
        majors.append({
            "name": label,
            "url": f"{BASE_URL}{href}",
            "slug": href.strip("/").split("/")[-1],
        })

    _majors_index_cache.set("seas_majors", majors)
    return majors


def list_engineering_degrees() -> list[dict]:
    return _majors_index()


def _program_lookup_map() -> dict[str, dict]:
    majors = _majors_index()
    lookup = {}
    alias_map = {
        "ee": "Electrical Engineering, BSE",
        "electricalengineering": "Electrical Engineering, BSE",
        "ese": "Electrical Engineering, BSE",
        "cis": "Computer Science, BSE",
        "cs": "Computer Science, BSE",
        "csci": "Computer Science, BSE",
        "csbse": "Computer Science, BSE",
        "csbas": "Computer Science, BAS",
        "ce": "Computer Engineering, BSE",
        "ai": "Artificial Intelligence, BSE",
        "dmd": "Digital Media Design, BSE",
        "bioengineering": "Bioengineering, BSE",
        "biomedicalscience": "Biomedical Science, BAS",
        "mse": "Materials Science and Engineering, BSE",
        "meam": "Mechanical Engineering and Applied Mechanics, BSE",
        "cbe": "Chemical and Biomolecular Engineering, BSE",
    }

    for major in majors:
        lookup[_normalize_key(major["name"])] = major

    for alias, target in alias_map.items():
        target_key = _normalize_key(target)
        if target_key in lookup:
            lookup[alias] = lookup[target_key]

    return lookup


def resolve_engineering_degree(major: str) -> dict:
    key = _normalize_key(major)
    lookup = _program_lookup_map()

    if key in lookup:
        return lookup[key]

    for name_key, value in lookup.items():
        if key and key in name_key:
            return value

    raise RuntimeError(f"Unknown engineering degree: {major}")


def _program_page(url: str) -> str:
    cache_key = f"program:{url}"
    cached = _program_page_cache.get(cache_key)
    if cached is not None:
        return cached

    html_text = _get(url)
    _program_page_cache.set(cache_key, html_text)
    return html_text


def _parse_requirement_table(html_text: str) -> list[dict]:
    table_match = _COURSE_TABLE_RE.search(html_text)
    if not table_match:
        raise RuntimeError("Could not find course requirement table on degree page.")

    rows = []
    current_area = "General"
    pending_requirement = None

    for row_match in _ROW_RE.finditer(table_match.group("body")):
        row_html = row_match.group(0)
        classes = row_match.group("class_value") or ""
        cells_html = _CELL_RE.findall(row_match.group("body"))
        cells = [_strip_tags(cell) for cell in cells_html]
        if not cells:
            continue

        if "hidden noscript" in row_html.lower():
            continue

        if "areaheader" in row_html:
            current_area = cells[0]
            rows.append({
                "section": current_area,
                "type": "section_header",
                "label": current_area,
            })
            pending_requirement = None
            continue

        code_text = cells[0] if len(cells) >= 1 else ""
        title_text = cells[1] if len(cells) >= 2 else ""
        units_text = cells[2] if len(cells) >= 3 else ""

        if "orclass" in classes:
            alternative_codes = _extract_codes(code_text)
            if pending_requirement is not None:
                pending_requirement.setdefault("alternatives", []).append({
                    "codes": alternative_codes,
                    "label": title_text or code_text,
                })
            continue

        codes = _extract_codes(code_text)
        label = title_text or code_text
        item_type = "course_group" if codes else "descriptive_requirement"
        requirement = {
            "section": current_area,
            "type": item_type,
            "label": label,
            "codes": codes,
            "units": units_text,
            "alternatives": [],
        }

        rows.append(requirement)
        pending_requirement = requirement

    return rows


def get_engineering_degree_requirements(major: str) -> dict:
    degree = resolve_engineering_degree(major)
    html_text = _program_page(degree["url"])
    title_match = _PROGRAM_TITLE_RE.search(html_text)
    title = _strip_tags(title_match.group(1)) if title_match else degree["name"]
    total_match = _TOTAL_CU_RE.search(_strip_tags(html_text))
    total_cu = float(total_match.group(1)) if total_match else None
    requirements = _parse_requirement_table(html_text)

    return {
        "program": title,
        "slug": degree["slug"],
        "url": degree["url"],
        "total_course_units": total_cu,
        "requirements": requirements,
    }


def _is_requirement_satisfied(requirement: dict, taken: set[str]) -> tuple[bool, list[str]]:
    codes = requirement.get("codes", [])
    alternatives = requirement.get("alternatives", [])

    if not codes:
        return False, []

    primary_ok = all(code in taken for code in codes)
    if primary_ok:
        return True, []

    for alternative in alternatives:
        alt_codes = alternative.get("codes", [])
        if alt_codes and all(code in taken for code in alt_codes):
            return True, []

    primary_missing = [code for code in codes if code not in taken]
    return False, primary_missing


def evaluate_engineering_degree_progress(major: str, classes_taken: list[str]) -> dict:
    degree = get_engineering_degree_requirements(major)
    taken = {_normalize_course_code(code) for code in classes_taken}

    satisfied = []
    unsatisfied = []
    unresolved = []

    for requirement in degree["requirements"]:
        if requirement["type"] == "section_header":
            continue
        if requirement["type"] != "course_group":
            unresolved.append(requirement)
            continue

        ok, missing = _is_requirement_satisfied(requirement, taken)
        record = {
            "section": requirement["section"],
            "label": requirement["label"],
            "codes": requirement["codes"],
            "alternatives": requirement["alternatives"],
            "units": requirement["units"],
        }
        if ok:
            satisfied.append(record)
        else:
            record["missing_codes"] = missing
            unsatisfied.append(record)

    return {
        "program": degree["program"],
        "url": degree["url"],
        "total_course_units": degree["total_course_units"],
        "classes_taken": sorted(taken),
        "satisfied_requirements": satisfied,
        "unsatisfied_requirements": unsatisfied,
        "unresolved_descriptive_requirements": unresolved,
        "note": (
            "This progress check automatically evaluates course-based rows and OR "
            "alternatives from the official requirement table. Broad elective buckets "
            "and footnote constraints remain descriptive for now."
        ),
    }
