# Content

Pysocha reads three content directories:

```text
content/
  pages/        Markdown pages
  blog_posts/   Markdown blog posts
  extra_files/  files that Pysocha copies without change
```

Pysocha copies `extra_files` into the output directory. Put your CSS, your
JavaScript, and your images there.

## Pages

A page is a Markdown file in `content/pages`. The output name is the file name
with `defaultExtension`. The file `about.md` becomes `about.html`.

A page can contain YAML front matter and one Markdown body. Pysocha renders the
body. It gives the body to the template as `content`.

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

Pysocha gives every front-matter key to the template. `Title` becomes `Title`.

### Page front matter

| Key | Description |
| --- | --- |
| `Title` | The title of the page. |
| `Template` | The template of this page. The default is `pageDefaultTemplate`. |
| `Extension` | The output extension of this page. |
| `ContentMode` | Set to `regions` for more than one Markdown region. |
| `Unlisted` | Set to `true` to keep the page out of search. |

## Blog posts

A blog post is a Markdown file in `content/blog_posts`. The file name has no
effect on the output. Pysocha makes the output name from the title.

These front-matter keys are necessary:

```yaml
---
Title: "Post title"
PostedDate: "2026-07-14T10:00:00-06:00"
Author: "Author Name"
AuthorEmail: "author@example.com"
---
```

`AuthorEmail` is necessary for RSS. Atom uses `Author` for the display name.

### Post front matter

| Key | Description |
| --- | --- |
| `Tags` | A list of tags. Pysocha writes one page for each tag. |
| `Unlisted` | Set to `true` to keep the post out of listings, feeds, and search. |
| `hook` or `summary` | The summary text for a feed and for a listing. |
| `Template` | The template of this post. |
| `Extension` | The output extension of this post. |

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

Front matter can contain your own data, such as labels, URLs, and flags. Put
related values in a namespace such as `Components` or `Actions`. Pysocha does
not define the values in these namespaces.

Each region supports the same Markdown configuration as an ordinary page.
Pysocha also supplies `content`. For a region page, `content` contains all
region HTML in source order.

### Region rules

Pysocha applies these rules when `ContentMode` is `regions`:

- Each region name must be unique.
- Each region must contain content.
- Each opening marker must have a closing marker.
- Regions must not be inside other regions.
- Region markers must start in column 1 at the document top level.
- All Markdown body content must be inside a region.
- `content` and `content_regions` are reserved front-matter keys.

A marker inside a fenced code block is code. It does not start or end a region.

Pysocha reports the source path, the line number, and the source text for a
region error or a front-matter error.

```text
content/pages/index.md:18: duplicate region "details"
    ::: region details
```

A region page uses strict Jinja value checks. A missing value stops the build.
Use an `is defined` check for an optional value. An ordinary page keeps the
permissive Jinja behavior.
