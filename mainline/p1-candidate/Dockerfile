FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ARG DEBIAN_FRONTEND=noninteractive

COPY rootfs-debian13/apt/debian.sources /etc/apt/sources.list.d/debian.sources
COPY rootfs-debian13/apt/99snapshot /etc/apt/apt.conf.d/99snapshot

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        dosfstools \
        mtools \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC

WORKDIR /work
