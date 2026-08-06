from .base import ScrapedContent, ScraperStrategy
from .og_tags import fetch_og_tags


class GenericScraper(ScraperStrategy):
    """Catch-all fallback: most gift links are ordinary retailer product
    pages (Amazon, Etsy, Target, ...) rather than Instagram/Facebook posts,
    and most of those sites publish Open Graph tags for their own link
    previews without requiring a crawler-specific User-Agent. Registered
    last in `registry.py` so a more specific strategy always wins first.
    """

    name = "generic"

    def matches(self, url: str) -> bool:
        return True

    def scrape(self, url: str) -> ScrapedContent:
        return fetch_og_tags(url)
