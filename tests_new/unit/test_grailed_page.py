from app.scrapers.grailed_page import GrailedPageState, classify_grailed_html


def test_classifies_next_data_listing() -> None:
    html = '<html><script id="__NEXT_DATA__">{"props":{"pageProps":{"listing":{"price":120}}}}</script></html>'
    assert classify_grailed_html(html) is GrailedPageState.LISTING


def test_classifies_access_denied_page() -> None:
    html = "<html><body>You are unable to access grailed.com</body></html>"
    assert classify_grailed_html(html) is GrailedPageState.BLOCKED


def test_classifies_cloudflare_challenge_page() -> None:
    html = '<html><body><div id="challenge-running">Checking your browser</div></body></html>'
    assert classify_grailed_html(html) is GrailedPageState.BLOCKED


def test_classifies_missing_listing_data_as_incomplete() -> None:
    assert classify_grailed_html("<html><body>Grailed</body></html>") is GrailedPageState.INCOMPLETE
    assert classify_grailed_html(None) is GrailedPageState.INCOMPLETE
