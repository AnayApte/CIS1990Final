"""
Caches for engineering degree requirement scraping.
"""

from tools.course_search.cache import Cache


_majors_index_cache = Cache(ttl_seconds=3600)
_program_page_cache = Cache(ttl_seconds=1800)
