FROM ghcr.io/rust-cross/cargo-xwin@sha256:9856b895265d4966f212228ba64802cf89337e2a2a537aa2533c1b8784cbc81b AS build
WORKDIR /build
COPY Cargo.toml Cargo.lock build.rs ./
COPY assets/pysocha.rc assets/pysocha.ico assets/
COPY src src
RUN rustup toolchain install 1.100.0 --profile minimal --target x86_64-pc-windows-msvc && \
    cargo +1.100.0 xwin build --locked --release --target x86_64-pc-windows-msvc -j 4
FROM scratch
COPY --from=build /build/target/x86_64-pc-windows-msvc/release/pysocha-editor.exe /
