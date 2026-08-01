# pysocha

Pysocha is a static site generator of as simple a variety as we can make for our
needs.

It reads Markdown content and Jinja templates. It writes a directory of files.
No code runs on the server.

It still has features like search for large sites, rss and atom feeds, and extra files for things like favicons.

## Installation

Pysocha needs Python 3.8 or newer.

```bash
python -m pip install pysocha
```

With uv:

```bash
uv tool install pysocha
```

Direct from this repository:

```bash
python -m pip install git+https://github.com/catalystcommunity/pysocha.git
```

For work on Pysocha itself, use uv from the repository root:

```bash
uv sync
uv run pysocha --help
```

## Quickstart

Make a site with this shape:

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

Write a page in `content/pages/index.md`:

```markdown
---
Title: "Welcome"
---

# Welcome

This is the first page.
```

Write a post in `content/blog_posts/first-post.md`:

```markdown
---
Title: "The first post"
PostedDate: "2026-07-14T10:00:00-06:00"
Author: "Your Name"
AuthorEmail: "you@example.com"
hook: "A short summary for feeds and listings."
---

Hello.
```

Write `config.yaml`. Every key has a default, so a short file is enough:

```yaml
siteTitle: "My site"
siteAddress: "https://example.com/"
blogConfig:
  title: "My blog"
  blogBaseDir: "blog"
```

Build the site:

```bash
pysocha build --config-file config.yaml
```

Look at the site:

```bash
pysocha preview --config-file config.yaml
```

Pysocha writes the files into `outputDir`. The default is `generated`.

## What Pysocha does

- Markdown pages, with one body or with named regions.
- Blog posts, listing pages, tag pages, and author pages.
- Atom feeds and RSS feeds.
- Syntax highlighting at build time, with no style sheet.
- Search in the browser, with more than one search for each site.
- Staged output. A failed build never replaces a good site.

## Documentation

The [docs](docs/) directory holds the details:

- [Configuration](docs/configuration.md) — every key and its default.
- [Content](docs/content.md) — pages, blog posts, front matter, and regions.
- [Markdown](docs/markdown.md) — syntax highlighting and themes.
- [Feeds](docs/feeds.md) — Atom and RSS.
- [Search](docs/search.md) — search configuration and the two providers.
- [Search providers](docs/search-providers.md) — how to write your own.
- [Build behavior](docs/building.md) — commands, staged output, and preview.

## Example sites

- [`example/`](example/) in this repository. It shows every feature, and it
  includes a search page for each provider.
- [todpunk/tnl-site](https://github.com/todpunk/tnl-site) — the content of
  [todandlorna.com](https://todandlorna.com/).

## Licence

Apache-2.0.
