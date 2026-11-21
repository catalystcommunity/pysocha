# Pysocha Editor

Download the archive for your computer from the GitHub release. Extract the full archive. Keep the runtime folder with the application. The archive includes Python and the Pysocha search providers.

| Computer | Archive name contains | Start the editor |
| --- | --- | --- |
| Mac with Apple silicon | `macos-arm64` | Open Pysocha Editor.app. |
| 64-bit Intel or AMD Windows | `windows-x86_64` | Run pysocha-editor.exe. |
| 64-bit Intel or AMD Linux | `linux-x86_64` | Run pysocha-editor. |
| ARM64 Linux | `linux-arm64` | Run pysocha-editor. |

The Linux build uses Debian 13 libraries, WebKitGTK 4.1, and an X11 display. A Wayland session can use XWayland. The Windows preview uses the WebView2 Runtime.

## Edit a site

1. Select **Open site**. Select the YAML configuration file for the site.
2. Select **Open file**. Select a Markdown page, a post, a template, a style sheet, or another text file in the site. Select **New file** to add a file.
3. Edit the text. A dot beside the file name shows unsaved changes. Use the file tabs to move between open files. Use Ctrl+F to search the active file. On macOS, use Command+F.
4. Select **Side by side** or **Stacked** to see the source and preview together. Select the preview tab to use the full window. Follow a link in the preview to open another page.
5. Select **Save** to write the active file. You can also use Ctrl+S or Command+S.

The preview uses unsaved changes from all open files. It builds a private copy of the site. A build error leaves the last successful preview on the screen. Read the message above the preview. Hold the pointer over the message to pause its timer.

Select **Site theme** to try a different template folder in the site. Select **Use site default** to use the configuration again. Select **Dark appearance** or **Light appearance** to change the editor and the browser color scheme. The site controls how its pages respond to the color scheme.

## Run from source

Install the Linux development packages in `editor/ci/linux.Dockerfile` if you build on Linux. From the repository root, run these commands in a POSIX shell.

```sh
uv sync --locked --all-extras
PYSOCHA_PYTHON="$PWD/.venv/bin/python" cargo run --locked --manifest-path editor/Cargo.toml -- example/example-config.yaml
```

## Release process

A pull request to main starts the Python tests and the editor timer tests. The Python check builds a source distribution and a wheel. It installs the wheel in a clean environment.

A merge to main tags the merge commit. The first tag uses the package version in pyproject.toml. Later merges increase the patch number. Increase the version in pyproject.toml to select a higher release number.

A version tag starts two jobs. One job publishes Pysocha to PyPI. The other builds the four desktop archives, uploads them to a draft GitHub release, and makes the release public.
