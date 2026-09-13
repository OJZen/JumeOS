ARG BASE_IMAGE=arkos4clone/r46h-debian13-p2-mvp:v0.1@sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9

FROM ${BASE_IMAGE}
ARG DEBIAN_FRONTEND=noninteractive
ENV LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    TZ=UTC

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential=12.12 \
      cmake=3.31.6-2 \
      git=1:2.47.3-0+deb13u1 \
      libegl-dev=1.7.0-1+b2 \
      libgles-dev=1.7.0-1+b2 \
      pkg-config=1.8.1-4 \
      python3=3.13.5-1 \
      retroarch=1.20.0+dfsg-2+b1 \
    && rm -rf /var/lib/apt/lists/*
