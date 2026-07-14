from pysocha.markdown import get_builtin_pygments_styles, parseCommonMark


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
