from .state import UrlResult
from datetime import datetime, UTC
from bs4 import BeautifulSoup


def fetch_error(url: str, reason: str) -> dict:
    """Helper to create a UrlResult dict for a failed fetch, to keep the reducer logic clean."""
    return {
        "current_raw_content": None,
        "last_result": UrlResult(
            url=url,
            status="failed",
            error=reason,
            processed_at=datetime.now(UTC),
        ),
    }


def extract_text(html: str) -> str:
    """Helper to extract text from HTML, removing scripts/styles and truncating to 8000 chars."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)[:8000]
