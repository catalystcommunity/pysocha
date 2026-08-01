# Search providers

A search provider turns the documents of a site into a search index. Pysocha
supplies two providers. You can write your own.

A provider needs four types. Pysocha shares nothing else with it.

## The contract

```python
from pysocha.search import SearchProvider, SearchAssets


class MyProvider(SearchProvider):
    name = "my-provider"

    def __init__(self, context):
        super().__init__(context)
        self.records = []

    def add(self, record):
        """Take one document."""
        self.records.append(record)

    def finalize(self):
        """Write the index. Say what the page must load."""
        return SearchAssets(scripts=[], styles=[], data={})
```

Pysocha makes one provider for each search in each build. It gives the provider
each document that the search accepts. Then it calls `finalize`.

A provider never sees HTML. A provider never reads the generated site.

## SearchRecord

One document. The text is plain text.

| Field | Description |
| --- | --- |
| `url` | The URL from the root of the site, such as `/blog/my-post.html`. |
| `title` | The title of the document. |
| `content` | The body text, without the code blocks. |
| `code` | The text of the code blocks. Use `text()` instead of this field. |
| `section` | `posts` or `pages`. |
| `language` | The ISO 639-1 language code. |
| `date` | The publication date, or `None`. |
| `meta` | Extra display values. Flat strings. |
| `filters` | Facet values. Flat lists of strings. |
| `sort` | Sort keys. Flat strings. |

Use `record.text(include_code)` for the text to index:

```python
text = record.text(self.options.get("indexCode", False))
```

Code makes an index much larger. A reader rarely searches for it. Index the code
only when the site asks for it.

## SearchContext

What a provider knows about the build.

| Field | Description |
| --- | --- |
| `instance` | The configuration of this search. |
| `output_dir` | The site root. Write only inside this directory. |
| `instance_dir` | The directory of this search. |
| `instance_url` | The URL of this search, such as `/search/`. |
| `extra_files_dir` | The `extra_files` directory of the site. |
| `site_address` | The public address of the site. |
| `site_title` | The title of the site. |
| `language` | The default language. |
| `options` | The `options` mapping from the configuration. |

Write your files into `instance_dir`. Pysocha makes the directory before it
calls the provider.

Write a cached download into `extra_files_dir`. The file then becomes part of
the source of the site.

## SearchAssets

What the search page must load.

| Field | Description |
| --- | --- |
| `scripts` | The URLs of the scripts, in load order. |
| `styles` | The URLs of the style sheets. |
| `data` | Your own values. The template reads them as `search.data`. |

## Paths and URLs

Make a file path with `os.path.join`. Make a URL with a forward slash.

```python
path = os.path.join(self.context.instance_dir, "index.json")   # correct
url = self.context.instance_url + "index.json"                 # correct
url = os.path.join(self.context.instance_url, "index.json")    # wrong
```

The last line writes a backslash on Windows. A URL must never hold one.

## Use your provider

Give the `module:Class` path as the provider:

```yaml
search:
  - name: "site"
    provider: "mypackage.search:MyProvider"
    path: "search"
    template: "search.jinja2"
    include: ["posts", "pages"]
    options:
      myOption: true
```

Pysocha imports the module and checks that the class is a `SearchProvider`.
Pysocha does not read `options`. It gives them to your provider.

## A complete example

This provider writes one JSON file of titles and URLs.

```python
import json
import os

from pysocha.search import SearchAssets, SearchProvider


class TitleIndexProvider(SearchProvider):
    """Write a small index of titles."""

    name = "title-index"

    def __init__(self, context):
        super().__init__(context)
        self.records = []

    def add(self, record):
        self.records.append(record)

    def finalize(self):
        entries = [
            {"url": record.url, "title": record.title}
            for record in self.records
        ]
        path = os.path.join(self.context.instance_dir, "titles.json")
        with open(path, "w") as handle:
            json.dump(entries, handle)
        return SearchAssets(
            data={"index": self.context.instance_url + "titles.json",
                  "recordCount": len(entries)},
        )
```
