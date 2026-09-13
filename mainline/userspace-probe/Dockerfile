FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd AS build

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libegl-dev \
        libgles-dev \
    && rm -rf /var/lib/apt/lists/*

COPY r46h-gles2-fbo-probe.c /src/r46h-gles2-fbo-probe.c

RUN cc -std=c11 -O2 -Wall -Wextra -Werror \
      /src/r46h-gles2-fbo-probe.c -o /r46h-gles2-fbo-probe \
      -lEGL -lGLESv2 \
    && strip /r46h-gles2-fbo-probe

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ARG DEBIAN_FRONTEND=noninteractive

COPY packages.txt /tmp/packages.txt
RUN apt-get update \
    && xargs -r apt-get install -y --no-install-recommends < /tmp/packages.txt \
    && rm -rf /var/lib/apt/lists/* /tmp/packages.txt

COPY --from=build /r46h-gles2-fbo-probe /usr/local/libexec/r46h-gles2-fbo-probe

ENV EGL_PLATFORM=surfaceless \
    GALLIUM_DRIVER=panfrost \
    MESA_LOADER_DRIVER_OVERRIDE=panfrost \
    MESA_SHADER_CACHE_DISABLE=true

ENTRYPOINT ["/usr/local/libexec/r46h-gles2-fbo-probe"]
