import importlib
import os
import stat
from pathlib import Path

import pytest

from pysocha.build import ContentBuildError, _publish_staged_output, buildSite
from pysocha.markdown import MarkdownContentError


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


def test_ordinary_page_keeps_template_extension_and_permissive_values(tmp_path, monkeypatch):
    config = _write_minimal_site(tmp_path, """Title: Post
Author: Tod
AuthorEmail: tod@example.com
PostedDate: "2026-07-14T10:00:00-06:00"
""")
    (tmp_path / "content" / "pages" / "index.md").write_text(
        """---
Title: Home
Template: custom.jinja2
Extension: .txt
---
# Home
"""
    )
    (tmp_path / "templates" / "custom.jinja2").write_text(
        "{{ missing_optional_value }}{{ content }}"
    )
    monkeypatch.chdir(tmp_path)

    buildSite(config)

    rendered = (tmp_path / "generated" / "index.txt").read_text()
    assert "<h1>Home</h1>" in rendered


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
    assert "Post body" in (tmp_path / "generated" / "blog" / "post.html").read_text()


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


def test_rich_page_renders_regions_and_frontmatter_component_data(tmp_path, monkeypatch):
    config = _write_minimal_site(tmp_path, """Title: Post
Author: Tod
AuthorEmail: tod@example.com
PostedDate: "2026-07-14T10:00:00-06:00"
""")
    page = tmp_path / "content" / "pages" / "index.md"
    page.write_text(
        """---
Title: Home
Template: rich-page.jinja2
ContentMode: regions
Components:
  primary_action:
    label: Start now
    url: other.md
---
::: region hero
# Build useful things

Use **simple tools**.
:::

::: region examples
```python
def hello():
    return 1
```
:::
"""
    )
    (tmp_path / "content" / "pages" / "other.md").write_text(
        "---\nTitle: Other\n---\n# Other\n"
    )
    rich_template = tmp_path / "templates" / "rich-page.jinja2"
    rich_template.write_text(
        """<main>{{ content_regions["hero"] }}</main>
<aside>{{ content_regions["examples"] }}</aside>
{% if Components.primary_action is defined %}
{% with action=Components.primary_action %}
{% include "button.jinja2" %}
{% endwith %}
{% endif %}
"""
    )
    button_template = tmp_path / "templates" / "button.jinja2"
    button_template.write_text('<a class="button" href="{{ action.url }}">{{ action.label }}</a>')
    monkeypatch.chdir(tmp_path)

    buildSite(config)

    rendered = (tmp_path / "generated" / "index.html").read_text()
    assert "<h1>Build useful things</h1>" in rendered
    assert "<strong>simple tools</strong>" in rendered
    assert "highlight language-python" in rendered
    assert '<a class="button" href="other.html">Start now</a>' in rendered
    assert "Build useful things" not in rich_template.read_text()
    assert "Start now" not in rich_template.read_text()
    assert "Start now" not in button_template.read_text()


def test_rich_page_uses_strict_template_values(tmp_path, monkeypatch):
    config = _write_minimal_site(tmp_path, """Title: Post
Author: Tod
AuthorEmail: tod@example.com
PostedDate: "2026-07-14T10:00:00-06:00"
""")
    (tmp_path / "content" / "pages" / "index.md").write_text(
        """---
Title: Home
Template: rich-page.jinja2
ContentMode: regions
Components:
  primary_action:
    url: /start/
---
::: region hero
# Home
:::
"""
    )
    (tmp_path / "templates" / "rich-page.jinja2").write_text(
        '{{ content_regions["hero"] }}{{ Components.primary_action.label }}'
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ContentBuildError) as caught:
        buildSite(config)

    error = str(caught.value)
    assert "content/pages/index.md" in error
    assert "rich-page.jinja2" in error
    assert "label" in error


def test_failed_build_keeps_previous_output(tmp_path, monkeypatch):
    config = _write_minimal_site(tmp_path, """Title: Post
Author: Tod
AuthorEmail: tod@example.com
PostedDate: "2026-07-14T10:00:00-06:00"
""")
    monkeypatch.chdir(tmp_path)
    buildSite(config)
    generated_page = tmp_path / "generated" / "index.html"
    previous_output = generated_page.read_text()

    (tmp_path / "content" / "pages" / "index.md").write_text(
        """---
Title: Broken
ContentMode: regions
---
::: region hero
# Missing closing marker
"""
    )

    with pytest.raises(MarkdownContentError):
        buildSite(config)

    assert generated_page.read_text() == previous_output
    assert list(tmp_path.glob(".generated.pysocha-build-*")) == []


def test_successful_build_preserves_output_directory_mode(tmp_path, monkeypatch):
    config = _write_minimal_site(tmp_path, """Title: Post
Author: Tod
AuthorEmail: tod@example.com
PostedDate: "2026-07-14T10:00:00-06:00"
""")
    monkeypatch.chdir(tmp_path)
    buildSite(config)
    output = tmp_path / "generated"
    output.chmod(0o750)

    buildSite(config)

    assert stat.S_IMODE(output.stat().st_mode) == 0o750


def test_publish_failure_restores_previous_output(tmp_path, monkeypatch):
    output = tmp_path / "generated"
    staged = tmp_path / ".generated.pysocha-build-test"
    output.mkdir()
    staged.mkdir()
    (output / "index.html").write_text("previous")
    (staged / "index.html").write_text("new")
    real_replace = os.replace
    build_module = importlib.import_module("pysocha.build")
    call_count = 0

    def fail_new_output_publish(source, destination):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("publish failed")
        return real_replace(source, destination)

    monkeypatch.setattr(build_module.os, "replace", fail_new_output_publish)

    with pytest.raises(OSError, match="publish failed"):
        _publish_staged_output(str(staged), str(output))

    assert (output / "index.html").read_text() == "previous"
    assert list(tmp_path.glob(".generated.pysocha-backup-*")) == []


def test_page_names_keep_every_character_before_the_extension(tmp_path, monkeypatch):
    # Stripping ".md" as a set of characters ate trailing d, m and dot
    # characters, so "diagram.md" became "diagra".
    config = _write_minimal_site(tmp_path, """Title: Post
Author: Tod
AuthorEmail: tod@example.com
PostedDate: "2026-07-14T10:00:00-06:00"
""")
    for name in ["diagram.md", "command.md", "dammed.md", "index.md"]:
        (tmp_path / "content" / "pages" / name).write_text(
            "---\nTitle: %s\n---\nBody\n" % name
        )
    monkeypatch.chdir(tmp_path)

    buildSite(config)

    generated = tmp_path / "generated"
    for expected in ["diagram.html", "command.html", "dammed.html", "index.html"]:
        assert (generated / expected).is_file(), expected


def test_links_between_pages_point_at_the_files_that_exist(tmp_path, monkeypatch):
    # The link replacement map and the output file name have to agree, or a
    # link points at a page that was never written.
    config = _write_minimal_site(tmp_path, """Title: Post
Author: Tod
AuthorEmail: tod@example.com
PostedDate: "2026-07-14T10:00:00-06:00"
""")
    (tmp_path / "content" / "pages" / "diagram.md").write_text(
        "---\nTitle: Diagram\n---\nA diagram page\n"
    )
    (tmp_path / "content" / "pages" / "index.md").write_text(
        "---\nTitle: Home\n---\nSee [the diagram](diagram.md)\n"
    )
    monkeypatch.chdir(tmp_path)

    buildSite(config)

    generated = tmp_path / "generated"
    assert 'href="diagram.html"' in (generated / "index.html").read_text()
    assert (generated / "diagram.html").is_file()


def test_default_config_supplies_the_listing_pagination_key_the_build_reads(tmp_path, monkeypatch):
    # The default config spelled this key listingPagination_num, so a site that
    # relied on the defaults failed with a KeyError.
    from pysocha.config import override_config

    config = _write_minimal_site(tmp_path, """Title: Post
Author: Tod
AuthorEmail: tod@example.com
PostedDate: "2026-07-14T10:00:00-06:00"
""")
    del config["blogConfig"]["listingPaginationNum"]
    merged = override_config(config)
    monkeypatch.chdir(tmp_path)

    buildSite(merged)

    assert (tmp_path / "generated" / "blog" / "listing1.html").is_file()
