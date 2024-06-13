import frontmatter
from markdown_it import MarkdownIt
from mdit_py_plugins.front_matter import front_matter_plugin

MD = None

def _initialize(options: dict = None):
    global MD
    if options is None:
        options = {}
    MD = (
        MarkdownIt("commonmark", options)
        .use(front_matter_plugin)
        .enable(['table', 'linkify', 'replacements'])
    )

def parseCommonMark(markdown: str, options: dict = None):
    global MD
    if options is None:
        options = {}
    if MD is None:
        _initialize(options)
    retVal = {
        'frontmatter': frontmatter.loads(markdown).metadata,
        'markdown': MD.render(markdown)
    }
    return retVal
