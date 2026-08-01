# Feeds

Pysocha writes an Atom feed and an RSS feed for the blog posts. It writes them
into the blog directory:

- `atom.xml`
- `rss.xml`

Pysocha writes a feed only for a listed post. A post with `Unlisted: true` is
not in a feed.

## Configuration

```yaml
blogConfig:
  atomFeeds: True
  disableRSS: False
```

`atomFeeds` controls both feeds. The name stays the same for compatibility with
an existing configuration.

Pysocha writes the RSS feed only when these two conditions are true:

- `disableRSS` is not `true`.
- Every listed post has `AuthorEmail` in its front matter.

## Feed content

Each entry uses these front-matter keys:

| Key | Use |
| --- | --- |
| `Title` | The entry title. |
| `PostedDate` | The entry date. |
| `Author` | The author name in Atom. |
| `AuthorEmail` | The author address in RSS. |
| `hook` or `summary` | The entry summary. The title is the fallback. |

Pysocha makes each entry link from `siteAddress`, `blogBaseDir`, and the post
slug. Set `siteAddress` to the public address of the site.

Pysocha checks that each feed is well-formed XML before it writes the file.
