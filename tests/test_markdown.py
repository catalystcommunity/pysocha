import pytest

from pysocha.markdown import (
    MarkdownContentError,
    get_builtin_pygments_styles,
    parseCommonMark,
)


def test_fenced_code_highlighting_is_enabled_by_default():
    fence = "`" * 3
    markdown = f"{fence}python\ndef hello():\n    return 1\n{fence}"

    html = parseCommonMark(markdown)["markdown"]

    assert html.startswith("<pre")
    assert "highlight language-python" in html
    assert "#1e1e2e" in html.lower()
    assert "hello" in html


def test_all_catppuccin_styles_render():
    fence = "`" * 3
    markdown = f"{fence}python\ndef hello():\n    return 1\n{fence}"
    expected = [
        "catppuccin-frappe",
        "catppuccin-latte",
        "catppuccin-macchiato",
        "catppuccin-mocha",
    ]

    assert get_builtin_pygments_styles() == expected
    for style in expected:
        html = parseCommonMark(markdown, {"syntaxHighlighting": {"style": style}})["markdown"]
        assert html.startswith("<pre")
        assert "highlight language-python" in html
        assert "hello" in html


def test_unknown_language_falls_back_to_text():
    fence = "`" * 3
    markdown = f"{fence}not-a-real-language\nsome < text\n{fence}"

    html = parseCommonMark(markdown)["markdown"]

    assert html.startswith("<pre")
    assert "some &lt; text" in html


def test_ordinary_markdown_keeps_single_body_behavior():
    markdown = (
        "---\nTitle: Ordinary\nContentMode: site-specific-value\n---\n"
        "# Heading\n\nBody with *emphasis*.\n"
    )

    result = parseCommonMark(markdown)

    assert result["markdown"] == "\n<h1>Heading</h1>\n<p>Body with <em>emphasis</em>.</p>\n"
    assert "content_regions" not in result


def test_rich_markdown_provides_distinct_regions_with_normal_markdown():
    fence = "`" * 3
    markdown = f"""---
ContentMode: regions
---
::: region introduction
# A useful heading

Body with **strong text**, `code`, and [a link](other.md).
:::

::: region details
- First item
- Second item

{fence}python
def hello():
    return 1
{fence}
:::
"""

    result = parseCommonMark(markdown, source="content/pages/index.md")

    assert list(result["content_regions"]) == ["introduction", "details"]
    assert "<h1>A useful heading</h1>" in result["content_regions"]["introduction"]
    assert "<strong>strong text</strong>" in result["content_regions"]["introduction"]
    assert '<a href="other.md">a link</a>' in result["content_regions"]["introduction"]
    assert "<ul>" in result["content_regions"]["details"]
    assert "highlight language-python" in result["content_regions"]["details"]
    assert "::: region" not in result["markdown"]
    assert "A useful heading" in result["markdown"]
    assert "First item" in result["markdown"]


def test_region_marker_inside_fenced_code_is_code():
    fence = "`" * 3
    markdown = f"""---
ContentMode: regions
---
::: region example
{fence}text
::: region not-a-region
:::
{fence}
:::
"""

    result = parseCommonMark(markdown)

    assert list(result["content_regions"]) == ["example"]
    assert "::: region not-a-region" in result["content_regions"]["example"]


def test_reference_links_can_use_definitions_from_another_region():
    markdown = """---
ContentMode: regions
---
::: region introduction
Read the [shared guide][guide].
:::

::: region references
[guide]: guide.md

The link definition is page-wide.
:::
"""

    result = parseCommonMark(markdown)

    assert '<a href="guide.md">shared guide</a>' in result["content_regions"]["introduction"]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("::: region first\nText\n", 'region "first" has no closing marker'),
        (":::\n", "region closing marker has no opening marker"),
        ("::: region bad name\nText\n:::\n", 'invalid region name "bad name"'),
        (
            "::: region first\nText\n:::\n::: region first\nAgain\n:::\n",
            'duplicate region "first"',
        ),
        ("Text before a region\n::: region first\nText\n:::\n", "Markdown content is outside a region"),
        ("::: region empty\n:::\n", 'region "empty" is empty'),
        (
            "::: region outer\nText\n::: region inner\nMore text\n:::\n:::\n",
            'region "inner" is nested inside region "outer"',
        ),
    ],
)
def test_invalid_region_content_reports_source_and_excerpt(body, message):
    markdown = f"---\nContentMode: regions\n---\n{body}"

    with pytest.raises(MarkdownContentError) as caught:
        parseCommonMark(markdown, source="content/pages/index.md")

    error = str(caught.value)
    assert "content/pages/index.md:" in error
    assert message in error


def test_reserved_rich_page_frontmatter_key_is_an_error():
    markdown = """---
ContentMode: regions
content_regions:
  old: value
---
::: region main
Text
:::
"""

    with pytest.raises(MarkdownContentError) as caught:
        parseCommonMark(markdown, source="content/pages/index.md")

    error = str(caught.value)
    assert "content/pages/index.md:3" in error
    assert 'front-matter key "content_regions" is reserved by Pysocha' in error


def test_invalid_frontmatter_reports_source_line():
    markdown = "---\nTitle: [invalid\n---\nText\n"

    with pytest.raises(MarkdownContentError) as caught:
        parseCommonMark(markdown, source="content/pages/index.md")

    error = str(caught.value)
    assert "content/pages/index.md:3" in error
    assert "invalid front matter" in error
