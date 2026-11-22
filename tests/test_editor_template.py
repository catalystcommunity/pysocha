from datetime import datetime, timezone

import frontmatter
import pytest

from pysocha.build import get_markdown_files
from pysocha.editor_template import fields, render


NOW = datetime(2026, 11, 21, 12, 34, 56, tzinfo=timezone.utc)


def test_custom_fields_are_optional_and_render_once_in_yaml_and_markdown():
    source = """---
# Keep this note.
Title: {$title}
PostedDate: '{$current_time}'
Author: "{$byline}"
Tags: ['{$tag}']
Hook: "<p>{$summary}</p>" # Keep this too.
---
# {$title}
{$byline} at {$current_time}
{$summary}
{{ page.title }}
"""
    assert fields(source) == ["byline", "tag", "summary"]
    title = "L'été: #42"
    author = 'Ada "A"'
    draft = render(source, title, {"byline": author, "summary": "{$title}"}, NOW)
    assert draft["filename"] == "l-ete-42.md"
    parsed = frontmatter.loads(draft["text"])
    assert parsed.metadata == {"Title": title, "PostedDate": NOW.isoformat(), "Author": author,
                               "Tags": [""], "Hook": "<p>{$title}</p>"}
    assert parsed.content == '# {}\n{} at {}\n{{$title}}\n{{{{ page.title }}}}'.format(title, author, NOW.isoformat())
    assert "# Keep this note." in draft["text"] and "# Keep this too." in draft["text"]


def test_tnl_starter_and_existing_articles():
    legacy = "---\r\nTitle: 'TITLE'\r\nPostedDate: 'sample'\r\nHook: \"<p>HOOK</p>\"\r\n---\r\nCONTENT\r\n"
    draft = render(legacy, "New post", {}, NOW)["text"]
    assert frontmatter.loads(draft)["PostedDate"] == NOW.isoformat()
    assert draft.endswith("---\r\nCONTENT\r\n")
    assert 'Hook: "<p>HOOK</p>"' in draft
    article = legacy.replace("'TITLE'", "'Original title'").replace("'sample'", "'2012-01-01'")
    data = frontmatter.loads(render(article, "Fresh draft", {}, NOW)["text"])
    assert data["Title"] == "Fresh draft" and data["PostedDate"] == "2012-01-01"


def test_landing_template_with_block_scalar_and_no_blog_fields():
    template = "---\nTitle: 'About {$team}'\nIntro: |\n  Meet {$team}.\nFixed: yes\n---\n{$team}"
    draft = render(template, "Our team", {"team": "Research: A & B"}, NOW)
    data = frontmatter.loads(draft["text"])
    assert draft["filename"] == "our-team.md"
    assert data["Title"] == "About Research: A & B"
    assert data["Intro"] == "Meet Research: A & B.\n" and data["Fixed"] is True
    assert data.content == "Research: A & B"
    assert render("Hello {$title}", "Start here", {}, NOW)["text"] == "Hello Start here"


@pytest.mark.parametrize("title", ["", "...", "NUL", "COM1", "0-basetemplate"])
def test_invalid_or_reserved_title(title):
    with pytest.raises(ValueError):
        render("body", title, {}, NOW)


def test_starters_are_excluded_from_build_discovery(tmp_path):
    for name in ["new.template.md", "0-basetemplate.md", "0-basetemplate.txt", "article.md"]:
        (tmp_path / name).touch()
    assert get_markdown_files(tmp_path) == ["article.md"]
