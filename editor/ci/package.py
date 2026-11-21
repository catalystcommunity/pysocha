"""Package the editor with an isolated Python runtime for the same target."""
import argparse
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

TARGETS = {
    "linux-x86_64": ("x86_64-unknown-linux-gnu", "linux-x86_64-gnu"),
    "linux-arm64": ("aarch64-unknown-linux-gnu", "linux-aarch64-gnu"),
    "macos-arm64": ("aarch64-apple-darwin", "macos-aarch64-none"),
    "windows-x86_64": ("x86_64-pc-windows-msvc", "windows-x86_64-none"),
}


def run(*args):
    subprocess.run(args, check=True)


def package(target, binary, output, version):
    platform, python_platform = TARGETS[target]
    windows = target.startswith("windows")
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        tree = work / "archive"
        app = tree / "Pysocha Editor.app/Contents" if target == "macos-arm64" else None
        folder = app / "MacOS" if app else tree / "pysocha-editor"
        folder.mkdir(parents=True)
        shutil.copy2(binary, folder / ("pysocha-editor.exe" if windows else "pysocha-editor"))
        if app:
            (app / "Info.plist").write_bytes(plistlib.dumps(dict(
                CFBundleName="Pysocha Editor", CFBundlePackageType="APPL",
                CFBundleIdentifier="com.catalystsquad.pysocha.editor",
                CFBundleExecutable="pysocha-editor", CFBundleVersion=version,
                CFBundleShortVersionString=version, NSHighResolutionCapable=True,
            )))
        runtime = folder / "runtime"
        distribution = "cpython-3.12.12-" + python_platform
        run("uv", "python", "install", "--no-bin", "--install-dir", work / "python", distribution)
        (work / "python" / distribution).rename(runtime)
        # uv creates an absolute convenience symlink for the host.
        for link in runtime.rglob("*"):
            if link.is_symlink() and link.readlink().is_absolute():
                old = link.readlink().relative_to(work / "python" / distribution)
                link.unlink()
                if (runtime / old).exists():
                    link.symlink_to(os.path.relpath(runtime / old, link.parent))
        packages = runtime / ("Lib/site-packages" if windows else "lib/python3.12/site-packages")
        requirements = work / "requirements.txt"
        run("uv", "export", "--locked", "--no-dev", "--extra", "search-pagefind",
            "--no-emit-project", "--output-file", requirements, "--quiet")
        install = ["uv", "pip", "install", "--target", packages, "--only-binary", ":all:",
                   "--python-version", "3.12.12", "--python-platform", platform]
        run(*install, "--require-hashes", "-r", requirements)
        project = work / "package"
        project.mkdir()
        shutil.copytree("src/pysocha", project / "src/pysocha", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2("README.md", project)
        manifest = Path("pyproject.toml").read_text()
        if version != "0.0.0":
            manifest = re.sub(r'^version = "[^"]+"$', 'version = "{}"'.format(version),
                              manifest, count=1, flags=re.MULTILINE)
        (project / "pyproject.toml").write_text(manifest)
        run("uv", "build", "--wheel", "--out-dir", work / "wheel", project)
        wheel, = (work / "wheel").glob("*.whl")
        run(*install, "--no-deps", wheel)
        output.mkdir(exist_ok=True, parents=True)
        name = output / ("pysocha-editor-{}-{}".format(version, target))
        archive = shutil.make_archive(str(name), "zip" if windows else "gztar", tree)
        print(archive)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("binary", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("version")
    args = parser.parse_args()
    package(args.target, args.binary, args.output, args.version)
