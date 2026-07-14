from pathlib import Path

from pysocha.build import buildSite


def _write_minimal_site(root: Path, post_frontmatter: str, *, disable_rss: bool = False):
    content = root / "content"
    templates = root / "templates"
    (content / "pages").mkdir(parents=True)
    (content / "blog_posts").mkdir(parents=True)
    (content / "extra_files").mkdir(parents=True)
    templates.mkdir()

    (content / "pages" / "index.md").write_text("---\ntitle: Home\n---\n# Home\n")
    (content / "blog_posts" / "post.md").write_text(f"---\n{post_frontmatter}---\nPost body\n")
    for template in [
        "page.jinja2",
        "blog.jinja2",
        "listing.jinja2",
        "tags.jinja2",
        "tag.jinja2",
        "authors.jinja2",
        "author.jinja2",
    ]:
        (templates / template).write_text("{{ content|default('') }}")

    return {
        "contentDir": "content",
        "outputDir": "generated",
        "templatesDir": "templates",
        "siteTitle": "Test Site",
        "siteAddress": "https://example.com/",
        "descending": True,
        "defaultExtension": ".html",
        "startPage": "index.html",
        "pageConfig": {
            "pageDefaultTemplate": "page.jinja2",
        },
        "blogConfig": {
            "title": "Blog",
            "blogBaseDir": "blog",
            "blogTemplate": "blog.jinja2",
            "listingTemplate": "listing.jinja2",
            "listingPaginationNum": 5,
            "atomFeeds": True,
            "disableRSS": disable_rss,
            "tagsTemplate": "tags.jinja2",
            "tagTemplate": "tag.jinja2",
            "tagPaginationNum": 5,
            "authorsTemplate": "authors.jinja2",
            "authorTemplate": "author.jinja2",
            "authorPaginationNum": 10,
        },
    }


def test_build_is_quiet_by_default_and_verbose_prints_paths(tmp_path, monkeypatch, capsys):
    config = _write_minimal_site(tmp_path, """Title: Post
Author: Tod
AuthorEmail: tod@example.com
PostedDate: "2026-07-14T10:00:00-06:00"
""")
    monkeypatch.chdir(tmp_path)

    buildSite(config)
    quiet = capsys.readouterr()
    assert quiet.out == ""

    buildSite(config, verbose=True)
    verbose = capsys.readouterr()
    assert "generated/index.html" in verbose.out
    assert "generated/blog/rss.xml" in verbose.out


def test_rss_is_generated_when_author_email_is_present(tmp_path, monkeypatch):
    config = _write_minimal_site(tmp_path, """Title: Post
Author: Tod
AuthorEmail: tod@example.com
PostedDate: "2026-07-14T10:00:00-06:00"
""")
    monkeypatch.chdir(tmp_path)

    buildSite(config)

    assert (tmp_path / "generated" / "blog" / "atom.xml").exists()
    assert (tmp_path / "generated" / "blog" / "rss.xml").exists()


def test_rss_is_not_generated_without_author_email(tmp_path, monkeypatch):
    config = _write_minimal_site(tmp_path, """Title: Post
Author: Tod
PostedDate: "2026-07-14T10:00:00-06:00"
""")
    monkeypatch.chdir(tmp_path)

    buildSite(config)

    assert (tmp_path / "generated" / "blog" / "atom.xml").exists()
    assert not (tmp_path / "generated" / "blog" / "rss.xml").exists()


def test_rss_can_be_disabled_even_with_author_email(tmp_path, monkeypatch):
    config = _write_minimal_site(
        tmp_path,
        """Title: Post
Author: Tod
AuthorEmail: tod@example.com
PostedDate: "2026-07-14T10:00:00-06:00"
""",
        disable_rss=True,
    )
    monkeypatch.chdir(tmp_path)

    buildSite(config)

    assert (tmp_path / "generated" / "blog" / "atom.xml").exists()
    assert not (tmp_path / "generated" / "blog" / "rss.xml").exists()
