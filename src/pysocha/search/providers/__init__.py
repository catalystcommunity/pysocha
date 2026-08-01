"""Search providers that ship with pysocha.

Each provider is imported lazily by :func:`pysocha.search.resolve_provider`, so
a provider's third-party dependencies are only needed by sites that use it.
"""
