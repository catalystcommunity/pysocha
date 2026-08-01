"""Search index generation for pysocha.

A site can configure any number of searches. Each one names a provider, gets its
own directory in the output, and chooses which sections of the site it indexes::

    search:
      - name: "site"
        provider: "pagefind"
        path: "search"
        template: "search.jinja2"
        include: ["posts", "pages"]
        options:
          indexCode: false

The ``provider`` value is either a built-in key or a ``module:Class`` path, so a
site can supply its own provider without changing pysocha.
"""

import importlib
import os
from typing import Any, Dict, Iterable, List, Optional

from pysocha.search.types import (
    SECTION_PAGES,
    SECTION_POSTS,
    SearchAssets,
    SearchContext,
    SearchInstance,
    SearchProvider,
    SearchRecord,
)

__all__ = [
    "SECTION_PAGES",
    "SECTION_POSTS",
    "SearchAssets",
    "SearchContext",
    "SearchError",
    "SearchInstance",
    "SearchProvider",
    "SearchRecord",
    "build_search_indexes",
    "load_search_instances",
    "resolve_provider",
]


class SearchError(RuntimeError):
    pass


#: Providers that ship with pysocha.
BUILTIN_PROVIDERS = {
    "pagefind": "pysocha.search.providers.pagefind:PagefindProvider",
    "sqlite-fts5": "pysocha.search.providers.sqlite_fts:SqliteFtsProvider",
}

_KNOWN_SECTIONS = frozenset({SECTION_POSTS, SECTION_PAGES})


def resolve_provider(provider: str):
    """Resolve a provider name or ``module:Class`` path to a class."""
    target = BUILTIN_PROVIDERS.get(provider, provider)
    if ":" not in target:
        raise SearchError(
            f"unknown search provider {provider!r}. Use one of "
            f"{', '.join(sorted(BUILTIN_PROVIDERS))} or a 'module:Class' path"
        )
    module_name, _, class_name = target.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise SearchError(
            f"search provider {provider!r} could not be imported: {error}"
        ) from error
    try:
        provider_class = getattr(module, class_name)
    except AttributeError as error:
        raise SearchError(
            f"search provider {provider!r} has no class {class_name!r}"
        ) from error
    if not issubclass(provider_class, SearchProvider):
        raise SearchError(
            f"search provider {provider!r} must subclass pysocha.search.SearchProvider"
        )
    return provider_class


def load_search_instances(config: dict) -> List[SearchInstance]:
    """Parse and validate the ``search:`` section of a site config."""
    raw = config.get("search") or []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise SearchError("search config must be a list of search instances")

    instances: List[SearchInstance] = []
    seen_names = set()
    seen_paths = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise SearchError("each search entry must be a mapping")
        if entry.get("enabled") is False:
            continue
        name = entry.get("name")
        if not name:
            raise SearchError("each search entry needs a unique 'name'")
        if name in seen_names:
            raise SearchError(f"duplicate search name {name!r}")
        seen_names.add(name)

        provider = entry.get("provider")
        if not provider:
            raise SearchError(f"search {name!r} needs a 'provider'")

        path = str(entry.get("path", "search")).strip("/")
        if not path:
            raise SearchError(f"search {name!r} needs a non-empty 'path'")
        if path in seen_paths:
            raise SearchError(
                f"search {name!r} reuses path {path!r}. Each search needs its own path"
            )
        seen_paths.add(path)

        include = entry.get("include", [SECTION_POSTS])
        if isinstance(include, str):
            include = [include]
        if isinstance(include, dict):
            include = [key for key, value in include.items() if value]
        unknown = sorted(set(include) - _KNOWN_SECTIONS)
        if unknown:
            raise SearchError(
                f"search {name!r} includes unknown sections: {', '.join(unknown)}. "
                f"Known sections are {', '.join(sorted(_KNOWN_SECTIONS))}"
            )
        if not include:
            raise SearchError(f"search {name!r} must include at least one section")

        options = entry.get("options") or {}
        if not isinstance(options, dict):
            raise SearchError(f"search {name!r} options must be a mapping")

        instances.append(
            SearchInstance(
                name=name,
                provider=provider,
                path=path,
                template=entry.get("template"),
                include=list(include),
                options=options,
            )
        )
    return instances


def _make_context(config: dict, instance: SearchInstance) -> SearchContext:
    output_dir = os.path.abspath(config["outputDir"])
    instance_dir = os.path.join(output_dir, instance.path)
    return SearchContext(
        instance=instance,
        output_dir=output_dir,
        extra_files_dir=os.path.abspath(
            os.path.join(config.get("contentDir", "content"), "extra_files")
        ),
        instance_dir=instance_dir,
        instance_url="/" + instance.path + "/",
        site_address=config.get("siteAddress", ""),
        site_title=config.get("siteTitle", ""),
        language=config.get("language", "en"),
    )


def build_search_indexes(
    config: dict,
    records: Iterable[SearchRecord],
    render_page=None,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """Build every configured search index.

    ``render_page`` is an optional callable taking ``(instance, context, assets)``
    that writes the search page. It is separate so that providers stay unaware of
    templating.
    """
    instances = load_search_instances(config)
    if not instances:
        return []

    records = list(records)
    results = []
    for instance in instances:
        context = _make_context(config, instance)
        os.makedirs(context.instance_dir, exist_ok=True)
        provider_class = resolve_provider(instance.provider)
        provider = provider_class(context)

        count = 0
        for record in records:
            if instance.accepts(record):
                provider.add(record)
                count += 1

        assets = provider.finalize()
        if verbose:
            print(
                f"search '{instance.name}' ({instance.provider}): "
                f"{count} records -> {os.path.join(instance.path, '')}"
            )
        if render_page is not None and instance.template:
            render_page(instance, context, assets)
        results.append({"instance": instance, "assets": assets, "records": count})
    return results
