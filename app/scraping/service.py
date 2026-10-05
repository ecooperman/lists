from sqlalchemy.orm import Session

from .. import crud, models
from .base import ScraperError
from .registry import find_strategy


def scrape_item(db: Session, item_id: int, url: str) -> models.Item:
    """Run the matching strategy for `url` and persist the outcome onto the
    item, whatever it is (success, failed, or unsupported) - so the UI
    always has something to show rather than silently doing nothing.
    """
    strategy = find_strategy(url)
    if strategy is None:
        return crud.save_scrape_result(
            db,
            item_id,
            models.ScrapeStatus.unsupported,
            error="No scraping strategy is available for this URL yet",
        )

    try:
        content = strategy.scrape(url)
    except ScraperError as exc:
        return crud.save_scrape_result(
            db, item_id, models.ScrapeStatus.failed, error=str(exc)
        )

    return crud.save_scrape_result(
        db,
        item_id,
        models.ScrapeStatus.success,
        title=content.title,
        description=content.description,
        image_url=content.image_url,
    )
