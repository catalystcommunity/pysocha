"""SQLite FTS5 search provider.

This provider writes one SQLite database that holds the whole index. A browser
reads it with byte-range requests, so it downloads only the pages it needs
instead of the whole file. The web server must answer range requests. Caddy's
``file_server`` does this by default.

The reason to choose this provider over Pagefind is control of the ranking
function. Pagefind sorts by relevance or by a sort key, never by both. Here the
score is BM25 multiplied by a recency factor, so a news site can rank a good
match from last week above an equally good match from four years ago.

The recency factor is::

    1 / (1 + age_in_days / halfLifeDays)

At an age of ``halfLifeDays`` a document keeps half its relevance. This uses
only arithmetic, because the SQLite math functions are not present in every
WebAssembly build.

Options, under ``options:`` in the search config:

``indexCode``
    Index the text of code blocks as well as prose. Defaults to false.
``halfLifeDays``
    Age at which a document keeps half its relevance. Set to 0 to rank purely
    by relevance. Defaults to 0, so ranking is pure BM25 until you ask for
    recency.
``titleWeight``
    BM25 weight of the title column. Defaults to 10.0.
``tagWeight``
    BM25 weight of the tag column. Defaults to 5.0.
``pageSize``
    SQLite page size. Smaller pages mean more, smaller range requests.
    Defaults to 4096.
``databaseName``
    File name of the database. Defaults to ``search.db``.
``frontend``
    Write the browser code and make sure the SQLite WebAssembly build is
    present. Defaults to true. Set it to false to build only the database.
``assetsDir``
    Where the WebAssembly build lives, inside ``extra_files``. Defaults to
    ``vendor/sql.js-httpvfs``.
``assetsVersion``
    Which version of that build to use. Defaults to the pinned version.
``download``
    Fetch the WebAssembly build when it is missing. Defaults to true. With
    false, a missing build stops the build with an error instead.
``registry``
    Where to fetch it from. Defaults to the public npm registry.

The WebAssembly build is not shipped with pysocha. The first build that needs it
downloads it into ``extra_files``, checks it against a pinned hash, and says so.
After that it is part of the site's own source, so no later build needs the
network and the files can be committed.
"""

import json
import os
import shutil
import sqlite3
from typing import Any, Dict, List, Optional

from pysocha.search.types import SearchAssets, SearchContext, SearchProvider, SearchRecord
from pysocha.search.vendor import DEFAULT_REGISTRY, SQL_JS_HTTPVFS, ensure_assets


DEFAULT_DATABASE_NAME = "search.db"
DEFAULT_ASSETS_DIR = "vendor/sql.js-httpvfs"
FRONTEND_SCRIPT_NAME = "sqlite-search.js"
DEFAULT_PAGE_SIZE = 4096
DEFAULT_TITLE_WEIGHT = 10.0
DEFAULT_TAG_WEIGHT = 5.0

SCHEMA = """
CREATE TABLE documents (
    id       INTEGER PRIMARY KEY,
    url      TEXT NOT NULL,
    title    TEXT NOT NULL,
    section  TEXT NOT NULL,
    language TEXT,
    date     TEXT,
    epoch    INTEGER,
    meta     TEXT
);
CREATE VIRTUAL TABLE documents_fts USING fts5(
    title,
    content,
    tags,
    tokenize = 'porter unicode61',
    prefix = '2 3'
);
"""

#: The ranking query. The frontend and the Python helper both use this, so the
#: ranking a site tests is the ranking it ships.
SEARCH_SQL = """
SELECT
    d.url        AS url,
    d.title      AS title,
    d.section    AS section,
    d.date       AS date,
    d.meta       AS meta,
    snippet(documents_fts, 1, :open_tag, :close_tag, :ellipsis, :snippet_words) AS excerpt,
    -bm25(documents_fts, :title_weight, 1.0, :tag_weight) AS relevance,
    -bm25(documents_fts, :title_weight, 1.0, :tag_weight)
        * CASE
            WHEN :half_life <= 0 OR d.epoch IS NULL THEN 1.0
            ELSE 1.0 / (1.0 + (MAX(0, :now - d.epoch) / 86400.0) / :half_life)
          END  AS score
FROM documents_fts
JOIN documents AS d ON d.id = documents_fts.rowid
WHERE documents_fts MATCH :query
ORDER BY score DESC
LIMIT :limit
"""


class SqliteFtsProvider(SearchProvider):
    name = "sqlite-fts5"

    def __init__(self, context: SearchContext):
        super().__init__(context)
        self._records: List[SearchRecord] = []
        self._include_code = bool(self.options.get("indexCode", False))
        self._database_name = self.options.get("databaseName", DEFAULT_DATABASE_NAME)
        self._page_size = int(self.options.get("pageSize", DEFAULT_PAGE_SIZE))
        self._half_life = float(self.options.get("halfLifeDays", 0))
        self._title_weight = float(self.options.get("titleWeight", DEFAULT_TITLE_WEIGHT))
        self._tag_weight = float(self.options.get("tagWeight", DEFAULT_TAG_WEIGHT))
        self._frontend = bool(self.options.get("frontend", True))
        self._assets_dir = str(self.options.get("assetsDir", DEFAULT_ASSETS_DIR)).strip("/")
        self._assets_version = self.options.get("assetsVersion")
        self._allow_download = bool(self.options.get("download", True))
        self._registry = self.options.get("registry", DEFAULT_REGISTRY)

    def add(self, record: SearchRecord) -> None:
        self._records.append(record)

    def _write_database(self, database_path: str) -> None:
        if os.path.exists(database_path):
            os.remove(database_path)
        connection = sqlite3.connect(database_path)
        try:
            # The page size must be set before any table exists.
            connection.execute("PRAGMA page_size = {}".format(self._page_size))
            # A static file cannot use a write-ahead log.
            connection.execute("PRAGMA journal_mode = DELETE")
            try:
                connection.executescript(SCHEMA)
            except sqlite3.OperationalError as error:
                if "fts5" not in str(error):
                    raise
                raise RuntimeError(
                    "this Python was built against a SQLite without FTS5, so the "
                    "sqlite-fts5 search provider cannot build an index. The "
                    "official builds for Windows, macOS and Linux all include "
                    "FTS5. Check yours with:\n"
                    "    python -c \"import sqlite3; print([o for o in "
                    "sqlite3.connect(':memory:').execute('PRAGMA compile_options')"
                    ".fetchall() if 'FTS5' in o[0]])\""
                ) from error

            for row_id, record in enumerate(self._records, start=1):
                tags = " ".join(
                    value for values in record.filters.values() for value in values
                )
                connection.execute(
                    "INSERT INTO documents (id, url, title, section, language, date, epoch, meta)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row_id,
                        record.url,
                        record.title,
                        record.section,
                        record.language,
                        record.date.isoformat() if record.date else None,
                        int(record.date.timestamp()) if record.date else None,
                        json.dumps(record.meta, sort_keys=True),
                    ),
                )
                connection.execute(
                    "INSERT INTO documents_fts (rowid, title, content, tags) VALUES (?, ?, ?, ?)",
                    (row_id, record.title, record.text(self._include_code), tags),
                )
            connection.commit()
            # Pack the file so that range requests read as few pages as possible.
            connection.execute("VACUUM")
            connection.commit()
        finally:
            connection.close()

    def _manifest(self, database_url: str) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "database": database_url,
            "pageSize": self._page_size,
            "recordCount": len(self._records),
            "ranking": {
                "titleWeight": self._title_weight,
                "tagWeight": self._tag_weight,
                "halfLifeDays": self._half_life,
            },
            "sql": SEARCH_SQL.strip(),
        }

    def _ensure_browser_assets(self) -> str:
        """Put the SQLite WebAssembly build where the site can serve it.

        The files are kept in ``extra_files`` so that they become part of the
        site's own source after the first build. They are also copied into the
        output, because the extra files are copied before search runs and a
        download that happened just now would otherwise be missing.
        """
        source_dir = os.path.join(self.context.extra_files_dir, self._assets_dir)
        os.makedirs(source_dir, exist_ok=True)
        ensure_assets(
            SQL_JS_HTTPVFS,
            source_dir,
            version=self._assets_version,
            allow_download=self._allow_download,
            registry=self._registry,
            log=print,
        )

        output_assets_dir = os.path.join(self.context.output_dir, self._assets_dir)
        os.makedirs(output_assets_dir, exist_ok=True)
        for name in SQL_JS_HTTPVFS.wanted_files().values():
            source = os.path.join(source_dir, name)
            destination = os.path.join(output_assets_dir, name)
            if os.path.isfile(source) and not os.path.isfile(destination):
                shutil.copyfile(source, destination)
        return "/" + self._assets_dir + "/"

    def _write_frontend(self) -> str:
        """Copy the browser code next to the index it reads."""
        source = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                              "assets", FRONTEND_SCRIPT_NAME)
        destination = os.path.join(self.context.instance_dir, FRONTEND_SCRIPT_NAME)
        shutil.copyfile(source, destination)
        return self.context.instance_url + FRONTEND_SCRIPT_NAME

    def finalize(self) -> SearchAssets:
        database_path = os.path.join(self.context.instance_dir, self._database_name)
        self._write_database(database_path)

        database_url = self.context.instance_url + self._database_name
        manifest = self._manifest(database_url)
        manifest_path = os.path.join(self.context.instance_dir, "search-manifest.json")
        with open(manifest_path, "w") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)

        data = dict(manifest)
        data["manifest"] = self.context.instance_url + "search-manifest.json"
        data["databaseBytes"] = os.path.getsize(database_path)
        data["indexCode"] = self._include_code

        scripts: List[str] = []
        if self._frontend:
            assets_url = self._ensure_browser_assets()
            data["worker"] = assets_url + "sqlite.worker.js"
            data["wasm"] = assets_url + "sql-wasm.wasm"
            # The bundle must load first, because it defines createDbWorker.
            scripts.append(assets_url + "index.js")
            scripts.append(self._write_frontend())
        return SearchAssets(scripts=scripts, styles=[], data=data)


def search(
    database_path: str,
    query: str,
    now: Optional[int] = None,
    limit: int = 20,
    half_life_days: float = 0.0,
    title_weight: float = DEFAULT_TITLE_WEIGHT,
    tag_weight: float = DEFAULT_TAG_WEIGHT,
    snippet_words: int = 12,
) -> List[Dict[str, Any]]:
    """Run the shipped ranking query against a built database.

    This is the same SQL the frontend runs. It exists so that a site can check
    its ranking from Python, without a browser.
    """
    import time

    connection = sqlite3.connect("file:{}?mode=ro".format(database_path), uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            SEARCH_SQL,
            {
                "query": query,
                "now": int(time.time()) if now is None else now,
                "limit": limit,
                "half_life": half_life_days,
                "title_weight": title_weight,
                "tag_weight": tag_weight,
                "open_tag": "<mark>",
                "close_tag": "</mark>",
                "ellipsis": "…",
                "snippet_words": snippet_words,
            },
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()
