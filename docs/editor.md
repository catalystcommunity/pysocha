# Pysocha Editor

Download the archive for your computer from the GitHub release. Extract the full archive. Keep the runtime folder with the application. The archive includes Python and the Pysocha search providers.

| Computer | Archive name contains | Start the editor |
| --- | --- | --- |
| Mac with Apple silicon | `macos-arm64` | Open Pysocha Editor.app. |
| 64-bit Intel or AMD Windows | `windows-x86_64` | Run pysocha-editor.exe. |
| 64-bit Intel or AMD Linux | `linux-x86_64` | Run pysocha-editor. |
| ARM64 Linux | `linux-arm64` | Run pysocha-editor. |

The Linux build uses Debian 13 libraries, WebKitGTK 4.1, and an X11 display. A Wayland session can use XWayland. The Windows preview uses the WebView2 Runtime.

To add the Linux application to your desktop menu, open a terminal in the extracted `pysocha-editor` folder. Run these commands. Your desktop session must include `~/.local/bin` in `PATH`.

```sh
mkdir -p ~/.local/bin
ln -s "$PWD/pysocha-editor" ~/.local/bin/pysocha-editor
xdg-icon-resource install --mode user --size 1024 --novendor pysocha.png com.catalystsquad.pysocha.editor
xdg-desktop-menu install --mode user --novendor com.catalystsquad.pysocha.editor.desktop
```

## Edit a site

1. Select **Open site**. Select the YAML configuration file for the site.
2. In **Files**, select a folder to expand it. Select a text file once to open it in a temporary tab. Its name is italic. Select another file to reuse that tab. Double-click the file or its tab to keep it open. The first edit also keeps it open. You can also select **Open file** to use the file dialog.
3. Edit the text. A soft yellow dot beside the file name shows unsaved changes. Use the file tabs to move between open files. Use Ctrl+F to search the active file. On macOS, use Command+F.
4. Select **Side by side** or **Stacked** to see the source and preview together. Select the preview tab to use the full window. Follow a link in the preview to open another page.
5. Select **Save** to write the active file. You can also use Ctrl+S or Command+S.

Select **Hide files** to reduce the panel to its icons. Select **Show files** to see the tree again.

- To add a file, select its folder in the tree. Select the plus icon (**New file**), enter a name, and press Enter.
- To copy a file, select it and use the two-sheets icon (**Duplicate file**). Enter a name for the copy and press Enter. The copy goes in the same folder and includes unsaved edits. If the name is in use, enter another name.

The preview uses unsaved changes from all open files. The status bar shows a spinner while the editor builds or displays an update. Selecting an open tab uses the current build. An edit to a linked stylesheet updates the preview in place and keeps your scroll position. An edit to an imported stylesheet reloads the page. A build error leaves the last successful preview on the screen. Read the message above the preview. Hold the pointer over the message to pause its timer.

Select **Site theme** to try a different template folder in the site. Select **Use site default** to use the configuration again. Select **Dark appearance** or **Light appearance** to change the editor and the browser color scheme. The site controls how its pages respond to the color scheme.

## Create a file from a template

In **Files**, right-click a Markdown or text file and select **Use as template…**. Enter a title. For example, `First Light` gives the file name `first-light.md`. Select **Create file**. The editor opens the new file in the same folder. It uses any unsaved edits in the source file. If the file name is in use, enter a different title.

Use `{$title}` to insert the title. Use `{$current_time}` to insert the local date, time, and UTC offset. All time fields in one draft use the same time. Add a field such as `{$author}` in the YAML header or the Markdown body. The dialog asks for each field once. A field left empty gives an empty string. Use letters, digits, and underscores in a field name. Start the name with a letter or an underscore.

To keep a starter beside published pages or posts, give it a name such as `article.template.md`. The site build skips files that end in `.template.md` and files named `0-basetemplate.md`. The example site includes a starter in `content/blog_posts/article.template.md`.

You can also use an existing article. The editor replaces a fixed YAML `Title` with the new title. Other fixed fields keep their values. For older starters with the literal title `TITLE`, the editor also updates the sample `PostedDate`.

## Run from source

Install Rust and uv. On Linux, also install the development packages in `editor/ci/linux.Dockerfile`. From the repository root, run this command to open the example site.

```sh
./tools.sh editor example/example-config.yaml
```

Run `./tools.sh editor` to choose a site from the editor.

## Release process

A pull request to main starts the Python tests and the editor timer tests. The Python check builds a source distribution and a wheel. It installs the wheel in a clean environment.

A merge to main tags the merge commit. The first tag uses the package version in pyproject.toml. Later merges increase the patch number. Increase the version in pyproject.toml to select a higher release number.

A version tag starts two jobs. One job publishes Pysocha to PyPI. The other builds the four desktop archives, uploads them to a draft GitHub release, and makes the release public.
