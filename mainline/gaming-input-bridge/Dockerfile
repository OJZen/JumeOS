ARG BASE_IMAGE=arkos4clone/r46h-debian13-p2-mvp:v0.1@sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9

FROM ${BASE_IMAGE}
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential file \
    && rm -rf /var/lib/apt/lists/*
COPY gaming-input-bridge/r46h-input-bridge.c /src/r46h-input-bridge.c
RUN cc -std=c11 -O2 -Wall -Wextra -Werror \
      -fstack-protector-strong -D_FORTIFY_SOURCE=2 \
      -Wl,-z,relro,-z,now -Wl,--build-id=none \
      /src/r46h-input-bridge.c -o /r46h-input-bridge \
    && strip /r46h-input-bridge \
    && file /r46h-input-bridge | grep -Eq 'ELF 64-bit.*ARM aarch64' \
    && test "$(/r46h-input-bridge --version)" = r46h-gaming-input-bridge-v0.5
