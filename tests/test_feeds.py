from datetime import datetime, timezone
from xml.etree import ElementTree

from pysocha.atom import build_atom_feed, build_rss_feed


def _posts():
    return [
        {
            "Title": "A & B < C",
            "Author": "Tod & Team",
            "AuthorEmail": "tod@example.com",
            "PostedDate": datetime(2026, 7, 14, 16, 30, tzinfo=timezone.utc),
            "slugify": "a-b-c.html",
            "summary": "Summary with & and < safely escaped",
        }
    ]


def test_atom_feed_parses_and_escapes_text():
    feed = build_atom_feed(
        "Site & Title",
        "https://example.com/",
        "blog",
        _posts(),
        "Tod & Team",
    )
    root = ElementTree.fromstring(feed)
    ns = {"a": "http://www.w3.org/2005/Atom"}

    assert root.tag == "{http://www.w3.org/2005/Atom}feed"
    assert root.find("a:title", ns).text == "Site & Title"
    entry = root.find("a:entry", ns)
    assert entry.find("a:title", ns).text == "A & B < C"
    assert entry.find("a:summary", ns).text == "Summary with & and < safely escaped"


def test_rss_feed_parses_and_uses_author_email():
    feed = build_rss_feed("Site & Title", "https://example.com/", "blog", _posts())
    root = ElementTree.fromstring(feed)
    channel = root.find("channel")
    item = channel.find("item")

    assert root.tag == "rss"
    assert root.attrib["version"] == "2.0"
    assert channel.find("title").text == "Site & Title"
    assert item.find("title").text == "A & B < C"
    assert item.find("author").text == "tod@example.com"
    assert item.find("pubDate").text == "Tue, 14 Jul 2026 16:30:00 GMT"
