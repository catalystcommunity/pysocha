from pathlib import Path
import shutil

import pytest
import yaml

from pysocha.editor_engine import build_preview, explain


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
