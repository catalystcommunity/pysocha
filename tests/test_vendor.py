import io
import os
import tarfile

import pytest

from pysocha.search.vendor import (
    SQL_JS_HTTPVFS,
    VendorError,
    VendorPackage,
    ensure_assets,
    missing_files,
)


def make_package(version='1.0.0', integrity=None):
    return VendorPackage(
        name='fake-package',
        version=version,
        files={'package/dist/one.js': 'one.js', 'package/dist/two.wasm': 'two.wasm'},
        integrity=integrity or {},
        license_path='package/LICENSE',
        homepage='https://example.test/fake',
    )


def make_tarball(members):
    """Build a package archive the way the npm registry serves one."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for name, content in members.items():
            data = content.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


DEFAULT_MEMBERS = {
    'package/dist/one.js': 'console.log(1);',
    'package/dist/two.wasm': 'not really wasm',
    'package/LICENSE': 'Apache-2.0',
}


def publish(tmp_path, package, version, archive):
    """Lay out a local registry that urllib can read over file://."""
    registry = tmp_path / 'registry'
    path = registry / package.name / '-'
    path.mkdir(parents=True, exist_ok=True)
    short = package.name.split('/')[-1]
    (path / '{}-{}.tgz'.format(short, version)).write_bytes(archive)
    return registry.as_uri()


class TestMissingFiles:
    def test_reports_every_absent_file(self, tmp_path):
        assert missing_files(make_package(), str(tmp_path)) == ['one.js', 'two.wasm']

    def test_reports_nothing_when_all_present(self, tmp_path):
        (tmp_path / 'one.js').write_text('x')
        (tmp_path / 'two.wasm').write_text('x')
        assert missing_files(make_package(), str(tmp_path)) == []


class TestEnsureAssets:
    def test_existing_files_are_left_alone_and_nothing_is_fetched(self, tmp_path):
        target = tmp_path / 'vendor'
        target.mkdir()
        (target / 'one.js').write_text('mine')
        (target / 'two.wasm').write_text('mine')

        downloaded = ensure_assets(
            make_package(), str(target), registry='file:///nowhere-at-all',
        )
        assert downloaded is False
        # A site that vendored its own copy keeps it.
        assert (target / 'one.js').read_text() == 'mine'

    def test_missing_files_are_downloaded_and_written(self, tmp_path):
        package = make_package()
        registry = publish(tmp_path, package, '1.0.0', make_tarball(DEFAULT_MEMBERS))
        target = tmp_path / 'extra_files' / 'vendor'

        downloaded = ensure_assets(package, str(target), registry=registry)

        assert downloaded is True
        assert (target / 'one.js').read_text() == 'console.log(1);'
        assert (target / 'two.wasm').read_text() == 'not really wasm'
        # The licence travels with the files it covers.
        assert (target / 'LICENSE').read_text() == 'Apache-2.0'

    def test_a_second_build_needs_no_network(self, tmp_path):
        package = make_package()
        registry = publish(tmp_path, package, '1.0.0', make_tarball(DEFAULT_MEMBERS))
        target = tmp_path / 'vendor'

        assert ensure_assets(package, str(target), registry=registry) is True
        # Point at a registry that does not exist. If it tried to fetch again
        # this would raise.
        assert ensure_assets(package, str(target), registry='file:///nowhere') is False

    def test_the_message_says_what_happened_and_where(self, tmp_path, capsys):
        package = make_package()
        registry = publish(tmp_path, package, '1.0.0', make_tarball(DEFAULT_MEMBERS))
        target = tmp_path / 'extra_files' / 'vendor'
        messages = []

        ensure_assets(package, str(target), registry=registry, log=messages.append)

        joined = '\n'.join(messages)
        assert 'fake-package' in joined
        assert 'extra_files' in joined
        assert 'Commit them' in joined
        assert package.homepage in joined

    def test_download_can_be_refused(self, tmp_path):
        with pytest.raises(VendorError, match='add these files yourself'):
            ensure_assets(make_package(), str(tmp_path / 'vendor'), allow_download=False)

    def test_a_bad_hash_writes_nothing(self, tmp_path):
        package = make_package(integrity={'1.0.0': 'sha512-not-the-real-hash'})
        registry = publish(tmp_path, package, '1.0.0', make_tarball(DEFAULT_MEMBERS))
        target = tmp_path / 'vendor'

        with pytest.raises(VendorError, match='failed its integrity check'):
            ensure_assets(package, str(target), registry=registry)
        assert not (target / 'one.js').exists()

    def test_a_matching_hash_is_accepted(self, tmp_path):
        from pysocha.search.vendor import _integrity_of
        archive = make_tarball(DEFAULT_MEMBERS)
        package = make_package(integrity={'1.0.0': _integrity_of(archive)})
        registry = publish(tmp_path, package, '1.0.0', archive)

        assert ensure_assets(package, str(tmp_path / 'vendor'), registry=registry) is True

    def test_an_unpinned_version_is_fetched_but_reported(self, tmp_path):
        package = make_package(integrity={'1.0.0': 'sha512-whatever'})
        registry = publish(tmp_path, package, '2.0.0', make_tarball(DEFAULT_MEMBERS))
        target = tmp_path / 'vendor'
        messages = []

        ensure_assets(package, str(target), version='2.0.0',
                      registry=registry, log=messages.append)

        assert (target / 'one.js').exists()
        assert 'not a version pysocha pins' in '\n'.join(messages)

    def test_an_incomplete_archive_is_rejected(self, tmp_path):
        package = make_package()
        archive = make_tarball({'package/dist/one.js': 'only one file'})
        registry = publish(tmp_path, package, '1.0.0', archive)

        with pytest.raises(VendorError, match='does not contain'):
            ensure_assets(package, str(tmp_path / 'vendor'), registry=registry)

    def test_a_missing_version_reports_the_url(self, tmp_path):
        package = make_package()
        publish(tmp_path, package, '1.0.0', make_tarball(DEFAULT_MEMBERS))
        registry = (tmp_path / 'registry').as_uri()

        with pytest.raises(VendorError, match='could not download'):
            ensure_assets(package, str(tmp_path / 'vendor'),
                          version='9.9.9', registry=registry)


class TestPinnedPackage:
    def test_the_sqlite_build_names_the_files_the_browser_needs(self):
        assert sorted(SQL_JS_HTTPVFS.files.values()) == [
            'index.js', 'sql-wasm.wasm', 'sqlite.worker.js',
        ]

    def test_the_default_version_is_pinned_to_a_known_hash(self):
        assert SQL_JS_HTTPVFS.version in SQL_JS_HTTPVFS.integrity
        assert SQL_JS_HTTPVFS.integrity[SQL_JS_HTTPVFS.version].startswith('sha512-')

    def test_the_tarball_url_matches_the_registry_layout(self):
        assert SQL_JS_HTTPVFS.tarball_url('0.8.12') == (
            'https://registry.npmjs.org/sql.js-httpvfs/-/sql.js-httpvfs-0.8.12.tgz'
        )
