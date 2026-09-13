FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bc \
        bison \
        build-essential \
        ca-certificates \
        cpio \
        curl \
        device-tree-compiler \
        file \
        flex \
        git \
        kmod \
        libelf-dev \
        libssl-dev \
        make \
        patch \
        python3 \
        rsync \
        shellcheck \
        u-boot-tools \
        xz-utils \
        zstd \
    && rm -rf /var/lib/apt/lists/*

ENV KBUILD_BUILD_USER=arkos4clone \
    KBUILD_BUILD_HOST=debian-trixie-arm64 \
    KBUILD_BUILD_VERSION=1 \
    KBUILD_BUILD_TIMESTAMP="2026-07-30 00:00:00 UTC" \
    SOURCE_DATE_EPOCH=1785369600 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC

WORKDIR /workspace
