FROM rust:1.100-trixie AS build
ARG TARGET
WORKDIR /build
RUN set -eu; case "$TARGET" in \
    x86_64-unknown-linux-gnu) arch=amd64 ;; \
    aarch64-unknown-linux-gnu) arch=arm64; dpkg --add-architecture arm64 ;; \
    *) exit 1 ;; esac; \
    echo 'path-exclude=/usr/share/man/*' > /etc/dpkg/dpkg.cfg.d/pysocha; apt-get update; apt-get install -y --no-install-recommends clang cmake pkg-config \
      gcc-aarch64-linux-gnu g++-aarch64-linux-gnu libwebkit2gtk-4.1-dev:$arch \
      libxkbcommon-x11-dev:$arch libfontconfig-dev:$arch libssl-dev:$arch \
      libx11-xcb-dev:$arch libx11-dev:$arch libwayland-dev:$arch; \
    rustup target add "$TARGET"
COPY Cargo.toml Cargo.lock build.rs ./
COPY assets/pysocha-128.png assets/
COPY src src
RUN set -eu; \
    export PKG_CONFIG_ALLOW_CROSS=1 PKG_CONFIG_LIBDIR=/usr/lib/$(echo "$TARGET" | sed s/-unknown//)/pkgconfig:/usr/share/pkgconfig; \
    export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc; \
    if [ "$TARGET" = x86_64-unknown-linux-gnu ]; then cargo test --release --locked --target "$TARGET" -j 4; fi; \
    cargo build --locked --release --target "$TARGET" -j 4; \
    cp "target/$TARGET/release/pysocha-editor" /pysocha-editor
FROM scratch
COPY --from=build /pysocha-editor /
