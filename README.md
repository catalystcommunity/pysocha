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

Show generated file paths while building:

```bash
pysocha build --config-file config.yaml --verbose
```

Preview the generated site locally:

```bash
pysocha preview --config-file config.yaml
```

The generated files are written to `outputDir` from your config. Extra files are
copied from `content/extra_files` into that output directory.

## Markdown pages

A page can contain YAML front matter and one Markdown body. Pysocha renders the
body and supplies it to the selected Jinja template as `content`.

```markdown
---
Title: "Example page"
Template: "page.jinja2"
---

# Example page

This is the page body.
```

```jinja2
<main>
  {{ content }}
</main>
```

This model is the default. Existing pages and blog posts do not need changes.

## Pages with content regions

A page can supply more than one Markdown region to its template. Set
`ContentMode` to `regions` to use this model.

```markdown
---
Title: "Example service"
Template: "service.jinja2"
ContentMode: regions
Components:
  primary_action:
    label: "Start now"
    url: "/start/"
---

::: region introduction
# A clear introduction

Use **standard Markdown** in each region.
:::

::: region details
## More information

- First item
- Second item
:::
```

Start a region with `::: region NAME`. End it with `:::`. A region name must
start with a letter. It can contain letters, numbers, hyphens, and underscores.

The template gets an ordered mapping named `content_regions`. Use bracket
access for a region name.

```jinja2
<main class="introduction">
  {{ content_regions["introduction"] }}
</main>

<aside class="details">
  {{ content_regions["details"] }}
</aside>

{% if Components is defined and Components.primary_action is defined %}
  {% with action=Components.primary_action %}
    {% include "button.jinja2" %}
  {% endwith %}
{% endif %}
```

The included template owns the button HTML.

```jinja2
<a class="button" href="{{ action.url }}">{{ action.label }}</a>
```

Front matter can contain site-specific data such as labels, URLs, variants, and
flags. Put related values in a namespace such as `Components` or `Actions`.
Pysocha does not define the values in these namespaces.

Each region supports the same Markdown configuration as an ordinary page. This
includes headings, paragraphs, emphasis, lists, links, inline code, fenced code
blocks, and syntax highlighting. Pysocha also supplies `content`. For a region
page, `content` contains all region HTML in source order.

### Region validation

Pysocha applies these rules when `ContentMode` is `regions`:

- Each region name must be unique.
- Each region must contain content.
- Each opening marker must have a closing marker.
- Regions must not be nested.
- Region markers must start in column 1 at the document top level.
- Markdown body content must be inside a region.
- `content` and `content_regions` are reserved front-matter keys.

A marker inside a fenced code block is code. It does not start or end a region.

Pysocha reports the source path, line number, and relevant source text for a
region or front-matter error.

```text
content/pages/index.md:18: duplicate region "details"
    ::: region details
```

Region pages use strict Jinja value checks. A missing required value stops the
build. Use an explicit `is defined` check for optional values. Ordinary pages
keep the existing permissive Jinja behavior.

## Staged output

Pysocha builds the complete site in a temporary directory next to `outputDir`.
It publishes the new output only after all build steps succeed. If parsing,
template rendering, feed generation, or file copying fails, Pysocha keeps the
previous output and removes the temporary output.

The publish step keeps a backup while it replaces the output directory. If the
replacement fails, Pysocha restores the backup.

## Blog Frontmatter

Blog posts are Markdown files in `content/blog_posts`. Required fields:

```yaml
---
Title: "Post title"
PostedDate: "2026-07-14T10:00:00-06:00"
Author: "Author Name"
AuthorEmail: "author@example.com"
---
```

`AuthorEmail` is required for RSS output. Atom uses `Author` for display names.

Optional fields:

- `Tags`: list of tags for tag pages
- `Unlisted`: set to `true` to keep a post out of listings and feeds
- `hook` or `summary`: feed summary text
- `Template`: per-post template override
- `Extension`: per-post output extension override

## Feeds

When `blogConfig.atomFeeds` is true, Pysocha generates feeds for listed blog
posts:

- `atom.xml`
- `rss.xml`

RSS is generated only when `disableRSS` is not true and every listed post has
`AuthorEmail` in frontmatter. The `atomFeeds` name is kept for compatibility
with existing configs.

```yaml
blogConfig:
  atomFeeds: True
  disableRSS: False
```

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
