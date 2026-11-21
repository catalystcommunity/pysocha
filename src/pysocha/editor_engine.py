"""Build private live previews for the desktop editor over a line-based pipe."""

import contextlib
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import quote

import frontmatter
import yaml
from slugify import slugify
from jinja2 import TemplateNotFound, TemplateSyntaxError
from werkzeug.serving import make_server

from .build import buildSite, strip_markdown_extension
from .config import override_config
from .preview import makePreviewServer


def inside(root, path):
    path = (root / path).resolve()
    try:
        return path.relative_to(root)
    except ValueError:
        raise ValueError("Select a file inside the site folder.")


def explain(error):
    if isinstance(error, yaml.YAMLError):
        mark = getattr(error, "problem_mark", None)
        line = " on line {}".format(mark.line + 1) if mark else ""
        return "Check the YAML indentation and punctuation{}: {}".format(
            line, getattr(error, "problem", None) or str(error))
    if isinstance(error, TemplateNotFound):
        return "Pysocha could not find the template {!r}. Check the selected theme folder and template name.".format(error.name)
    if isinstance(error, TemplateSyntaxError):
        return "Check {} on line {}. {}".format(error.name, error.lineno, error.message)
    if isinstance(error, FileNotFoundError):
        return "Pysocha needs a file or folder that it could not find. Check {}.".format(error.filename)
    if isinstance(error, KeyError):
        return "Add the missing field {} to the page, post, or site configuration.".format(error)
    return "Check the site files and try again. {}".format(error)


def active_page(config, content, name):
    if not name or Path(name).suffix.lower() != ".md":
        return None
    source = Path(name)
    if source.parent not in (content / "pages", content / "blog_posts"):
        return None
    path = Path(config["contentDir"]) / source.relative_to(content)
    fields = frontmatter.loads(path.read_text(encoding="utf-8")).metadata
    extension = fields.get("Extension", config["defaultExtension"])
    if source.parent.name == "pages":
        filename = strip_markdown_extension(source.name) + extension
    else:
        filename = config["blogConfig"]["blogBaseDir"] + "/" + slugify(fields["Title"]) + extension
    return "/" + quote(filename.lstrip("/"))


def copy_site_folder(source, target):
    def check_links(directory, names):
        for name in names:
            path = Path(directory) / name
            if path.is_symlink():
                inside(source, path)
                if path.is_dir():
                    raise ValueError("Use a folder instead of a directory link at {}.".format(path))
        return {".git"} & set(names)
    shutil.copytree(str(source), str(target), ignore=check_links)


def build_preview(config_path, edits, output, work, templates=None, active=None):
    root = config_path.parent
    config_text = edits.get(config_path.name)
    if config_text is None:
        config_text = config_path.read_text(encoding="utf-8")
    settings = yaml.safe_load(config_text)
    if settings is not None and not isinstance(settings, dict):
        raise ValueError("Start the configuration with a YAML mapping of setting names to values.")
    config = override_config(settings)
    if templates:
        config["templatesDir"] = templates
    # Preview edits and downloaded assets belong in a scratch tree. Keep all
    # generated output outside the user's site, even with a custom outputDir.
    content = inside(root, config["contentDir"])
    for key in ("contentDir", "templatesDir"):
        relative = inside(root, config[key])
        source = root / relative
        target = work / key
        if not relative.parts:
            raise ValueError("Use a separate folder for {}.".format(key))
        copy_site_folder(source, target)
        for name, value in edits.items():
            path = inside(root, name)
            if relative in path.parents:
                file = target / path.relative_to(relative)
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(value, encoding="utf-8")
        config[key] = str(target)
    config["outputDir"] = str(output)
    with contextlib.redirect_stdout(sys.stderr):
        buildSite(config)
    return config, active_page(config, content, active)


def respond(**data):
    print(json.dumps(data), flush=True)


def main():
    config_path = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="pysocha-preview-") as temp:
        output = Path(temp) / "site"
        app = makePreviewServer(str(output))
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        respond(origin="http://127.0.0.1:{}".format(server.server_port))
        try:
            for line in sys.stdin:
                message = json.loads(line)
                try:
                    with tempfile.TemporaryDirectory(dir=temp) as stage:
                        config, page = build_preview(
                            config_path, message["edits"], output, Path(stage),
                            templates=message.get("templates"), active=message.get("active"),
                        )
                    makePreviewServer(str(output), config["startPage"], config["defaultExtension"])
                    respond(revision=message["revision"], page=page, start="/" + quote(config["startPage"].lstrip("/")))
                except Exception as error:
                    respond(revision=message["revision"], error=explain(error).replace(stage + os.sep, "").replace(str(temp), "preview"))
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
