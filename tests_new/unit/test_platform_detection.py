from app.bot.utils import detect_platform


class TestPlatformDetection:
    def test_detect_platform_ebay(self, test_urls):
        url = test_urls["ebay"][0]
        assert detect_platform(url) == "ebay"

    def test_detect_platform_grailed_listing(self, test_urls):
        url = test_urls["grailed"][0]
        assert detect_platform(url) == "grailed"

    def test_detect_platform_grailed_profile(self, test_urls):
        url = test_urls["grailed"][1]
        assert detect_platform(url) == "profile"
