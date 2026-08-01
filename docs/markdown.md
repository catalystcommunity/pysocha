# Markdown

Pysocha reads CommonMark. It supports headings, paragraphs, emphasis, lists,
links, tables, inline code, and fenced code blocks.

## Syntax highlighting

Pysocha highlights fenced code blocks at build time with Pygments. The generated
page stays static. Pysocha writes the highlighting as HTML.

Syntax highlighting is on by default.

```yaml
markdown:
  syntaxHighlighting:
    enabled: True
    style: "catppuccin-mocha"
    cssClass: "highlight"
    noclasses: True
```

With `noclasses: True`, Pysocha writes the colors inline. The page needs no
style sheet.

With `noclasses: False`, Pygments writes token classes. Supply the matching
Pygments CSS in your template or in `extra_files`.

To stop highlighting for a site:

```yaml
markdown:
  syntaxHighlighting:
    enabled: False
```

## Styles

`style` defaults to `catppuccin-mocha`. Pysocha includes all Catppuccin
flavors:

- `catppuccin-latte`
- `catppuccin-frappe`
- `catppuccin-macchiato`
- `catppuccin-mocha`

You can use any style that Pygments supplies, such as `monokai`, `dracula`, or
`friendly`.

## Your own theme

A theme is a Pygments `Style` class. Register the class before Pysocha renders
the Markdown.

```python
from pygments.style import Style
from pygments.token import Keyword, Name, Text
from pysocha.markdown import register_pygments_style


class MyTheme(Style):
    background_color = "#111111"
    default_style = "#eeeeee"
    styles = {
        Text: "#eeeeee",
        Keyword: "#ffcc66",
        Name.Function: "#66d9ef",
    }


register_pygments_style("my-theme", MyTheme)
```

Then select the theme in the configuration:

```yaml
markdown:
  syntaxHighlighting:
    enabled: True
    style: "my-theme"
```

## Code and search

A search index does not contain the text of a code block by default. Code makes
an index much larger. A reader rarely searches for it.

To index code, set `indexCode` in the search options. See [Search](search.md).
