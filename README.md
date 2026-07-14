# pysocha

pysocha is a static site generator of as simple a variety as we can make for our needs.

## Installation

Pysocha requires Python 3.8 or newer.

Install from PyPI when a release is available:

```bash
python -m pip install pysocha
```

Install with uv:

```bash
uv tool install pysocha
```

Install directly from this repository:

```bash
python -m pip install git+https://github.com/catalystcommunity/pysocha.git
```

For local development, use uv from the repository root:

```bash
uv sync
uv run pysocha --help
```

## Usage

Create a site with this shape:

```text
site/
  config.yaml
  content/
    pages/
      index.md
    blog_posts/
      first-post.md
    extra_files/
      main.css
  templates/
    page.jinja2
    blog.jinja2
    listing.jinja2
    tags.jinja2
    tag.jinja2
    authors.jinja2
    author.jinja2
```

Build the site:

```bash
pysocha build --config-file config.yaml
```

Preview the generated site locally:

```bash
pysocha preview --config-file config.yaml
```

The generated files are written to `outputDir` from your config. Extra files are
copied from `content/extra_files` into that output directory.

## Feeds

When `blogConfig.atomFeeds` is true, Pysocha generates both feed formats for
listed blog posts:

- `atom.xml`
- `rss.xml`

The name is kept as `atomFeeds` for compatibility with existing configs.

## Syntax highlighting

Pysocha can syntax-highlight triple-backtick fenced code blocks at build time with
Pygments. The generated pages stay static: highlighting is emitted as HTML, and
with the default `noclasses: True` setting the color styles are emitted inline.
Syntax highlighting is enabled by default.

```yaml
markdown:
  syntaxHighlighting:
    enabled: True
    style: "catppuccin-mocha"
    cssClass: "highlight"
    noclasses: True
```

`style` defaults to `catppuccin-mocha`. Pysocha includes all Catppuccin flavors:

- `catppuccin-latte`
- `catppuccin-frappe`
- `catppuccin-macchiato`
- `catppuccin-mocha`

You can also use any style name installed with Pygments, such as `monokai`,
`dracula`, or `friendly`.

To keep CSS out of the generated markup, set `noclasses: False`; Pygments will
emit token classes instead of inline token colors. In that mode, include matching
Pygments CSS in your template or copied static files.

To disable highlighting for a site:

```yaml
markdown:
  syntaxHighlighting:
    enabled: False
```

### Adding Themes

Themes are Pygments `Style` classes. Register one before rendering markdown:

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

Then select it in config:

```yaml
markdown:
  syntaxHighlighting:
    enabled: True
    style: "my-theme"
```
