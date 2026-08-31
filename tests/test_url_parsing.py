import pytest

from app.errors import InvalidProfileURL
from app.linkedin.router import parse_profile_url


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.linkedin.com/in/ada-lovelace", "ada-lovelace"),
        ("https://www.linkedin.com/in/ada-lovelace/", "ada-lovelace"),
        ("http://www.linkedin.com/in/ada-lovelace", "ada-lovelace"),
        ("https://linkedin.com/in/ada-lovelace", "ada-lovelace"),
        ("www.linkedin.com/in/ada-lovelace", "ada-lovelace"),
        ("linkedin.com/in/ada-lovelace", "ada-lovelace"),
        ("https://de.linkedin.com/in/ada-lovelace", "ada-lovelace"),
        ("https://www.linkedin.com/in/ada-lovelace?trk=nav", "ada-lovelace"),
        ("https://www.linkedin.com/in/ada-lovelace/en", "ada-lovelace"),
        ("  https://www.linkedin.com/in/ada-lovelace  ", "ada-lovelace"),
        ("https://www.linkedin.com/in/ACoAAA-encoded_slug", "ACoAAA-encoded_slug"),
        ("https://www.linkedin.com:443/in/ada-lovelace", "ada-lovelace"),
    ],
)
def test_accepts_profile_urls(url, expected):
    assert parse_profile_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "https://example.com/in/ada-lovelace",
        "https://notlinkedin.com/in/ada",
        "https://linkedin.com.evil.com/in/ada",
        "https://www.linkedin.com/company/tross",
        "https://www.linkedin.com/school/oxford",
        "https://www.linkedin.com/feed/",
        "https://www.linkedin.com/in/",
        "https://www.linkedin.com/",
        "not a url at all",
    ],
)
def test_rejects_non_profile_urls(url):
    with pytest.raises(InvalidProfileURL):
        parse_profile_url(url)
