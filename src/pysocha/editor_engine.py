"""Build private live previews for the desktop editor over a line-based pipe."""

import contextlib
import copy
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import quote

import frontmatter
import yaml
from slugify import slugify
from jinja2 import BytecodeCache, TemplateNotFound, TemplateSyntaxError
from werkzeug.serving import make_server

from .build import buildSite, strip_markdown_extension
from .config import override_config
from .markdown import parseCommonMark
from .search import BUILTIN_PROVIDERS, build_index, load_search_instances
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


def site_config(config_path, edits, templates):
    config_text = edits.get(config_path.name)
    if config_text is None:
        config_text = config_path.read_text(encoding="utf-8")
    settings = yaml.safe_load(config_text)
    if settings is not None and not isinstance(settings, dict):
        raise ValueError("Start the configuration with a YAML mapping of setting names to values.")
    config = override_config(settings)
    if templates:
        config["templatesDir"] = templates
    return config


def build_preview(config_path, edits, output, work, templates=None, active=None, *, cache=None, config=None):
    root = config_path.parent
    config = dict(config or site_config(config_path, edits, templates))
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
        buildSite(config, preview_cache=cache)
    return config, active_page(config, content, active)


class PreviewTemplates(BytecodeCache):
    """Reuse compiled Jinja across temporary inputs. Jinja checks the source checksum."""

    def __init__(self):
        self.code = {}

    def get_cache_key(self, name, filename=None):
        return name

    def load_bytecode(self, bucket):
        if bucket.key in self.code:
            bucket.bytecode_from_string(self.code[bucket.key])

    def dump_bytecode(self, bucket):
        self.code[bucket.key] = bucket.bytecode_to_string()


@dataclass
class CachedOutput:
    key: tuple
    directory: tempfile.TemporaryDirectory
    result: object
    routes: dict


class PreviewCache:
    """Reusable Markdown and provider artifacts owned by one editor session."""

    def __init__(self, work):
        self.work = work
        self.documents = {}
        self.indexes = {}
        self.routes = {}
        self.extra_inputs = {}
        self.templates = PreviewTemplates()
        self.sections = {}
        self.section_inputs = {}

    def parse(self, content, path, text, options):
        key = os.path.relpath(path, content)
        entry = self.documents.get(key)
        if entry is None or entry[:2] != (text, options):
            entry = (text, options, parseCommonMark(text, options, source=path))
            self.documents[key] = entry
        # The generator adds per-render fields to front matter.
        return copy.deepcopy(entry[2])

    def route(self, source, output, config):
        key = Path(source).relative_to(config["contentDir"]).as_posix()
        config["_routes"][key] = "/" + quote(Path(output).relative_to(config["outputDir"]).as_posix())

    def render_section(self, section, render, config, verbose):
        # A slug change can affect Markdown links in either section.
        key = (self.section_inputs[section], config["_replacements"])
        entry = self.sections.get(section)
        if entry is None or entry.key != key:
            scratch = tempfile.TemporaryDirectory(dir=self.work)
            private = dict(config, outputDir=scratch.name, _routes={})
            try:
                records = render(private, verbose=verbose)
            except BaseException:
                scratch.cleanup()
                raise
            if entry is not None:
                entry.directory.cleanup()
            entry = self.sections[section] = CachedOutput(key, scratch, records, private["_routes"])
        shutil.copytree(entry.directory.name, config["outputDir"], dirs_exist_ok=True)
        self.routes.update(entry.routes)
        return entry.result

    def index(self, context, records):
        instance = context.instance
        if instance.provider not in BUILTIN_PROVIDERS:
            return build_index(context, records)
        key = (instance, context.language, context.site_title, context.site_address, records,
               self.extra_inputs if instance.provider == "sqlite-fts5" else None)
        entry = self.indexes.get(instance.name)
        if entry is None or entry.key != key:
            scratch = tempfile.TemporaryDirectory(dir=self.work)
            try:
                directory = Path(scratch.name) / inside(Path(scratch.name), instance.path)
                directory.mkdir(parents=True, exist_ok=True)
                private = replace(context, instance_dir=str(directory), output_dir=scratch.name)
                assets = build_index(private, records)
            except BaseException:
                scratch.cleanup()
                raise
            if entry is not None:
                entry.directory.cleanup()
            entry = self.indexes[instance.name] = CachedOutput(key, scratch, assets, {})
        shutil.copytree(entry.directory.name, context.output_dir, dirs_exist_ok=True)
        return entry.result


class PreviewSession:
    def __init__(self, config_path, work):
        self.config_path = config_path
        self.root = config_path.parent
        self.work = work
        self.output = work / "site"
        self.cache = PreviewCache(work)
        self.previous = None
        self.inputs = {}
        self.pages = {}

    def snapshot(self, config, edits):
        inputs = {}
        roots = []

        def fail(error):
            raise error
        for key in ("contentDir", "templatesDir"):
            base = self.root / inside(self.root, config[key])
            if base == self.root:
                raise ValueError("Use a separate folder for {}.".format(key))
            roots.append(base.relative_to(self.root))
            for folder, dirs, files in os.walk(str(base), onerror=fail):
                inputs[Path(folder).relative_to(self.root)] = ()
                dirs[:] = [d for d in dirs if d != ".git"]
                for name in dirs:
                    if (Path(folder) / name).is_symlink():
                        raise ValueError("Use a folder instead of a directory link at {}.".format(Path(folder) / name))
                for name in files:
                    path = Path(folder) / name
                    if path.is_symlink():
                        inside(base, path)
                    st = path.stat()
                    inputs[path.relative_to(self.root)] = (st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        for name, text in edits.items():
            path = inside(self.root, name)
            if any(base in path.parents for base in roots):
                inputs[path] = text
        return inputs

    def update_stylesheet(self, path, inputs, extras, config):
        if (path.suffix.lower() != ".css" or extras not in path.parents or path not in inputs
                or path not in self.inputs or inside(self.root, config["templatesDir"]) in path.parents
                or config["defaultExtension"].lower() == ".css"):
            return None
        relative = path.relative_to(extras)
        url = "/" + quote(relative.as_posix())
        target = self.output / relative
        if url in self.pages.values() or not target.is_file():
            return None
        for instance in load_search_instances(config):
            if instance.provider not in BUILTIN_PROVIDERS or Path(instance.path) in relative.parents:
                return None
        value = inputs[path]
        data = value.encode("utf-8") if isinstance(value, str) else (self.root / path).read_bytes()
        # Replace a single asset atomically while the preview server is reading it.
        with tempfile.TemporaryDirectory(dir=self.work) as scratch:
            new_file = Path(scratch) / "style.css"
            new_file.write_bytes(data)
            os.replace(new_file, target)
        return url

    def update(self, edits, templates=None):
        config = site_config(self.config_path, edits, templates)
        inputs = self.snapshot(config, edits)
        content = inside(self.root, config["contentDir"])
        extras = content / "extra_files"
        changed = {p for p in self.inputs.keys() | inputs.keys() if self.inputs.get(p) != inputs.get(p)}
        refresh = "all"
        if config == self.previous:
            if not changed:
                refresh = "none"
            elif len(changed) == 1:
                refresh = self.update_stylesheet(next(iter(changed)), inputs, extras, config) or "all"
        if refresh == "all":
            template_dir = inside(self.root, config["templatesDir"])
            theme = {p: v for p, v in inputs.items() if template_dir in p.parents}
            for section in ("pages", "blog_posts"):
                folder = content / section
                sources = {p: v for p, v in inputs.items() if folder in p.parents}
                self.cache.section_inputs[section] = (config, theme, sources)
            self.cache.routes = {}
            self.cache.extra_inputs = {p: v for p, v in inputs.items() if extras in p.parents}
            with tempfile.TemporaryDirectory(dir=self.work) as stage:
                build_preview(self.config_path, edits, self.output, Path(stage), cache=self.cache, config=config)
            self.pages = {(content / key).as_posix(): url for key, url in self.cache.routes.items()}
        self.previous, self.inputs = config, inputs
        return dict(start="/" + quote(config["startPage"].lstrip("/")), pages=self.pages, refresh=refresh)


def respond(**data):
    print(json.dumps(data), flush=True)


def main():
    config_path = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="pysocha-preview-") as temp:
        session = PreviewSession(config_path, Path(temp))
        output = session.output
        app = makePreviewServer(str(output))
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        respond(origin="http://127.0.0.1:{}".format(server.server_port))
        try:
            for line in sys.stdin:
                message = json.loads(line)
                try:
                    result = session.update(message["edits"], message.get("templates"))
                    makePreviewServer(str(output), session.previous["startPage"], session.previous["defaultExtension"])
                    respond(revision=message["revision"], **result)
                except Exception as error:
                    respond(revision=message["revision"], error=explain(error).replace(str(temp), "preview"))
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
