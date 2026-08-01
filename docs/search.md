# Search

Pysocha can build a search index for a site. The search runs in the browser. No
code runs on the server.

A site can have more than one search. Each search has its own path, its own
provider, and its own part of the site.

## Configuration

```yaml
search:
  - name: "site"
    provider: "pagefind"
    path: "search"
    template: "search.jinja2"
    include: ["posts", "pages"]
    options: {}
```

| Key | Default | Description |
| --- | --- | --- |
| `name` | none | A unique name. Pysocha uses it in messages. Necessary. |
| `provider` | none | A provider name or a `module:Class` path. Necessary. |
| `path` | `search` | The directory of this search. `search` gives `/search/`. |
| `template` | none | The template of the search page. Without it, Pysocha writes the index but no page. |
| `include` | `["posts"]` | The parts of the site to index. Use `posts`, `pages`, or both. |
| `options` | `{}` | The options of the provider. Pysocha does not read them. |
| `enabled` | `true` | Set to `false` to skip this search. |

Each `name` must be unique. Each `path` must be unique.

## What Pysocha indexes

Pysocha indexes the rendered body of each document. It does not index the
finished page. Your navigation, your header, and your footer never reach the
index. Your templates need no markup for search.

Pysocha does not index a document with `Unlisted: true`.

Pysocha keeps the text of code blocks apart from the prose. A provider indexes
the code only when `indexCode` is `true`.

Each record holds the URL, the title, the body text, the date, the author, and
the tags. Every URL starts at the root of the site, such as
`/blog/my-post.html`.

## The search page

Pysocha renders the template into `<path>/index.html`. The template gets a
`search` mapping:

| Key | Description |
| --- | --- |
| `search.name` | The name of this search. |
| `search.path` | The path of this search. |
| `search.url` | The URL of this search, such as `/search/`. |
| `search.provider` | The provider of this search. |
| `search.scripts` | The scripts to load, in order. |
| `search.styles` | The style sheets to load. |
| `search.data` | The values of the provider. |

To put a search box on every page, add a link to `search.url` in your base
template. The `example/templates` directory has a complete search page for each
provider.

## The pagefind provider

Pagefind divides the index into small parts. The browser reads only the parts
that a query needs. Use this provider for a large site.

Install the provider:

```bash
pip install 'pysocha[search-pagefind]'
```

The provider needs Python 3.9 or newer. Pysocha itself needs Python 3.8 or
newer.

```yaml
search:
  - name: "site"
    provider: "pagefind"
    path: "search"
    template: "search.jinja2"
    include: ["posts", "pages"]
    options:
      indexCode: false
```

| Option | Default | Description |
| --- | --- | --- |
| `indexCode` | `false` | Index the text of code blocks. |
| `language` | the site `language` | The language of a record without one. |
| `forceLanguage` | none | Build one index for the site in this language. |
| `includeCharacters` | none | More characters to keep in a word. |
| `baseUrl` | `/` | The prefix of each result URL. |
| `verbose` | `false` | Write more messages while it builds. |

The template gets these values in `search.data`:

| Value | Description |
| --- | --- |
| `module` | The URL of the Pagefind module. |
| `bundlePath` | The directory of the Pagefind files. |
| `baseUrl` | The value for `pagefind.options()`. |
| `recordCount` | The number of indexed documents. |

Give `baseUrl` to Pagefind before you start it. The Pagefind files are inside
the search directory. Without `baseUrl`, Pagefind reads the search path as the
root of the site, and every result URL is wrong.

```js
const pagefind = await import("{{ search.data.module }}");
await pagefind.options({ baseUrl: "{{ search.data.baseUrl }}" });
await pagefind.init();
const results = await pagefind.search("static site");
```

Pagefind sorts by relevance or by one sort key. It cannot do both. It has no
setting for recency.

## The sqlite-fts5 provider

This provider writes one SQLite database. The browser reads the database with
HTTP range requests. It reads only the pages that a query needs.

Use this provider when you want control of the ranking. The score is BM25 and a
recency factor together. A news site can put a good match from last week above
an equal match from four years ago.

This provider needs no extra Python package. FTS5 is part of the standard
library.

```yaml
search:
  - name: "news"
    provider: "sqlite-fts5"
    path: "news-search"
    template: "search-sqlite.jinja2"
    include: ["posts"]
    options:
      halfLifeDays: 30
      titleWeight: 10.0
```

| Option | Default | Description |
| --- | --- | --- |
| `indexCode` | `false` | Index the text of code blocks. |
| `halfLifeDays` | `0` | The age at which a document keeps half its relevance. `0` gives pure relevance. |
| `titleWeight` | `10.0` | The BM25 weight of the title. |
| `tagWeight` | `5.0` | The BM25 weight of the tags. |
| `pageSize` | `4096` | The SQLite page size. A small page gives small range requests. |
| `databaseName` | `search.db` | The file name of the database. |
| `frontend` | `true` | Write the browser code and get the SQLite build. |
| `assetsDir` | `vendor/sql.js-httpvfs` | The directory of the SQLite build, inside `extra_files`. |
| `assetsVersion` | the pinned version | The version of the SQLite build. |
| `download` | `true` | Get the SQLite build when it is absent. |
| `registry` | the public npm registry | Where to get the SQLite build. |

The recency factor is:

```text
1 / (1 + age_in_days / halfLifeDays)
```

At an age of `halfLifeDays`, a document keeps half its relevance. This uses only
arithmetic, because some WebAssembly builds of SQLite have no math functions.

### The browser build

This provider needs a WebAssembly build of SQLite. Pysocha does not supply it.
The file is large, and it belongs to another project.

On the first build, Pysocha gets the build, compares it against a pinned hash,
and writes it into `extra_files`. Pysocha reports what it did:

```text
search: sql.js-httpvfs 0.8.12 is not in .../content/extra_files/vendor/sql.js-httpvfs.
search: fetching it once from https://registry.npmjs.org/...
search: the files are written into your extra_files directory, so this build is
        the only one that needs the network. Commit them to vendor them yourself.
```

After the first build, the files are part of your own source. No later build
needs the network. You can commit the files.

If the hash does not agree, Pysocha writes nothing and stops the build.

To keep your own copy, put the files in `assetsDir` yourself. Pysocha uses what
is there and gets nothing.

To stop the download, set `download: false`. A missing build then stops the
build with a message.

### The server

The web server must answer range requests. The Caddy `file_server` directive
does this by default. The Pysocha preview server does it too.

### Ranking from Python

The manifest holds the ranking query. The page and Python run the same SQL, so
you can test the ranking without a browser.

```python
from pysocha.search.providers.sqlite_fts import search

for row in search("generated/news-search/search.db", "static site",
                  half_life_days=30):
    print(row["score"], row["url"], row["title"])
```

### The browser API

Load the scripts from `search.scripts` in order. Then start the search:

```js
const search = await PysochaSearch.create({
    manifest: "{{ search.data.manifest }}",
    worker: "{{ search.data.worker }}",
    wasm: "{{ search.data.wasm }}"
});
const rows = await search.query("static site");
const used = await search.stats();
```

Each row holds `url`, `title`, `date`, `section`, `excerpt`, `meta`,
`relevance`, and `score`. The excerpt holds `<mark>` elements.

`stats()` reports how many bytes the browser read.

## Which provider

| Question | pagefind | sqlite-fts5 |
| --- | --- | --- |
| Extra Python package | yes | no |
| First download for the reader | about 160 KB | about 1.3 MB |
| Ranking by relevance | yes | yes |
| Ranking by relevance and age together | no | yes |
| Needs range requests | no | yes |
| Python 3.8 | no | yes |

Both providers work for a large site. The difference is control of the ranking.
