import yaml

default_yaml = """
contentDir: "content"
outputDir: "generated"
templatesDir: "templates"
siteTitle: "Example dot Com!"
descending: True
defaultExtension: ".html"
startPage: "index.html"
pageConfig: 
  pageTitle: "Example dot Com!"
  pageDefaultTemplate: "page.jinja2"
blogConfig: 
  title: "Tod and Lorna blog"
  blogBaseDir: "tnlblog"
  blogTemplate: "blog.jinja2"
  listingTemplate: "listing.jinja2"
  listingPagination_num: 5
  listingKeysNeeded: ['hook']
  atomFeed: True
  tagsTemplate: "tags.jinja2"
  tagTemplate: "tag.jinja2"
  tagPaginationNum: 5
  authorsTemplate: "authors.jinja2"
  authorTemplate: "author.jinja2"
  authorPaginationNum: 10
"""

CONFIG = yaml.load(default_yaml, Loader=yaml.Loader)

def override_config(overrides: dict) -> dict:
    CONFIG.update(overrides)
    return CONFIG

