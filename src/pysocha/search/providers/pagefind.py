"""Pagefind search provider.

Pagefind normally runs over a generated site and reads the HTML back. Pysocha
already holds the text and the URL of every document, so this provider adds
records directly instead. That keeps indexing inside the build, needs no
``data-pagefind-*`` markup in templates, and never re-parses generated HTML.

Requires the Pagefind binary::

    pip install 'pysocha[search-pagefind]'

Options, under ``options:`` in the search config:

``indexCode``
    Index the text of code blocks as well as prose. Defaults to false.
``language``
    ISO 639-1 code used for records that do not set one. Defaults to the site
    language.
``forceLanguage``
    Build one index for the whole site in this language, ignoring per-record
    languages.
``includeCharacters``
    Extra characters to keep when indexing words, for technical content.
``baseUrl``
    Prefix for the URLs in search results. Defaults to ``/``. Set this only if
    the site is served from a subpath.
``verbose``
    Print extra Pagefind logging while indexing.

Each search keeps its own bundle inside its own directory, so that a site can
run more than one search. Pagefind otherwise assumes the site root is the parent
of the bundle, which would make every result URL start with the search path, so
the search page must set ``baseUrl``. The value is in ``assets.data.baseUrl``.
"""

import asyncio
import os
from typing import Any, Dict, List

from pysocha.search.types import SearchAssets, SearchContext, SearchProvider, SearchRecord


#: Directory inside the instance directory that holds the Pagefind bundle.
BUNDLE_DIRNAME = "pagefind"


def _sort_value(record: SearchRecord) -> Dict[str, str]:
    """Sort keys for a record. Pagefind sort values must be strings."""
    sort = dict(record.sort)
    if record.date is not None and "date" not in sort:
        # A fixed width string keeps lexical order the same as date order.
        sort["date"] = record.date.strftime("%Y%m%d%H%M%S")
    return sort


class PagefindProvider(SearchProvider):
    name = "pagefind"

    def __init__(self, context: SearchContext):
        super().__init__(context)
        self._records: List[SearchRecord] = []
        self._include_code = bool(self.options.get("indexCode", False))
        self._language = self.options.get("language", context.language)

    def add(self, record: SearchRecord) -> None:
        self._records.append(record)

    def _index_config(self, bundle_dir: str) -> Dict[str, Any]:
        # Closing the index context writes the bundle using this path. Leaving it
        # unset makes Pagefind write a second copy into the working directory.
        config: Dict[str, Any] = {"output_path": bundle_dir}
        if self.options.get("forceLanguage"):
            config["force_language"] = self.options["forceLanguage"]
        if self.options.get("includeCharacters"):
            config["include_characters"] = self.options["includeCharacters"]
        if self.options.get("verbose"):
            config["verbose"] = True
        return config

    async def _build(self, bundle_dir: str) -> None:
        from pagefind.index import PagefindIndex

        async with PagefindIndex(config=self._index_config(bundle_dir)) as index:
            for record in self._records:
                meta = dict(record.meta)
                meta.setdefault("title", record.title)
                await index.add_custom_record(
                    # Pagefind does not alter this, so results stay root-relative.
                    url=record.url,
                    content=record.text(self._include_code),
                    language=record.language or self._language,
                    meta=meta,
                    filters=record.filters or None,
                    sort=_sort_value(record) or None,
                )
            # The bundle is written when the context closes, using output_path.

    def finalize(self) -> SearchAssets:
        try:
            import pagefind.index  # noqa: F401
        except ImportError as error:
            raise RuntimeError(
                "the pagefind search provider needs the pagefind package. "
                "Install it with: pip install 'pysocha[search-pagefind]'"
            ) from error

        bundle_dir = os.path.join(self.context.instance_dir, BUNDLE_DIRNAME)
        os.makedirs(bundle_dir, exist_ok=True)
        asyncio.run(self._build(bundle_dir))

        bundle_url = self.context.instance_url + BUNDLE_DIRNAME + "/"
        return SearchAssets(
            # pagefind.js is a module that the search page imports, so it is not
            # listed as a plain script tag.
            scripts=[],
            styles=[],
            data={
                "provider": self.name,
                "bundlePath": bundle_url,
                "module": bundle_url + "pagefind.js",
                # Without this, Pagefind treats the bundle's parent directory as
                # the site root and every result URL gains the search path.
                "baseUrl": self.options.get("baseUrl", "/"),
                "recordCount": len(self._records),
                "indexCode": self._include_code,
            },
        )
