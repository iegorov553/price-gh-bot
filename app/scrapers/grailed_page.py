from enum import StrEnum


class GrailedPageState(StrEnum):
    LISTING = "listing"
    BLOCKED = "blocked"
    INCOMPLETE = "incomplete"


_BLOCK_MARKERS = (
    "you are unable to access grailed.com",
    "checking your browser",
    "<title>just a moment...</title>",
    "performing security verification",
    "this website uses a security service to protect against malicious bots",
    "cf-chl-",
    "challenge-running",
)

_LISTING_MARKERS = (
    'id="__NEXT_DATA__"',
    "id='__NEXT_DATA__'",
    'property="product:price:amount"',
    'type="application/ld+json"',
)


def classify_grailed_html(html: str | None) -> GrailedPageState:
    if not html:
        return GrailedPageState.INCOMPLETE
    lowered = html.lower()
    if any(marker in lowered for marker in _BLOCK_MARKERS):
        return GrailedPageState.BLOCKED
    if any(marker.lower() in lowered for marker in _LISTING_MARKERS):
        return GrailedPageState.LISTING
    return GrailedPageState.INCOMPLETE
