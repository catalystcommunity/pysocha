from datetime import timezone
from email.utils import format_datetime
from urllib.parse import urljoin
from xml.etree import ElementTree


ATOM_NS = "http://www.w3.org/2005/Atom"
ElementTree.register_namespace("", ATOM_NS)


def _atom_tag(name: str) -> str:
    return f"{{{ATOM_NS}}}{name}"


def _atom_datetime(value) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _rss_datetime(value) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return format_datetime(value.astimezone(timezone.utc), usegmt=True)


def _site_url(site_address: str, *parts: str) -> str:
    base = site_address.rstrip("/") + "/"
    path = "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))
    return urljoin(base, path)


def build_atom_feed(site_title: str, site_address: str, blog_base_dir: str, posts: list, author: str = None) -> str:
    feed = ElementTree.Element(_atom_tag("feed"))
    ElementTree.SubElement(feed, _atom_tag("title")).text = site_title
    ElementTree.SubElement(feed, _atom_tag("link"), {"href": site_address})
    ElementTree.SubElement(feed, _atom_tag("link"), {"href": _site_url(site_address, blog_base_dir, "atom.xml"), "rel": "self"})

    latest_post = posts[0] if posts else None
    updated = latest_post["PostedDate"] if latest_post else None
    if updated is not None:
        ElementTree.SubElement(feed, _atom_tag("updated")).text = _atom_datetime(updated)

    if author:
        author_element = ElementTree.SubElement(feed, _atom_tag("author"))
        ElementTree.SubElement(author_element, _atom_tag("name")).text = author

    ElementTree.SubElement(feed, _atom_tag("id")).text = site_address

    for post in posts:
        post_url = _site_url(site_address, blog_base_dir, post["slugify"])
        entry = ElementTree.SubElement(feed, _atom_tag("entry"))
        ElementTree.SubElement(entry, _atom_tag("title")).text = post["Title"]
        entry_author = ElementTree.SubElement(entry, _atom_tag("author"))
        ElementTree.SubElement(entry_author, _atom_tag("name")).text = post.get("Author", author)
        ElementTree.SubElement(entry, _atom_tag("link"), {"href": post_url})
        ElementTree.SubElement(entry, _atom_tag("id")).text = post_url
        ElementTree.SubElement(entry, _atom_tag("updated")).text = _atom_datetime(post["PostedDate"])
        ElementTree.SubElement(entry, _atom_tag("summary")).text = post.get("hook", post.get("summary", post["Title"]))

    return ElementTree.tostring(feed, encoding="unicode", xml_declaration=True)


def validate_atom_feed(feed: str):
    ElementTree.fromstring(feed)


def build_rss_feed(site_title: str, site_address: str, blog_base_dir: str, posts: list) -> str:
    rss = ElementTree.Element("rss", {"version": "2.0", "xmlns:atom": ATOM_NS})
    channel = ElementTree.SubElement(rss, "channel")
    ElementTree.SubElement(channel, "title").text = site_title
    ElementTree.SubElement(channel, "link").text = _site_url(site_address, blog_base_dir)
    ElementTree.SubElement(channel, "description").text = site_title
    ElementTree.SubElement(channel, "atom:link", {
        "href": _site_url(site_address, blog_base_dir, "rss.xml"),
        "rel": "self",
        "type": "application/rss+xml",
    })

    latest_post = posts[0] if posts else None
    if latest_post is not None:
        ElementTree.SubElement(channel, "lastBuildDate").text = _rss_datetime(latest_post["PostedDate"])

    for post in posts:
        post_url = _site_url(site_address, blog_base_dir, post["slugify"])
        item = ElementTree.SubElement(channel, "item")
        ElementTree.SubElement(item, "title").text = post["Title"]
        ElementTree.SubElement(item, "link").text = post_url
        ElementTree.SubElement(item, "guid", {"isPermaLink": "true"}).text = post_url
        ElementTree.SubElement(item, "pubDate").text = _rss_datetime(post["PostedDate"])
        ElementTree.SubElement(item, "description").text = post.get("hook", post.get("summary", post["Title"]))
        ElementTree.SubElement(item, "author").text = post["AuthorEmail"]

    return ElementTree.tostring(rss, encoding="unicode", xml_declaration=True)


def validate_rss_feed(feed: str):
    ElementTree.fromstring(feed)
