import frontmatter
from html import escape
from markdown_it import MarkdownIt
from mdit_py_plugins.front_matter import front_matter_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.styles import get_style_by_name
from pygments.style import Style
from pygments.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Literal,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
)


CATPPUCCIN_FLAVORS = {
    "latte": {
        "base": "#eff1f5",
        "text": "#4c4f69",
        "overlay": "#9ca0b0",
        "red": "#d20f39",
        "peach": "#fe640b",
        "yellow": "#df8e1d",
        "green": "#40a02b",
        "teal": "#179299",
        "sky": "#04a5e5",
        "blue": "#1e66f5",
        "mauve": "#8839ef",
    },
    "frappe": {
        "base": "#303446",
        "text": "#c6d0f5",
        "overlay": "#737994",
        "red": "#e78284",
        "peach": "#ef9f76",
        "yellow": "#e5c890",
        "green": "#a6d189",
        "teal": "#81c8be",
        "sky": "#99d1db",
        "blue": "#8caaee",
        "mauve": "#ca9ee6",
    },
    "macchiato": {
        "base": "#24273a",
        "text": "#cad3f5",
        "overlay": "#6e738d",
        "red": "#ed8796",
        "peach": "#f5a97f",
        "yellow": "#eed49f",
        "green": "#a6da95",
        "teal": "#8bd5ca",
        "sky": "#91d7e3",
        "blue": "#8aadf4",
        "mauve": "#c6a0f6",
    },
    "mocha": {
        "base": "#1e1e2e",
        "text": "#cdd6f4",
        "overlay": "#6c7086",
        "red": "#f38ba8",
        "peach": "#fab387",
        "yellow": "#f9e2af",
        "green": "#a6e3a1",
        "teal": "#94e2d5",
        "sky": "#89dceb",
        "blue": "#89b4fa",
        "mauve": "#cba6f7",
    },
}


def _catppuccin_style(name: str, colors: dict):
    class _CatppuccinStyle(Style):
        background_color = colors["base"]
        default_style = colors["text"]

        styles = {
            Text: colors["text"],
            Error: colors["red"],
            Comment: f"italic {colors['overlay']}",
            Keyword: colors["mauve"],
            Keyword.Constant: colors["peach"],
            Keyword.Declaration: colors["blue"],
            Keyword.Namespace: colors["mauve"],
            Keyword.Type: colors["yellow"],
            Name: colors["text"],
            Name.Attribute: colors["yellow"],
            Name.Builtin: colors["red"],
            Name.Class: colors["yellow"],
            Name.Constant: colors["peach"],
            Name.Decorator: colors["blue"],
            Name.Exception: colors["red"],
            Name.Function: colors["blue"],
            Name.Namespace: colors["text"],
            Name.Tag: colors["blue"],
            Name.Variable: colors["text"],
            Literal: colors["peach"],
            Number: colors["peach"],
            Operator: colors["sky"],
            Punctuation: colors["teal"],
            String: colors["green"],
            Generic.Deleted: colors["red"],
            Generic.Emph: "italic",
            Generic.Heading: f"bold {colors['blue']}",
            Generic.Inserted: colors["green"],
            Generic.Strong: "bold",
        }

    _CatppuccinStyle.__name__ = f"Catppuccin{name.title()}Style"
    return _CatppuccinStyle


PYGMENTS_STYLES = {
    f"catppuccin-{name}": _catppuccin_style(name, colors)
    for name, colors in CATPPUCCIN_FLAVORS.items()
}


def register_pygments_style(name: str, style):
    if not isinstance(style, type) or not issubclass(style, Style):
        raise TypeError("style must be a pygments.style.Style subclass")
    PYGMENTS_STYLES[name] = style


def get_builtin_pygments_styles():
    return sorted(PYGMENTS_STYLES.keys())

DEFAULT_OPTIONS = {
    "syntaxHighlighting": {
        "enabled": True,
        "style": "catppuccin-mocha",
        "cssClass": "highlight",
        "noclasses": True,
    }
}


def _deep_merge(base: dict, overrides: dict) -> dict:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _get_pygments_style(style_name: str):
    if style_name in PYGMENTS_STYLES:
        return PYGMENTS_STYLES[style_name]
    return get_style_by_name(style_name)


def _get_lexer(language: str):
    if not language:
        return TextLexer()
    try:
        return get_lexer_by_name(language)
    except Exception:
        return TextLexer()


def _get_highlighter(options: dict):
    syntax_options = options["syntaxHighlighting"]
    if not syntax_options.get("enabled"):
        return None

    pygments_style = _get_pygments_style(syntax_options.get("style", "default"))
    formatter = HtmlFormatter(
        style=pygments_style,
        noclasses=syntax_options.get("noclasses", True),
        nowrap=True,
    )
    css_class = syntax_options.get("cssClass", "highlight")
    background_color = getattr(pygments_style, "background_color", None)
    style_attr = f' style="background: {background_color}; line-height: 125%;"' if background_color else ""

    def _highlight(code: str, language: str, attrs: str = "") -> str:
        language_class = f" language-{escape(language)}" if language else ""
        highlighted = highlight(code, _get_lexer(language), formatter)
        return f'<pre class="{escape(css_class)}{language_class}"{style_attr}><code>{highlighted}</code></pre>'

    return _highlight


def _markdown_it_options(options: dict) -> dict:
    markdown_options = dict(options.get("markdownIt", {}))
    highlighter = _get_highlighter(options)
    if highlighter:
        markdown_options["highlight"] = highlighter
    return markdown_options


def _initialize(options: dict = None):
    if options is None:
        options = {}
    options = _deep_merge(DEFAULT_OPTIONS, options)
    return (
        MarkdownIt("commonmark", _markdown_it_options(options))
        .use(front_matter_plugin)
        .enable(["table", "linkify", "replacements"])
    )


def parseCommonMark(markdown: str, options: dict = None):
    md = _initialize(options)
    retVal = {
        "frontmatter": frontmatter.loads(markdown).metadata,
        "markdown": md.render(markdown),
    }
    return retVal
