"""The data types that make up the pysocha search plugin contract.

A search provider gets a stream of :class:`SearchRecord` objects and writes
whatever artifacts it needs into the staged output directory. It returns a
:class:`SearchAssets` object that tells the search page template which files to
load. Nothing else is shared between pysocha and a provider, so a third party
only has to satisfy these three types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


#: Section names that pysocha itself produces records for.
SECTION_POSTS = "posts"
SECTION_PAGES = "pages"


@dataclass
class SearchRecord:
    """One indexable document.

    The content is already plain text. Providers never see HTML, and never
    parse the generated site, so no template markup is required to make a
    document indexable.
    """

    #: Root-relative URL of the document, for example ``/blog/my-post.html``.
    url: str
    #: Human readable title, used as the result heading.
    title: str
    #: Plain text body to index, with code blocks removed.
    content: str
    #: Text of the document's code blocks, kept apart so each search can choose
    #: whether to index it. Use :meth:`text` rather than reading this directly.
    code: str = ""
    #: Which part of the site this came from, one of the ``SECTION_*`` values.
    section: str = SECTION_PAGES
    #: ISO 639-1 language code.
    language: str = "en"
    #: Publication date, when the document has one.
    date: Optional[datetime] = None
    #: Extra display metadata, flat string values only.
    meta: Dict[str, str] = field(default_factory=dict)
    #: Facet values a provider can group results by, flat lists of strings.
    filters: Dict[str, List[str]] = field(default_factory=dict)
    #: Sort keys, flat string values only.
    sort: Dict[str, str] = field(default_factory=dict)

    def text(self, include_code: bool = False) -> str:
        """The text this record contributes to an index.

        Code blocks make an index much larger and are rarely what a reader
        searches for, so they are excluded unless a search asks for them.
        """
        if include_code and self.code:
            return self.content + "\n" + self.code
        return self.content


@dataclass
class SearchAssets:
    """What the search page template needs to load the provider frontend."""

    #: Root-relative URLs of scripts to load.
    scripts: List[str] = field(default_factory=list)
    #: Root-relative URLs of stylesheets to load.
    styles: List[str] = field(default_factory=list)
    #: Provider specific values, given to the template as ``search.data``.
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchInstance:
    """One configured search, parsed from a ``search:`` entry in the config."""

    #: Unique name. Used for output paths and for error messages.
    name: str
    #: Registry key or ``module:Class`` path of the provider.
    provider: str
    #: Root-relative directory the search page and artifacts go in.
    path: str
    #: Template that renders the search page, or None to write no page.
    template: Optional[str] = None
    #: Section names this search indexes.
    include: List[str] = field(default_factory=lambda: [SECTION_POSTS])
    #: Provider specific configuration, passed through untouched.
    options: Dict[str, Any] = field(default_factory=dict)

    def accepts(self, record: SearchRecord) -> bool:
        return record.section in self.include


@dataclass
class SearchContext:
    """Everything a provider is allowed to know about the build."""

    #: The instance being built.
    instance: SearchInstance
    #: Absolute path of the staged site root. Providers must only write here.
    output_dir: str
    #: Absolute path of the site's extra_files directory. A provider may cache
    #: downloaded browser assets here so that later builds need no network.
    extra_files_dir: str
    #: Absolute path of this instance's own directory inside the site root.
    instance_dir: str
    #: Root-relative URL of this instance's directory, with a trailing slash.
    instance_url: str
    #: Public site address from the config.
    site_address: str
    #: Site title from the config.
    site_title: str
    #: Default language for records that do not set one.
    language: str = "en"

    @property
    def options(self) -> Dict[str, Any]:
        return self.instance.options


class SearchProvider:
    """Base class for a search provider.

    Subclasses set :attr:`name` and implement :meth:`add` and :meth:`finalize`.
    A provider is constructed once per search instance per build, is given every
    record that instance accepts, and is then asked to write its artifacts.
    """

    #: Registry key that ``provider:`` in the config matches against.
    name = ""

    def __init__(self, context: SearchContext):
        self.context = context
        self.options = context.options

    def add(self, record: SearchRecord) -> None:
        """Take one record. Called once per document, in build order."""
        raise NotImplementedError

    def finalize(self) -> SearchAssets:
        """Write artifacts into ``context.instance_dir`` and describe them."""
        raise NotImplementedError
