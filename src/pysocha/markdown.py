from __future__ import annotations

import frontmatter
from html import escape
import re
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

CONTENT_MODE_KEY = "ContentMode"
CONTENT_MODE_REGIONS = "regions"
REGION_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
REGION_OPEN_PATTERN = re.compile(r"^:::\s+region(?:\s+(.*?))?\s*$")
REGION_CLOSE_PATTERN = re.compile(r"^:::\s*$")
RICH_PAGE_RESERVED_KEYS = {"content", "content_regions"}


class MarkdownContentError(ValueError):
    def __init__(self, source: str, errors: list[tuple[int, str, str]]):
        self.source = source
        self.errors = errors
        lines = []
        for line_number, message, excerpt in errors:
            location = f"{source}:{line_number}" if line_number else source
            lines.append(f"{location}: {message}")
            if excerpt:
                lines.append(f"    {excerpt}")
        super().__init__("\n".join(lines))


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


def _region_plugin(md: MarkdownIt):
    def region_rule(state, start_line: int, _end_line: int, silent: bool) -> bool:
        start = state.bMarks[start_line] + state.tShift[start_line]
        maximum = state.eMarks[start_line]
        line = state.src[start:maximum]
        open_match = REGION_OPEN_PATTERN.fullmatch(line)
        is_close = REGION_CLOSE_PATTERN.fullmatch(line)
        if open_match is None and is_close is None:
            return False
        if silent:
            return True

        token_type = "content_region_open" if open_match is not None else "content_region_close"
        token = state.push(token_type, "", 0)
        token.block = True
        token.map = [start_line, start_line + 1]
        token.meta = {
            "name": open_match.group(1) if open_match is not None else None,
            "column": state.tShift[start_line] + 1,
        }
        state.line = start_line + 1
        return True

    def render_region_marker(*_args, **_kwargs) -> str:
        return ""

    md.block.ruler.before(
        "fence",
        "content_region",
        region_rule,
        {"alt": ["paragraph", "reference", "blockquote", "list"]},
    )
    md.add_render_rule("content_region_open", render_region_marker)
    md.add_render_rule("content_region_close", render_region_marker)


def _line_details(markdown: str, token) -> tuple[int, str]:
    if not token.map:
        return 0, ""
    line_index = token.map[0]
    source_lines = markdown.splitlines()
    excerpt = source_lines[line_index].strip() if line_index < len(source_lines) else ""
    return line_index + 1, excerpt


def _frontmatter_key_details(markdown: str, key: str) -> tuple[int, str]:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:")
    for index, line in enumerate(markdown.splitlines()):
        if pattern.match(line):
            return index + 1, line.strip()
    return 1, ""


def _parse_regions(md: MarkdownIt, markdown: str, source: str) -> tuple[str, dict[str, str]]:
    env = {}
    tokens = md.parse(markdown, env)
    errors = []
    regions = {}
    current_name = None
    current_tokens = []
    seen_names = set()

    for token in tokens:
        if token.type == "front_matter":
            continue

        if token.type == "content_region_open":
            line_number, excerpt = _line_details(markdown, token)
            name = (token.meta.get("name") or "").strip()
            if token.level != 0 or token.meta.get("column") != 1:
                errors.append((line_number, "region directives must start at the top level in column 1", excerpt))
            if current_name is not None:
                errors.append((line_number, f'region "{name}" is nested inside region "{current_name}"', excerpt))
            if not name:
                errors.append((line_number, "region name is missing", excerpt))
            elif not REGION_NAME_PATTERN.fullmatch(name):
                errors.append((line_number, f'invalid region name "{name}"', excerpt))
            elif name in seen_names:
                errors.append((line_number, f'duplicate region "{name}"', excerpt))

            if current_name is None:
                current_name = name
                current_tokens = []
                if name:
                    seen_names.add(name)
            continue

        if token.type == "content_region_close":
            line_number, excerpt = _line_details(markdown, token)
            if token.level != 0 or token.meta.get("column") != 1:
                errors.append((line_number, "region directives must start at the top level in column 1", excerpt))
            if current_name is None:
                errors.append((line_number, "region closing marker has no opening marker", excerpt))
            else:
                if not current_tokens:
                    errors.append((line_number, f'region "{current_name}" is empty', excerpt))
                elif REGION_NAME_PATTERN.fullmatch(current_name) and current_name not in regions:
                    regions[current_name] = md.renderer.render(current_tokens, md.options, env)
                current_name = None
                current_tokens = []
            continue

        if current_name is None:
            line_number, excerpt = _line_details(markdown, token)
            if excerpt.startswith(":::"):
                message = "malformed region directive"
            else:
                message = "Markdown content is outside a region"
            errors.append((line_number, message, excerpt))
        else:
            current_tokens.append(token)

    if current_name is not None:
        open_line = next(
            (
                token
                for token in reversed(tokens)
                if token.type == "content_region_open"
                and (token.meta.get("name") or "").strip() == current_name
            ),
            None,
        )
        line_number, excerpt = _line_details(markdown, open_line) if open_line else (0, "")
        errors.append((line_number, f'region "{current_name}" has no closing marker', excerpt))

    if errors:
        raise MarkdownContentError(source, errors)

    content_tokens = [
        token
        for token in tokens
        if token.type not in {"content_region_open", "content_region_close"}
    ]
    content = md.renderer.render(content_tokens, md.options, env)
    return content, regions


def parseCommonMark(markdown: str, options: dict = None, source: str = "<string>"):
    try:
        post = frontmatter.loads(markdown)
    except Exception as error:
        problem_mark = getattr(error, "problem_mark", None)
        line_number = problem_mark.line + 1 if problem_mark is not None else 1
        source_lines = markdown.splitlines()
        excerpt = source_lines[line_number - 1].strip() if line_number <= len(source_lines) else ""
        problem = getattr(error, "problem", None) or str(error)
        raise MarkdownContentError(
            source,
            [(line_number, f"invalid front matter: {problem}", excerpt)],
        ) from error

    metadata = post.metadata
    md = _initialize(options)
    content_mode = metadata.get(CONTENT_MODE_KEY)
    if content_mode == CONTENT_MODE_REGIONS:
        conflicts = sorted(RICH_PAGE_RESERVED_KEYS.intersection(metadata))
        if conflicts:
            errors = []
            for key in conflicts:
                line_number, excerpt = _frontmatter_key_details(markdown, key)
                errors.append((line_number, f'front-matter key "{key}" is reserved by Pysocha', excerpt))
            raise MarkdownContentError(source, errors)
        _region_plugin(md)
        rendered, regions = _parse_regions(md, markdown, source)
    else:
        rendered = md.render(markdown)
        regions = None

    retVal = {
        "frontmatter": metadata,
        "markdown": rendered,
    }
    if regions is not None:
        retVal["content_regions"] = regions
    return retVal
