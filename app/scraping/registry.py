from typing import List, Optional

from .base import ScraperStrategy
from .facebook import FacebookScraper
from .generic import GenericScraper
from .instagram import InstagramScraper

# Order matters: the first match wins. Instagram/Facebook need their own
# crawler-UA handling so they're checked first; GenericScraper matches any
# URL, so it must stay last or nothing else would ever be reached.
STRATEGIES: List[ScraperStrategy] = [
    InstagramScraper(),
    FacebookScraper(),
    GenericScraper(),
]


def find_strategy(url: str) -> Optional[ScraperStrategy]:
    for strategy in STRATEGIES:
        if strategy.matches(url):
            return strategy
    return None
