# Build behavior

## Commands

Build the site:

```bash
pysocha build --config-file config.yaml
```

Show each generated file path:

```bash
pysocha build --config-file config.yaml --verbose
```

Build the site and serve it:

```bash
pysocha preview --config-file config.yaml
```

## Build order

Pysocha does these steps in order:

1. It reads the page names and the post names. It makes a map of Markdown links
   to output links.
2. It copies `content/extra_files` into the output directory.
3. It writes the pages.
4. It writes the blog posts, the listings, the tag pages, the author pages, and
   the feeds.
5. It builds each search index.

Search runs last, because a search index describes the finished site.

## Staged output

Pysocha builds the complete site in a temporary directory next to `outputDir`.
It publishes the new output only after all steps are successful.

If a step fails, Pysocha keeps the previous output. It removes the temporary
directory. A broken build cannot replace a good site.

The publish step keeps a backup while it replaces the output directory. If the
replacement fails, Pysocha restores the backup.

## Link replacement

Write links between Markdown files with the source file name:

```markdown
See [the diagram](diagram.md) and [the first post](first-post.md).
```

Pysocha replaces a page name with the page output name. It replaces a post name
with the post path and slug. The output extension comes from `defaultExtension`.

## Preview server

The preview server is a development tool. Do not use it in production.

The server does these things:

- It serves `startPage` at `/`.
- It serves the index file of a directory. A search page at `/search/` works.
- It answers range requests, which the `sqlite-fts5` search provider needs.
- It sets the correct content type for `.js`, `.mjs`, `.json`, `.wasm`, and
  `.css` files.

The last item is necessary because Windows reads these types from the registry.
A browser refuses to run a module with the wrong content type.

## Production server

Pysocha writes plain files. Any web server can serve them.

The `sqlite-fts5` search provider needs a server that answers range requests.
The Caddy `file_server` directive does this by default.
