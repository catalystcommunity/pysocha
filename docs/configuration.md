# Configuration

Pysocha reads one YAML file. Every key has a default. Your file supplies only
the keys that you change.

Pysocha merges your file into the defaults. It merges mappings key by key. It
replaces a list with your list.

## Site keys

| Key | Default | Description |
| --- | --- | --- |
| `contentDir` | `content` | Where the Markdown content is. |
| `outputDir` | `generated` | Where Pysocha writes the site. |
| `templatesDir` | `templates` | Where the Jinja templates are. |
| `siteTitle` | `Example dot Com!` | The title of the site. |
| `siteAddress` | `https://example.changeme.tld/` | The public address. Feeds need it. |
| `descending` | `True` | Sort posts with the newest first. |
| `defaultExtension` | `.html` | The extension of each output file. |
| `startPage` | `index.html` | The page that the preview server serves at `/`. |
| `language` | `en` | The ISO 639-1 language of the content. Search uses it. |
| `search` | `[]` | The list of searches. See [Search](search.md). |

`outputDir` must not be the working directory or the file system root.

## Page keys

The `pageConfig` mapping holds the page keys.

| Key | Default | Description |
| --- | --- | --- |
| `pageTitle` | `Example dot Com!` | The default title of a page. |
| `pageDefaultTemplate` | `page.jinja2` | The template of a page. |

You can add your own keys to `pageConfig`. Pysocha gives them to the template.

## Blog keys

The `blogConfig` mapping holds the blog keys.

| Key | Default | Description |
| --- | --- | --- |
| `title` | `Example blog` | The title of the blog. |
| `blogBaseDir` | `blog` | The path of the blog in the output. |
| `blogTemplate` | `blog.jinja2` | The template of one post. |
| `listingTemplate` | `listing.jinja2` | The template of a listing page. |
| `listingPaginationNum` | `5` | The number of posts on a listing page. |
| `listingKeysNeeded` | `['hook']` | The front-matter keys that your listing template needs. |
| `atomFeeds` | `True` | Write the feeds. See [Feeds](feeds.md). |
| `disableRSS` | `False` | Write no RSS feed. |
| `tagsTemplate` | `tags.jinja2` | The template that lists all tags. |
| `tagTemplate` | `tag.jinja2` | The template of one tag page. |
| `tagPaginationNum` | `5` | The number of posts on a tag page. |
| `authorsTemplate` | `authors.jinja2` | The template that lists all authors. |
| `authorTemplate` | `author.jinja2` | The template of one author page. |
| `authorPaginationNum` | `10` | The number of posts on an author page. |

You can add your own keys to `blogConfig`. Pysocha gives them to the template.

## Markdown keys

The `markdown` mapping holds the Markdown keys. See [Markdown](markdown.md).

| Key | Default | Description |
| --- | --- | --- |
| `syntaxHighlighting.enabled` | `True` | Highlight fenced code blocks. |
| `syntaxHighlighting.style` | `catppuccin-mocha` | The Pygments style. |
| `syntaxHighlighting.cssClass` | `highlight` | The CSS class of a code block. |
| `syntaxHighlighting.noclasses` | `True` | Write the colors inline. |

## Example

```yaml
contentDir: "content"
outputDir: "generated"
templatesDir: "templates"
siteTitle: "My site"
siteAddress: "https://example.com/"
defaultExtension: ".html"
startPage: "index.html"

pageConfig:
  pageTitle: "My site"
  pageDefaultTemplate: "page.jinja2"

blogConfig:
  title: "My blog"
  blogBaseDir: "blog"
  blogTemplate: "blog.jinja2"
  listingTemplate: "listing.jinja2"
  listingPaginationNum: 10
  tagsTemplate: "tags.jinja2"
  tagTemplate: "tag.jinja2"
  authorsTemplate: "authors.jinja2"
  authorTemplate: "author.jinja2"

search:
  - name: "site"
    provider: "pagefind"
    path: "search"
    template: "search.jinja2"
    include: ["posts", "pages"]
```
