FROM ghcr.io/rust-cross/cargo-zigbuild@sha256:b8364c2c60cdcc9b95c402d17654bff517410926a35678bd89dd924b8158d6ae AS build
ENV SDKROOT=/opt/MacOSX11.3.sdk MACOSX_DEPLOYMENT_TARGET=12.0
WORKDIR /build
COPY Cargo.toml Cargo.lock build.rs ./
COPY ci/cross-metal.py /build/
COPY src src
RUN rustup toolchain install 1.100.0 --profile minimal --target aarch64-apple-darwin && \
    cargo +1.100.0 fetch --locked --target aarch64-apple-darwin && python3 cross-metal.py && \
    cargo +1.100.0 zigbuild --release --target aarch64-apple-darwin -j 4
FROM scratch
COPY --from=build /build/target/aarch64-apple-darwin/release/pysocha-editor /
