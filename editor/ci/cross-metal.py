"""Enable GPUI's shader source generator on a Linux build host."""
import os
import shutil
from pathlib import Path

# The published build script checks the host OS. Its runtime_shaders path
# generates text with cbindgen and does not require Apple's Metal compiler.
cargo = Path(os.environ["CARGO_HOME"])
source, = cargo.glob("registry/src/*/gpui-pre-apple-0.3.12")
local = Path("gpui-apple-cross")
shutil.copytree(source, local)
build = local / "build.rs"
guard = '#[cfg(any(target_os = "macos", target_os = "ios"))]'
text = build.read_text()
assert text.count(guard) == 2
build.write_text(text.replace(guard, ""))
manifest = local / "Cargo.toml"
old = """[target.'cfg(any(target_os = "macos", target_os = "ios"))'.build-dependencies.cbindgen]"""
text = manifest.read_text()
assert old in text
manifest.write_text(text.replace(old, "[build-dependencies.cbindgen]"))
with Path("Cargo.toml").open("a") as output:
    output.write('\n[patch.crates-io]\ngpui-pre-apple = { path = "gpui-apple-cross" }\n')
