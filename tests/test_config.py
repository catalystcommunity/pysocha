from pysocha.config import CONFIG, override_config


def test_override_config_deep_merges_nested_values():
    config = override_config({
        "blogConfig": {
            "blogBaseDir": "writing",
        },
        "markdown": {
            "syntaxHighlighting": {
                "style": "catppuccin-latte",
            },
        },
    })

    assert config["blogConfig"]["blogBaseDir"] == "writing"
    assert config["blogConfig"]["blogTemplate"] == "blog.jinja2"
    assert config["markdown"]["syntaxHighlighting"]["style"] == "catppuccin-latte"
    assert config["markdown"]["syntaxHighlighting"]["enabled"] is True
    assert CONFIG["blogConfig"]["blogBaseDir"] == "blog"
    assert CONFIG["markdown"]["syntaxHighlighting"]["style"] == "catppuccin-mocha"
