import os

from pysocha.preview import makePreviewServer


def make_site(tmp_path):
    (tmp_path / 'index.html').write_text('<p>home</p>')
    search_dir = tmp_path / 'search'
    search_dir.mkdir()
    (search_dir / 'index.html').write_text('<p>search</p>')
    blog_dir = tmp_path / 'theblog'
    blog_dir.mkdir()
    (blog_dir / 'listing1.html').write_text('<p>listing</p>')
    return makePreviewServer(os.path.abspath(str(tmp_path)), 'index.html', '.html').test_client()


class TestPreviewServer:
    def test_serves_the_start_page(self, tmp_path):
        assert make_site(tmp_path).get('/').status_code == 200

    def test_serves_a_named_file(self, tmp_path):
        assert make_site(tmp_path).get('/theblog/listing1.html').status_code == 200

    def test_serves_a_directory_index(self, tmp_path):
        # A search page lives at a path such as /search/, so the preview has to
        # resolve the directory to its index file the way a web server does.
        response = make_site(tmp_path).get('/search/')
        assert response.status_code == 200
        assert b'search' in response.data

    def test_missing_directory_is_still_not_found(self, tmp_path):
        assert make_site(tmp_path).get('/nope/').status_code == 404

    def test_missing_file_is_still_not_found(self, tmp_path):
        assert make_site(tmp_path).get('/missing.html').status_code == 404


class TestContentTypes:
    """The browser refuses to run a module that arrives as the wrong type.

    On Windows the mimetypes module takes .js from the registry, which has long
    said text/plain. These tests simulate that and check the preview corrects it.
    """

    def make_files(self, tmp_path):
        (tmp_path / 'index.html').write_text('<p>home</p>')
        (tmp_path / 'app.js').write_text('export const x = 1;')
        (tmp_path / 'sql-wasm.wasm').write_bytes(b'\x00asm')
        (tmp_path / 'data.json').write_text('{}')
        return tmp_path

    def test_javascript_is_served_as_javascript(self, tmp_path, monkeypatch):
        import mimetypes
        from pysocha.preview import makePreviewServer

        # Stand in for the Windows registry mapping.
        mimetypes.add_type('text/plain', '.js')
        client = makePreviewServer(
            os.path.abspath(str(self.make_files(tmp_path))), 'index.html', '.html'
        ).test_client()

        content_type = client.get('/app.js').headers.get('Content-Type', '')
        assert 'javascript' in content_type
        assert 'text/plain' not in content_type

    def test_wasm_and_json_keep_their_own_types(self, tmp_path):
        from pysocha.preview import makePreviewServer

        client = makePreviewServer(
            os.path.abspath(str(self.make_files(tmp_path))), 'index.html', '.html'
        ).test_client()

        assert 'application/wasm' in client.get('/sql-wasm.wasm').headers.get('Content-Type', '')
        assert 'application/json' in client.get('/data.json').headers.get('Content-Type', '')

    def test_range_requests_are_supported_for_the_search_database(self, tmp_path):
        from pysocha.preview import makePreviewServer

        self.make_files(tmp_path)
        (tmp_path / 'search.db').write_bytes(b'x' * 8192)
        client = makePreviewServer(
            os.path.abspath(str(tmp_path)), 'index.html', '.html'
        ).test_client()

        response = client.get('/search.db', headers={'Range': 'bytes=0-1023'})
        assert response.status_code == 206
        assert response.headers.get('Content-Length') == '1024'
