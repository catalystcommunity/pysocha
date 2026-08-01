import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from pysocha.search import (
    SECTION_PAGES,
    SECTION_POSTS,
    SearchError,
    build_search_indexes,
    load_search_instances,
    resolve_provider,
)
from pysocha.search.providers.sqlite_fts import SqliteFtsProvider, search
from pysocha.search.text import html_to_text, split_text_and_code
from pysocha.search.types import SearchProvider, SearchRecord


def make_config(tmp_path, entries):
    return {
        'outputDir': str(tmp_path),
        'contentDir': str(tmp_path / 'content'),
        'siteTitle': 'Test Site',
        'siteAddress': 'https://example.test/',
        'language': 'en',
        'search': entries,
    }


def make_record(url, title, content, days_old=0, **kwargs):
    return SearchRecord(
        url=url,
        title=title,
        content=content,
        date=datetime.now(timezone.utc) - timedelta(days=days_old),
        **kwargs
    )


class TestText:
    def test_strips_tags_and_keeps_words_apart(self):
        html = '<h1>Title</h1><p>First</p><p>Second</p>'
        assert html_to_text(html) == 'Title First Second'

    def test_drops_script_and_style_content(self):
        html = '<p>Real</p><script>var hidden = 1;</script><style>.x{color:red}</style>'
        assert html_to_text(html) == 'Real'

    def test_code_is_separated_from_prose(self):
        html = '<p>Install it</p><pre><code>pip install pysocha</code></pre>'
        prose, code = split_text_and_code(html)
        assert prose == 'Install it'
        assert code == 'pip install pysocha'

    def test_code_is_excluded_by_default_and_included_on_request(self):
        html = '<p>Install it</p><pre><code>pip install pysocha</code></pre>'
        assert 'pip' not in html_to_text(html)
        assert 'pip' in html_to_text(html, include_code=True)

    def test_highlight_markup_does_not_reach_the_index(self):
        # Pygments wraps code in many nested spans with inline styles.
        html = '<p>Note</p><pre class="highlight"><code><span style="color:#f00">def</span> x</code></pre>'
        prose, _ = split_text_and_code(html)
        assert prose == 'Note'
        assert 'color' not in prose

    def test_empty_input(self):
        assert html_to_text('') == ''
        assert split_text_and_code(None) == ('', '')


class TestRecord:
    def test_text_appends_code_only_when_asked(self):
        record = SearchRecord(url='/a', title='A', content='prose', code='code')
        assert record.text() == 'prose'
        assert record.text(include_code=True) == 'prose\ncode'


class TestConfig:
    def test_absent_search_config_yields_nothing(self):
        assert load_search_instances({}) == []
        assert load_search_instances({'search': []}) == []

    def test_single_mapping_is_accepted(self):
        instances = load_search_instances({
            'search': {'name': 'one', 'provider': 'sqlite-fts5'}
        })
        assert len(instances) == 1
        assert instances[0].path == 'search'
        assert instances[0].include == [SECTION_POSTS]

    def test_multiple_instances_keep_their_own_options(self):
        instances = load_search_instances({'search': [
            {'name': 'a', 'provider': 'sqlite-fts5', 'path': 'a', 'options': {'halfLifeDays': 7}},
            {'name': 'b', 'provider': 'sqlite-fts5', 'path': 'b'},
        ]})
        assert [i.name for i in instances] == ['a', 'b']
        assert instances[0].options == {'halfLifeDays': 7}
        assert instances[1].options == {}

    def test_disabled_instance_is_skipped(self):
        instances = load_search_instances({'search': [
            {'name': 'a', 'provider': 'sqlite-fts5', 'enabled': False},
        ]})
        assert instances == []

    def test_duplicate_names_are_rejected(self):
        with pytest.raises(SearchError, match='duplicate search name'):
            load_search_instances({'search': [
                {'name': 'a', 'provider': 'sqlite-fts5', 'path': 'one'},
                {'name': 'a', 'provider': 'sqlite-fts5', 'path': 'two'},
            ]})

    def test_duplicate_paths_are_rejected(self):
        with pytest.raises(SearchError, match='reuses path'):
            load_search_instances({'search': [
                {'name': 'a', 'provider': 'sqlite-fts5', 'path': 'same'},
                {'name': 'b', 'provider': 'sqlite-fts5', 'path': 'same'},
            ]})

    def test_unknown_section_is_rejected(self):
        with pytest.raises(SearchError, match='unknown sections'):
            load_search_instances({'search': [
                {'name': 'a', 'provider': 'sqlite-fts5', 'include': ['posts', 'widgets']},
            ]})

    def test_missing_name_and_provider_are_rejected(self):
        with pytest.raises(SearchError, match="unique 'name'"):
            load_search_instances({'search': [{'provider': 'sqlite-fts5'}]})
        with pytest.raises(SearchError, match="needs a 'provider'"):
            load_search_instances({'search': [{'name': 'a'}]})


class TestRegistry:
    def test_builtin_names_resolve(self):
        assert resolve_provider('sqlite-fts5') is SqliteFtsProvider

    def test_dotted_path_resolves_a_third_party_provider(self):
        provider = resolve_provider(COUNTING_PROVIDER)
        assert provider is CountingProvider

    def test_unknown_name_is_rejected(self):
        with pytest.raises(SearchError, match='unknown search provider'):
            resolve_provider('nope')

    def test_non_provider_class_is_rejected(self):
        with pytest.raises(SearchError, match='must subclass'):
            resolve_provider(__name__ + ':NotAProvider')


#: Dotted path to the provider below, as a site would write it in config.
COUNTING_PROVIDER = __name__ + ':CountingProvider'


class NotAProvider:
    pass


class CountingProvider(SearchProvider):
    """A minimal third-party provider, used to prove the contract is enough."""

    name = 'counting'
    seen = []

    def __init__(self, context):
        super().__init__(context)
        self.records = []

    def add(self, record):
        self.records.append(record)

    def finalize(self):
        from pysocha.search.types import SearchAssets
        path = os.path.join(self.context.instance_dir, 'count.json')
        with open(path, 'w') as handle:
            json.dump({'count': len(self.records),
                       'urls': [r.url for r in self.records]}, handle)
        CountingProvider.seen = [r.url for r in self.records]
        return SearchAssets(data={'count': len(self.records)})


class TestOrchestration:
    def test_sections_route_to_the_right_instance(self, tmp_path):
        CountingProvider.seen = []
        config = make_config(tmp_path, [
            {'name': 'posts-only', 'provider': COUNTING_PROVIDER,
             'path': 'p', 'include': ['posts']},
        ])
        records = [
            make_record('/blog/one.html', 'One', 'alpha', section=SECTION_POSTS),
            make_record('/about.html', 'About', 'beta', section=SECTION_PAGES),
        ]
        results = build_search_indexes(config, records)
        assert results[0]['records'] == 1
        assert CountingProvider.seen == ['/blog/one.html']

    def test_two_instances_build_side_by_side(self, tmp_path):
        config = make_config(tmp_path, [
            {'name': 'all', 'provider': COUNTING_PROVIDER,
             'path': 'all', 'include': ['posts', 'pages']},
            {'name': 'blog', 'provider': 'sqlite-fts5', 'path': 'blog', 'include': ['posts']},
        ])
        records = [
            make_record('/blog/one.html', 'One', 'alpha static search', section=SECTION_POSTS),
            make_record('/about.html', 'About', 'beta', section=SECTION_PAGES),
        ]
        results = build_search_indexes(config, records)
        assert [r['records'] for r in results] == [2, 1]
        assert os.path.exists(tmp_path / 'all' / 'count.json')
        assert os.path.exists(tmp_path / 'blog' / 'search.db')

    def test_provider_writes_only_inside_its_own_directory(self, tmp_path):
        config = make_config(tmp_path, [
            {'name': 'a', 'provider': 'sqlite-fts5', 'path': 'nested/deep'},
        ])
        build_search_indexes(config, [make_record('/blog/x.html', 'X', 'text', section=SECTION_POSTS)])
        assert os.path.exists(tmp_path / 'nested' / 'deep' / 'search.db')


class TestSqliteProvider:
    def build(self, tmp_path, records, options=None):
        # These tests cover the index itself, so the browser assets are left
        # out. The frontend has its own tests below.
        merged = {'frontend': False}
        merged.update(options or {})
        config = make_config(tmp_path, [
            {'name': 'blog', 'provider': 'sqlite-fts5', 'path': 'search',
             'include': ['posts'], 'options': merged},
        ])
        results = build_search_indexes(config, records)
        return str(tmp_path / 'search' / 'search.db'), results[0]['assets']

    def test_urls_stay_root_relative(self, tmp_path):
        db, _ = self.build(tmp_path, [
            make_record('/theblog/a-post.html', 'A post', 'searchable words here',
                        section=SECTION_POSTS),
        ])
        rows = search(db, 'searchable')
        assert rows[0]['url'] == '/theblog/a-post.html'

    def test_title_outweighs_body(self, tmp_path):
        db, _ = self.build(tmp_path, [
            make_record('/blog/titled.html', 'Kubernetes', 'unrelated filler text',
                        section=SECTION_POSTS),
            make_record('/blog/body.html', 'Something else',
                        'a passing mention of kubernetes in the body', section=SECTION_POSTS),
        ])
        rows = search(db, 'kubernetes')
        assert rows[0]['url'] == '/blog/titled.html'

    def test_recency_decay_reorders_equally_relevant_posts(self, tmp_path):
        # The old post is deliberately the stronger match on pure relevance.
        db, _ = self.build(tmp_path, [
            make_record('/blog/old.html', 'Static search',
                        'static search static search', days_old=1200, section=SECTION_POSTS),
            make_record('/blog/new.html', 'Static search',
                        'static search plus a good deal of additional surrounding text '
                        'that dilutes the term frequency somewhat', days_old=2,
                        section=SECTION_POSTS),
        ])
        by_relevance = search(db, 'static', half_life_days=0)
        assert by_relevance[0]['url'] == '/blog/old.html'

        by_recency = search(db, 'static', half_life_days=30)
        assert by_recency[0]['url'] == '/blog/new.html'
        # Relevance still matters, so both posts are returned and ranked.
        assert len(by_recency) == 2

    def test_half_life_of_zero_is_pure_relevance(self, tmp_path):
        db, _ = self.build(tmp_path, [
            make_record('/blog/old.html', 'Static search', 'static search static search',
                        days_old=1200, section=SECTION_POSTS),
            make_record('/blog/new.html', 'Static search', 'static search and more words',
                        days_old=2, section=SECTION_POSTS),
        ])
        rows = search(db, 'static', half_life_days=0)
        assert [r['score'] for r in rows] == [r['relevance'] for r in rows]

    def test_code_is_excluded_unless_requested(self, tmp_path):
        record = SearchRecord(url='/blog/c.html', title='C', content='prose only',
                              code='kubectl apply', section=SECTION_POSTS,
                              date=datetime.now(timezone.utc))
        db, _ = self.build(tmp_path, [record])
        assert search(db, 'kubectl') == []

        db2, _ = self.build(tmp_path / 'with-code', [record], options={'indexCode': True})
        assert len(search(db2, 'kubectl')) == 1

    def test_filters_are_searchable_as_tags(self, tmp_path):
        db, _ = self.build(tmp_path, [
            SearchRecord(url='/blog/t.html', title='T', content='body text',
                         section=SECTION_POSTS, date=datetime.now(timezone.utc),
                         filters={'tags': ['observability']}),
        ])
        assert len(search(db, 'observability')) == 1

    def test_manifest_records_the_shipped_query_and_ranking(self, tmp_path):
        _, assets = self.build(tmp_path, [
            make_record('/blog/a.html', 'A', 'text', section=SECTION_POSTS),
        ], options={'halfLifeDays': 14})
        manifest_path = tmp_path / 'search' / 'search-manifest.json'
        manifest = json.loads(manifest_path.read_text())
        assert manifest['ranking']['halfLifeDays'] == 14
        assert 'bm25' in manifest['sql']
        assert manifest['database'] == '/search/search.db'
        assert assets.data['databaseBytes'] > 0

    def test_page_size_is_applied_for_range_requests(self, tmp_path):
        import sqlite3
        db, _ = self.build(tmp_path, [
            make_record('/blog/a.html', 'A', 'text', section=SECTION_POSTS),
        ], options={'pageSize': 1024})
        connection = sqlite3.connect(db)
        try:
            assert connection.execute('PRAGMA page_size').fetchone()[0] == 1024
        finally:
            connection.close()

    def test_rebuild_replaces_the_previous_database(self, tmp_path):
        self.build(tmp_path, [make_record('/blog/a.html', 'A', 'alpha', section=SECTION_POSTS)])
        db, _ = self.build(tmp_path, [make_record('/blog/b.html', 'B', 'beta', section=SECTION_POSTS)])
        assert search(db, 'alpha') == []
        assert len(search(db, 'beta')) == 1


pagefind = pytest.importorskip('pagefind.index', reason='pagefind is an optional dependency')


class TestPagefindProvider:
    def build(self, tmp_path, records, options=None):
        config = make_config(tmp_path, [
            {'name': 'site', 'provider': 'pagefind', 'path': 'search',
             'include': ['posts', 'pages'], 'options': options or {}},
        ])
        results = build_search_indexes(config, records)
        return tmp_path / 'search' / 'pagefind', results[0]['assets']

    def fragments(self, bundle_dir):
        import gzip
        found = []
        for name in sorted(os.listdir(str(bundle_dir / 'fragment'))):
            raw = gzip.decompress((bundle_dir / 'fragment' / name).read_bytes())
            # Fragments carry a short format tag before the JSON payload.
            found.append(json.loads(raw[raw.index(b'{'):]))
        return found

    def test_bundle_is_written_without_any_template_markup(self, tmp_path):
        bundle_dir, assets = self.build(tmp_path, [
            make_record('/theblog/a-post.html', 'A post', 'searchable words',
                        section=SECTION_POSTS),
        ])
        assert (bundle_dir / 'pagefind.js').exists()
        assert assets.data['module'] == '/search/pagefind/pagefind.js'
        assert assets.data['recordCount'] == 1

    def test_base_url_defaults_to_the_site_root(self, tmp_path):
        # The bundle sits under the search path, so Pagefind would otherwise
        # treat /search/ as the site root and prefix every result URL with it.
        _, assets = self.build(tmp_path, [
            make_record('/theblog/a-post.html', 'A post', 'alpha', section=SECTION_POSTS),
        ])
        assert assets.data['baseUrl'] == '/'

    def test_base_url_is_configurable_for_a_subpath_site(self, tmp_path):
        _, assets = self.build(tmp_path, [
            make_record('/theblog/a-post.html', 'A post', 'alpha', section=SECTION_POSTS),
        ], options={'baseUrl': '/docs/'})
        assert assets.data['baseUrl'] == '/docs/'

    def test_urls_are_passed_through_unaltered(self, tmp_path):
        bundle_dir, _ = self.build(tmp_path, [
            make_record('/theblog/a-post.html', 'A post', 'alpha', section=SECTION_POSTS),
            make_record('/about.html', 'About', 'beta', section=SECTION_PAGES),
        ])
        urls = sorted(f['url'] for f in self.fragments(bundle_dir))
        assert urls == ['/about.html', '/theblog/a-post.html']

    def test_meta_and_filters_reach_the_index(self, tmp_path):
        bundle_dir, _ = self.build(tmp_path, [
            SearchRecord(url='/theblog/p.html', title='Titled', content='body',
                         section=SECTION_POSTS, date=datetime.now(timezone.utc),
                         meta={'author': 'Tod'}, filters={'tags': ['testing']}),
        ])
        fragment = self.fragments(bundle_dir)[0]
        assert fragment['meta']['title'] == 'Titled'
        assert fragment['meta']['author'] == 'Tod'
        assert fragment['filters']['tags'] == ['testing']

    def test_indexed_content_holds_no_page_chrome(self, tmp_path):
        bundle_dir, _ = self.build(tmp_path, [
            make_record('/theblog/p.html', 'P', 'only the body text', section=SECTION_POSTS),
        ])
        assert self.fragments(bundle_dir)[0]['content'] == 'only the body text'

    def test_nothing_is_written_outside_the_output_directory(self, tmp_path, monkeypatch):
        # Pagefind writes its bundle when the index context closes. If the output
        # path is not configured it drops a second copy in the working directory.
        workdir = tmp_path / 'cwd'
        workdir.mkdir()
        monkeypatch.chdir(str(workdir))
        site = tmp_path / 'site'
        self.build(site, [
            make_record('/theblog/a-post.html', 'A post', 'alpha', section=SECTION_POSTS),
        ])
        assert os.listdir(str(workdir)) == []

    def test_dates_become_a_sortable_key(self, tmp_path):
        from pysocha.search.providers.pagefind import _sort_value
        record = make_record('/blog/a.html', 'A', 'text', days_old=0, section=SECTION_POSTS)
        assert len(_sort_value(record)['date']) == 14


class TestSqliteFrontend:
    """The browser side of the sqlite-fts5 provider.

    These tests never reach the network. The assets are either already in place
    or the download is refused.
    """

    ASSET_NAMES = ['index.js', 'sqlite.worker.js', 'sql-wasm.wasm']

    def place_assets(self, tmp_path, subdir='vendor/sql.js-httpvfs'):
        target = tmp_path / 'content' / 'extra_files' / subdir
        target.mkdir(parents=True)
        for name in self.ASSET_NAMES:
            (target / name).write_text('vendored ' + name)
        return target

    def build(self, tmp_path, options=None):
        config = make_config(tmp_path, [
            {'name': 'blog', 'provider': 'sqlite-fts5', 'path': 'news',
             'include': ['posts'], 'options': options or {}},
        ])
        records = [make_record('/blog/a.html', 'A', 'alpha text', section=SECTION_POSTS)]
        return build_search_indexes(config, records)[0]['assets']

    def test_scripts_are_listed_with_the_bundle_first(self, tmp_path):
        self.place_assets(tmp_path)
        assets = self.build(tmp_path)
        # createDbWorker has to exist before the pysocha code runs.
        assert assets.scripts == [
            '/vendor/sql.js-httpvfs/index.js',
            '/news/sqlite-search.js',
        ]

    def test_worker_and_wasm_urls_are_root_relative(self, tmp_path):
        self.place_assets(tmp_path)
        assets = self.build(tmp_path)
        assert assets.data['worker'] == '/vendor/sql.js-httpvfs/sqlite.worker.js'
        assert assets.data['wasm'] == '/vendor/sql.js-httpvfs/sql-wasm.wasm'

    def test_browser_code_is_written_next_to_the_index(self, tmp_path):
        self.place_assets(tmp_path)
        self.build(tmp_path)
        script = tmp_path / 'news' / 'sqlite-search.js'
        assert script.is_file()
        assert 'PysochaSearch' in script.read_text()

    def test_vendored_assets_are_copied_into_the_output(self, tmp_path):
        self.place_assets(tmp_path)
        self.build(tmp_path)
        for name in self.ASSET_NAMES:
            assert (tmp_path / 'vendor' / 'sql.js-httpvfs' / name).is_file()

    def test_an_existing_copy_is_never_overwritten(self, tmp_path):
        # A site that vendored its own build keeps exactly what it committed.
        self.place_assets(tmp_path)
        self.build(tmp_path)
        assert (tmp_path / 'vendor' / 'sql.js-httpvfs' / 'index.js').read_text() == (
            'vendored index.js'
        )

    def test_the_assets_directory_is_configurable(self, tmp_path):
        self.place_assets(tmp_path, subdir='lib/sqlite')
        assets = self.build(tmp_path, options={'assetsDir': 'lib/sqlite'})
        assert assets.scripts[0] == '/lib/sqlite/index.js'
        assert (tmp_path / 'lib' / 'sqlite' / 'sql-wasm.wasm').is_file()

    def test_a_refused_download_explains_what_to_do(self, tmp_path):
        from pysocha.search.vendor import VendorError
        with pytest.raises(VendorError, match='add these files yourself'):
            self.build(tmp_path, options={'download': False})

    def test_frontend_can_be_turned_off_entirely(self, tmp_path):
        assets = self.build(tmp_path, options={'frontend': False})
        assert assets.scripts == []
        assert 'worker' not in assets.data
        assert not (tmp_path / 'vendor').exists()

    def test_the_manifest_is_still_written_without_the_frontend(self, tmp_path):
        assets = self.build(tmp_path, options={'frontend': False})
        assert (tmp_path / 'news' / 'search-manifest.json').is_file()
        assert assets.data['database'] == '/news/search.db'


class TestFrontendAsset:
    """The browser code pysocha ships for the sqlite-fts5 provider."""

    def source(self):
        import pysocha.search
        path = os.path.join(os.path.dirname(pysocha.search.__file__),
                            'assets', 'sqlite-search.js')
        with open(path, 'rb') as handle:
            return handle.read()

    def test_the_file_is_pure_ascii(self):
        # A non-ASCII literal is decoded with whatever character set the server
        # declares for the file. Without one it turns into mojibake, so every
        # such character has to be written as an escape.
        self.source().decode('ascii')

    def test_it_exposes_the_documented_api(self):
        text = self.source().decode('ascii')
        assert 'global.PysochaSearch' in text
        assert 'create: create' in text
        assert 'buildMatchQuery' in text

    def test_it_uses_the_ranking_query_from_the_manifest(self):
        # The page must not carry its own copy of the ranking query, or what is
        # tested from Python stops being what the page runs.
        text = self.source().decode('ascii')
        assert 'manifest.sql' in text
        assert 'bm25' not in text


class TestPortability:
    """Behaviour that has to hold on Windows and macOS as well as Linux.

    URLs use forward slashes everywhere. File paths use the separator of the
    platform. Anything that builds a URL out of a file path breaks on Windows,
    so these tests keep the two apart.
    """

    ASSET_NAMES = ['index.js', 'sqlite.worker.js', 'sql-wasm.wasm']

    def place_assets(self, tmp_path, subdir='vendor/sql.js-httpvfs'):
        target = tmp_path / 'content' / 'extra_files' / subdir
        target.mkdir(parents=True)
        for name in self.ASSET_NAMES:
            (target / name).write_bytes(b'vendored')
        return target

    def test_no_url_contains_a_backslash(self, tmp_path):
        self.place_assets(tmp_path)
        config = make_config(tmp_path, [
            {'name': 'blog', 'provider': 'sqlite-fts5', 'path': 'news',
             'include': ['posts']},
        ])
        assets = build_search_indexes(config, [
            make_record('/blog/a.html', 'A', 'alpha', section=SECTION_POSTS),
        ])[0]['assets']

        urls = list(assets.scripts) + list(assets.styles) + [
            value for value in assets.data.values() if isinstance(value, str)
        ]
        for url in urls:
            assert '\\' not in url, url

    def test_a_nested_search_path_still_yields_a_posix_url(self, tmp_path):
        config = make_config(tmp_path, [
            {'name': 'deep', 'provider': 'sqlite-fts5', 'path': 'site/search',
             'include': ['posts'], 'options': {'frontend': False}},
        ])
        assets = build_search_indexes(config, [
            make_record('/blog/a.html', 'A', 'alpha', section=SECTION_POSTS),
        ])[0]['assets']
        assert assets.data['database'] == '/site/search/search.db'
        # The directory itself is made with the platform's own separator.
        assert (tmp_path / 'site' / 'search' / 'search.db').is_file()

    def test_the_browser_code_is_copied_byte_for_byte(self, tmp_path):
        # Copying in text mode would rewrite newlines on Windows, which changes
        # the file the browser gets for no reason.
        import pysocha.search
        self.place_assets(tmp_path)
        config = make_config(tmp_path, [
            {'name': 'blog', 'provider': 'sqlite-fts5', 'path': 'news',
             'include': ['posts']},
        ])
        build_search_indexes(config, [
            make_record('/blog/a.html', 'A', 'alpha', section=SECTION_POSTS),
        ])
        source = os.path.join(os.path.dirname(pysocha.search.__file__),
                              'assets', 'sqlite-search.js')
        with open(source, 'rb') as handle:
            expected = handle.read()
        assert (tmp_path / 'news' / 'sqlite-search.js').read_bytes() == expected

    def test_archive_member_names_use_the_tar_separator(self):
        # Tar always uses forward slashes, whatever platform reads the archive.
        from pysocha.search.vendor import SQL_JS_HTTPVFS
        for member in SQL_JS_HTTPVFS.wanted_files():
            assert '\\' not in member
        for name in SQL_JS_HTTPVFS.wanted_files().values():
            assert '/' not in name and '\\' not in name

    def test_record_urls_are_posix_regardless_of_platform(self, tmp_path):
        record = make_record('/theblog/a-post.html', 'A', 'text', section=SECTION_POSTS)
        assert record.url.startswith('/')
        assert '\\' not in record.url


class TestFts5Requirement:
    def test_a_sqlite_without_fts5_explains_itself(self, tmp_path, monkeypatch):
        import sqlite3
        from pysocha.search.providers import sqlite_fts

        real_connect = sqlite3.connect

        class NoFts5(object):
            """Stands in for a SQLite build that has no FTS5 module."""

            def __init__(self, inner):
                self._inner = inner

            def executescript(self, script):
                raise sqlite3.OperationalError('no such module: fts5')

            def __getattr__(self, name):
                return getattr(self._inner, name)

        monkeypatch.setattr(
            sqlite_fts.sqlite3, 'connect',
            lambda *a, **k: NoFts5(real_connect(*a, **k)),
        )
        config = make_config(tmp_path, [
            {'name': 'blog', 'provider': 'sqlite-fts5', 'path': 'news',
             'include': ['posts'], 'options': {'frontend': False}},
        ])
        with pytest.raises(RuntimeError, match='without FTS5'):
            build_search_indexes(config, [
                make_record('/blog/a.html', 'A', 'alpha', section=SECTION_POSTS),
            ])

    def test_an_unrelated_sqlite_error_is_not_swallowed(self, tmp_path, monkeypatch):
        import sqlite3
        from pysocha.search.providers import sqlite_fts

        real_connect = sqlite3.connect

        class Broken(object):
            def __init__(self, inner):
                self._inner = inner

            def executescript(self, script):
                raise sqlite3.OperationalError('disk I/O error')

            def __getattr__(self, name):
                return getattr(self._inner, name)

        monkeypatch.setattr(
            sqlite_fts.sqlite3, 'connect',
            lambda *a, **k: Broken(real_connect(*a, **k)),
        )
        config = make_config(tmp_path, [
            {'name': 'blog', 'provider': 'sqlite-fts5', 'path': 'news',
             'include': ['posts'], 'options': {'frontend': False}},
        ])
        with pytest.raises(sqlite3.OperationalError, match='disk I/O error'):
            build_search_indexes(config, [
                make_record('/blog/a.html', 'A', 'alpha', section=SECTION_POSTS),
            ])
