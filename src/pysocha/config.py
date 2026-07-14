import copy
import yaml

default_yaml = """
contentDir: "content"
outputDir: "generated"
templatesDir: "templates"
siteTitle: "Example dot Com!"
siteAddress: "https://example.changeme.tld/"
descending: True
defaultExtension: ".html"
startPage: "index.html"
markdown:
  syntaxHighlighting:
    enabled: True
    style: "catppuccin-mocha"
    cssClass: "highlight"
    noclasses: True
pageConfig: 
  pageTitle: "Example dot Com!"
  pageDefaultTemplate: "page.jinja2"
blogConfig: 
  title: "Example blog"
  blogBaseDir: "blog"
  blogTemplate: "blog.jinja2"
  listingTemplate: "listing.jinja2"
  listingPagination_num: 5
  listingKeysNeeded: ['hook']
  atomFeeds: True
  disableRSS: False
  tagsTemplate: "tags.jinja2"
  tagTemplate: "tag.jinja2"
  tagPaginationNum: 5
  authorsTemplate: "authors.jinja2"
  authorTemplate: "author.jinja2"
  authorPaginationNum: 10
"""

CONFIG = yaml.safe_load(default_yaml)


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    merged = copy.deepcopy(defaults)
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def override_config(overrides: dict) -> dict:
    return _deep_merge(CONFIG, overrides)
