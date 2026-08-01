/*
 * Browser side of the pysocha sqlite-fts5 search provider.
 *
 * The index is one SQLite database. This reads it over HTTP range requests, so
 * the browser downloads only the pages a query touches, not the whole file.
 *
 * The ranking query and its parameters come from the build, through the
 * manifest. The page does not decide how results are ranked, so what you test
 * from Python is what the page runs.
 *
 * Load the sql.js-httpvfs bundle before this file, then:
 *
 *     const search = await PysochaSearch.create({
 *         manifest: "/news-search/search-manifest.json",
 *         worker: "/vendor/sql.js-httpvfs/sqlite.worker.js",
 *         wasm: "/vendor/sql.js-httpvfs/sql-wasm.wasm"
 *     });
 *     const results = await search.query("static site");
 */
(function (global) {
    "use strict";

    // Characters that mean something to the FTS5 query parser. A reader typing
    // a quote or a minus sign must not produce a syntax error.
    var FTS_SYNTAX = /["'^*():+\-]/g;

    function buildMatchQuery(text) {
        var terms = String(text || "")
            .split(/\s+/)
            .map(function (term) { return term.replace(FTS_SYNTAX, "").trim(); })
            .filter(function (term) { return term.length > 0; });
        if (terms.length === 0) {
            return null;
        }
        // The last term gets a prefix match, so results appear while typing.
        return terms
            .map(function (term, index) {
                var quoted = '"' + term + '"';
                return index === terms.length - 1 ? quoted + "*" : quoted;
            })
            .join(" ");
    }

    function create(options) {
        if (typeof global.createDbWorker !== "function") {
            return Promise.reject(new Error(
                "PysochaSearch needs the sql.js-httpvfs bundle. Load its index.js " +
                "before this file."
            ));
        }
        return fetch(options.manifest)
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("could not read " + options.manifest);
                }
                return response.json();
            })
            .then(function (manifest) {
                return global.createDbWorker(
                    [{
                        from: "inline",
                        config: {
                            serverMode: "full",
                            url: manifest.database,
                            // Matching the database page size keeps every read
                            // to a single range request.
                            requestChunkSize: manifest.pageSize
                        }
                    }],
                    options.worker,
                    options.wasm
                ).then(function (worker) {
                    return makeSearch(manifest, worker, options);
                });
            });
    }

    function makeSearch(manifest, worker, options) {
        function query(text, queryOptions) {
            queryOptions = queryOptions || {};
            var match = buildMatchQuery(text);
            if (match === null) {
                return Promise.resolve([]);
            }
            var ranking = manifest.ranking || {};
            var params = {
                ":query": match,
                ":now": Math.floor(Date.now() / 1000),
                ":limit": queryOptions.limit || options.limit || 20,
                ":half_life": pick(queryOptions.halfLifeDays, ranking.halfLifeDays, 0),
                ":title_weight": pick(queryOptions.titleWeight, ranking.titleWeight, 10),
                ":tag_weight": pick(queryOptions.tagWeight, ranking.tagWeight, 5),
                ":open_tag": options.openTag || "<mark>",
                ":close_tag": options.closeTag || "</mark>",
                // Escaped, not literal, so this file reads the same whether or
                // not the server declares a character set for it.
                ":ellipsis": options.ellipsis || "\u2026",
                ":snippet_words": queryOptions.snippetWords || options.snippetWords || 12
            };
            return Promise.resolve(worker.db.query(manifest.sql, params))
                .then(function (rows) {
                    return rows.map(function (row) {
                        // Metadata is stored as JSON so that a provider can add
                        // fields without changing the schema.
                        var meta = {};
                        try {
                            meta = JSON.parse(row.meta || "{}");
                        } catch (error) {
                            meta = {};
                        }
                        row.meta = meta;
                        return row;
                    });
                })
                .catch(function (error) {
                    // A half-typed query can still be invalid FTS5. Report no
                    // results rather than breaking the page.
                    if (String(error).indexOf("fts5") !== -1) {
                        return [];
                    }
                    throw error;
                });
        }

        return {
            manifest: manifest,
            query: query,
            /**
             * Bytes actually fetched so far, to show how little is downloaded.
             * The worker answers over a message channel, so this is a promise.
             */
            stats: function () { return Promise.resolve(worker.worker.getStats()); }
        };
    }

    function pick() {
        for (var index = 0; index < arguments.length; index += 1) {
            if (arguments[index] !== undefined && arguments[index] !== null) {
                return arguments[index];
            }
        }
        return undefined;
    }

    global.PysochaSearch = {
        create: create,
        buildMatchQuery: buildMatchQuery
    };
})(typeof self !== "undefined" ? self : this);
