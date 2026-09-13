ARG BASE_IMAGE=arkos4clone/r46h-debian13-p2-mvp:v0.1@sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9

FROM ${BASE_IMAGE} AS core-build
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential retroarch-dev \
    && rm -rf /var/lib/apt/lists/*
COPY gaming-mvp/r46h-smoke-core.c /src/r46h-smoke-core.c
COPY gaming-input-bridge/r46h-input-bridge.c /src/r46h-input-bridge.c
RUN cc -std=c11 -O2 -fPIC -shared -Wall -Wextra -Werror \
      -Wl,-z,relro,-z,now -Wl,--build-id=none \
      /src/r46h-smoke-core.c -o /r46h-smoke-libretro.so \
    && strip /r46h-smoke-libretro.so \
    && cc -std=c11 -O2 -Wall -Wextra -Werror \
      -fstack-protector-strong -D_FORTIFY_SOURCE=2 \
      -Wl,-z,relro,-z,now -Wl,--build-id=none \
      /src/r46h-input-bridge.c -o /r46h-input-bridge \
    && strip /r46h-input-bridge \
    && test "$(/r46h-input-bridge --version)" = r46h-gaming-input-bridge-v0.5

FROM ${BASE_IMAGE}
ARG DEBIAN_FRONTEND=noninteractive
COPY gaming-mvp/packages.txt /tmp/packages.txt
RUN set -eux; \
    apt-get update; \
    mkdir -p /payload/debs /payload/files; \
    xargs -r apt-get install -y --download-only --no-install-recommends < /tmp/packages.txt; \
    cp /var/cache/apt/archives/*.deb /payload/debs/; \
    for package in $(cat /tmp/packages.txt); do \
      apt-cache policy "$package" | awk -v package="$package" '/Candidate:/ { print package "\t" $2 }'; \
    done | LC_ALL=C sort > /payload/PACKAGES.tsv; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*.deb /tmp/packages.txt
COPY --from=core-build /r46h-smoke-libretro.so /payload/files/r46h-smoke-libretro.so
COPY --from=core-build /r46h-input-bridge /payload/files/r46h-input-bridge
COPY gaming-mvp/retroarch.cfg /payload/files/retroarch.cfg
COPY rootfs-debian13/overlay/etc/fstab /payload/files/fstab
COPY gaming-mvp/r46h-game-ui /payload/files/r46h-game-ui
COPY gaming-mvp/r46h-gaming-frontend-condition /payload/files/r46h-gaming-frontend-condition
COPY gaming-mvp/r46h-gaming-frontend.service /payload/files/r46h-gaming-frontend.service
COPY gaming-mvp/r46h-gaming-input-ready /payload/files/r46h-gaming-input-ready
COPY gaming-mvp/r46h-gaming-input.service /payload/files/r46h-gaming-input.service
COPY gaming-mvp/r46h-volume-keys /payload/files/r46h-volume-keys
COPY gaming-mvp/r46h-volume-keys.service /payload/files/r46h-volume-keys.service
COPY gaming-mvp/r46h-storage-audit /payload/files/r46h-storage-audit
COPY gaming-mvp/install.sh /payload/install.sh
RUN chmod 0755 /payload/install.sh /payload/files/r46h-game-ui \
       /payload/files/r46h-gaming-frontend-condition \
       /payload/files/r46h-gaming-input-ready \
       /payload/files/r46h-volume-keys \
       /payload/files/r46h-input-bridge /payload/files/r46h-storage-audit \
    && chmod 0644 /payload/PACKAGES.tsv /payload/files/fstab \
       /payload/files/retroarch.cfg \
       /payload/files/r46h-smoke-libretro.so \
       /payload/files/r46h-gaming-frontend.service \
       /payload/files/r46h-gaming-input.service \
       /payload/files/r46h-volume-keys.service \
    && test -s /payload/PACKAGES.tsv \
    && test "$(find /payload/debs -type f -name '*.deb' | wc -l)" -gt 10
