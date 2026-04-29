"""
Simple caches for the Penn catalog scraper.
"""

from tools.course_search.cache import Cache


_department_index_cache = Cache(ttl_seconds=3600)
_department_page_cache = Cache(ttl_seconds=1800)
