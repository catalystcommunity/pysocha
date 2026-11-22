from pathlib import Path
import shutil

import pytest
import yaml
from jinja2 import TemplateSyntaxError

from pysocha.editor_engine import PreviewSession, build_preview, explain


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "working"
    shutil.copytree(Path(__file__).resolve().parents[1] / "example", root, ignore=shutil.ignore_patterns("generated"))
    path = root / "config.yaml"
    path.write_text("search: []\n")
    return path


def build(site, edits, tmp_path, **options):
    stage = tmp_path / "stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    return build_preview(site, edits, tmp_path / "preview", stage, **options)


def test_preview_uses_unsaved_buffers_and_preserves_last_success(site, tmp_path):
    page = "content/pages/index.md"
    original = (site.parent / page).read_bytes()
    edits = {page: "---\nTitle: Draft\n---\nA draft paragraph"}
    _, location = build(site, edits, tmp_path, active=page)
    assert location == "/index.html"
    result = tmp_path / "preview/index.html"
    assert "A draft paragraph" in result.read_text()
    good = result.read_bytes()
    edits["config.yaml"] = "search: ["
    with pytest.raises(yaml.YAMLError) as caught:
        build(site, edits, tmp_path)
    assert "line" in explain(caught.value)
    assert result.read_bytes() == good
    assert (site.parent / page).read_bytes() == original
    assert not (site.parent / "generated").exists()


def test_preview_theme_changes_only_the_private_build(site, tmp_path):
    theme = site.parent / "themes/print"
    shutil.copytree(site.parent / "templates", theme)
    (theme / "page.jinja2").write_text("<title>Print edition</title>{{ content }}")
    build(site, {}, tmp_path, templates="themes/print")
    assert "<title>Print edition</title>" in (tmp_path / "preview/index.html").read_text()
    assert "Print edition" not in (site.parent / "templates/page.jinja2").read_text()


def test_post_tab_uses_the_title_slug_and_custom_extension(site, tmp_path):
    post = "content/blog_posts/first_post.md"
    config = 'blogConfig:\n  blogBaseDir: posts\n'
    text = (site.parent / post).read_text()
    import frontmatter
    document = frontmatter.loads(text)
    document["Title"] = "A fresh title"
    document["Extension"] = ".htm"
    _, url = build(site, {"config.yaml": config, post: frontmatter.dumps(document)}, tmp_path, active=post)
    assert url == "/posts/a-fresh-title.htm"
    assert (tmp_path / "preview" / url.lstrip("/")).is_file()


def test_incremental_preview_matches_clean_output_and_recovers_after_error(site, tmp_path, monkeypatch):
    from pysocha.search.providers.sqlite_fts import SqliteFtsProvider

    config = {"search": [{"name": "news", "provider": "sqlite-fts5", "path": "news",
                          "include": ["posts", "pages"], "options": {"frontend": False}}]}
    site.write_text(yaml.safe_dump(config))
    session = PreviewSession(site, tmp_path)
    calls = []
    original = SqliteFtsProvider.finalize

    def finalize(provider):
        calls.append(provider.context.instance.name)
        return original(provider)

    monkeypatch.setattr(SqliteFtsProvider, "finalize", finalize)
    first = session.update({})
    assert first["pages"]["content/pages/index.md"] == "/index.html"
    assert calls == ["news"]
    base = "templates/base.jinja2"
    edits = {base: (site.parent / base).read_text() + "\n<!-- layout edit -->"}
    assert session.update(edits)["refresh"] == "all"
    assert calls == ["news"]
    assert "<!-- layout edit -->" in (session.output / "index.html").read_text()

    page = "content/pages/index.md"
    edits[page] = "---\nTitle: Changed\n---\nAn indexed search phrase"
    assert session.update(edits)["refresh"] == "all"
    assert calls == ["news", "news"]
    assert session.update(edits)["refresh"] == "none"
    good = (session.output / "index.html").read_bytes()
    with pytest.raises(TemplateSyntaxError):
        session.update(dict(edits, **{base: "{% if broken %}"}))
    assert (session.output / "index.html").read_bytes() == good
    assert session.update(edits)["refresh"] == "none"

    build(site, edits, tmp_path)
    expected = tmp_path / "preview"
    files = {f.relative_to(expected) for f in expected.rglob("*") if f.is_file()}
    assert files == {f.relative_to(session.output) for f in session.output.rglob("*") if f.is_file()}
    for name in files:
        assert (session.output / name).read_bytes() == (expected / name).read_bytes(), name


def test_stylesheet_edit_and_discard_update_only_the_asset(site, tmp_path, monkeypatch):
    from pysocha import editor_engine

    session = PreviewSession(site, tmp_path)
    session.update({})
    css = "content/extra_files/main.css"
    original = (site.parent / css).read_bytes()

    def no_build(*args, **kwargs):
        pytest.fail("Stylesheet edits must skip the generator")

    monkeypatch.setattr(editor_engine, "buildSite", no_build)
    assert session.update({css: "a { color: red; }"})["refresh"] == "/main.css"
    assert (session.output / "main.css").read_text() == "a { color: red; }"
    assert session.update({})["refresh"] == "/main.css"
    assert (session.output / "main.css").read_bytes() == original
    assert (site.parent / css).read_bytes() == original
