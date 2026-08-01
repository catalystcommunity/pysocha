"""Fetch the browser assets that a search provider needs.

Some providers need a library in the browser that pysocha cannot generate, such
as a WebAssembly build of SQLite. Pysocha does not ship those files, because
they are large and they belong to another project.

Instead, a provider asks for the files it needs. If they are already in the
site's ``extra_files`` directory, they are used as they are. If they are
missing, they are downloaded once, checked against a pinned hash, and written
into ``extra_files``. From then on they are part of the site's own source, so
later builds need no network, and the site owner can commit them.
"""

import base64
import hashlib
import io
import os
import tarfile
import urllib.request
from typing import Callable, Dict, Optional


DEFAULT_REGISTRY = "https://registry.npmjs.org"

#: Seconds to wait for the download.
DOWNLOAD_TIMEOUT = 120


class VendorError(RuntimeError):
    pass


class VendorPackage(object):
    """A package of browser assets, taken from the npm registry.

    The npm registry is used because it serves every published version at a
    stable URL, with a hash that can be checked.
    """

    def __init__(self, name, version, files, integrity, license_path=None, homepage=""):
        #: Package name in the registry.
        self.name = name
        #: Version used when the site does not pin one.
        self.version = version
        #: Map of path inside the archive to the file name written on disk.
        self.files = files
        #: Known archive hashes, by version.
        self.integrity = integrity
        #: Path of the licence inside the archive, copied along with the files.
        self.license_path = license_path
        #: Where a reader can find out more about the package.
        self.homepage = homepage

    def tarball_url(self, version: str, registry: str = DEFAULT_REGISTRY) -> str:
        # Scoped names such as @scope/name keep only the last part in the path.
        short_name = self.name.split("/")[-1]
        return "{}/{}/-/{}-{}.tgz".format(
            registry.rstrip("/"), self.name, short_name, version
        )

    def wanted_files(self) -> Dict[str, str]:
        wanted = dict(self.files)
        if self.license_path:
            wanted[self.license_path] = os.path.basename(self.license_path)
        return wanted


#: The SQLite build used by the sqlite-fts5 provider. It reads a database over
#: HTTP range requests, which is what makes a large index usable in a browser.
SQL_JS_HTTPVFS = VendorPackage(
    name="sql.js-httpvfs",
    version="0.8.12",
    files={
        "package/dist/index.js": "index.js",
        "package/dist/sqlite.worker.js": "sqlite.worker.js",
        "package/dist/sql-wasm.wasm": "sql-wasm.wasm",
    },
    integrity={
        "0.8.12": "sha512-lcEBc2q0psFRfdCx8Di22oUIkkv5MUIaVO/fGCj/Jjx6YQDKVylQEcjd7NSSbmINHTRwVkm/vWP8uuevT7Rkkw==",
    },
    license_path="package/LICENSE",
    homepage="https://github.com/phiresky/sql.js-httpvfs",
)


def _integrity_of(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")


def missing_files(package: VendorPackage, target_dir: str):
    """Names of the package files that are not in ``target_dir`` yet."""
    return sorted(
        name for name in package.files.values()
        if not os.path.isfile(os.path.join(target_dir, name))
    )


def _download(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:
            return response.read()
    except Exception as error:
        raise VendorError("could not download {}: {}".format(url, error))


def _extract(package: VendorPackage, archive: bytes, target_dir: str) -> None:
    wanted = package.wanted_files()
    written = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member_path, output_name in wanted.items():
            try:
                member = tar.getmember(member_path)
            except KeyError:
                raise VendorError(
                    "{} {} does not contain {}".format(
                        package.name, package.version, member_path
                    )
                )
            if not member.isfile():
                raise VendorError("{} is not a file".format(member_path))
            source = tar.extractfile(member)
            if source is None:
                raise VendorError("could not read {}".format(member_path))
            # Each member is written by name, so a path inside the archive can
            # never decide where the file lands.
            with open(os.path.join(target_dir, output_name), "wb") as handle:
                handle.write(source.read())
            written.add(output_name)
    if written != set(wanted.values()):
        raise VendorError("{} did not provide every needed file".format(package.name))


def ensure_assets(
    package: VendorPackage,
    target_dir: str,
    version: Optional[str] = None,
    allow_download: bool = True,
    registry: str = DEFAULT_REGISTRY,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """Make sure every file of ``package`` is in ``target_dir``.

    Returns True if files were downloaded, and False if they were already there.
    """
    version = version or package.version
    log = log or (lambda message: None)

    missing = missing_files(package, target_dir)
    if not missing:
        return False

    if not allow_download:
        raise VendorError(
            "{} is missing from {}: {}. Either add these files yourself, or "
            "allow pysocha to fetch them by removing 'download: false' from the "
            "search options.".format(package.name, target_dir, ", ".join(missing))
        )

    url = package.tarball_url(version, registry)
    log(
        "search: {} {} is not in {}.\n"
        "search: fetching it once from {}\n"
        "search: the files are written into your extra_files directory, so this "
        "build is the only one that needs the network. Commit them to vendor "
        "them yourself. See {}".format(
            package.name, version, target_dir, url, package.homepage
        )
    )

    archive = _download(url)
    expected = package.integrity.get(version)
    if expected is None:
        log(
            "search: {} {} is not a version pysocha pins, so its download is "
            "not checked against a known hash. The hash of what was fetched is "
            "{}".format(package.name, version, _integrity_of(archive))
        )
    elif _integrity_of(archive) != expected:
        raise VendorError(
            "{} {} failed its integrity check. Expected {}, got {}. Nothing was "
            "written.".format(package.name, version, expected, _integrity_of(archive))
        )

    os.makedirs(target_dir, exist_ok=True)
    _extract(package, archive, target_dir)
    log("search: wrote {} into {}".format(", ".join(sorted(package.files.values())), target_dir))
    return True
