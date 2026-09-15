ARG BASE_IMAGE=arkos4clone/r46h-debian13-p2-mvp:v0.1@sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9

FROM ${BASE_IMAGE} AS build
ARG DEBIAN_FRONTEND=noninteractive
ARG SOURCE_DATE_EPOCH=1775822834
ENV LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    TZ=UTC \
    SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}

# Recreate the accepted gaming p2 package state before capturing its ABI. The
# runtime bundle then carries only SONAMEs absent from the actual target; Mesa,
# DRM, RetroArch's FFmpeg/SDL closure and glibc remain owned by p2.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      kbd=2.7.1-2 \
      libretro-desmume=0.9.11+git20160819+dfsg1-2+b2 \
      libretro-gambatte=0.5.0+git20160522+dfsg1-3 \
      libretro-mgba=0.10.5+dfsg-1 \
      libretro-nestopia=1.53.0+20250119.git5b56b6b-1 \
      retroarch=1.20.0+dfsg-2+b1 \
    && ldconfig -p | awk '/^[[:space:]]+[^[:space:]]+ / { print $1 }' | LC_ALL=C sort -u \
      > /tmp/base-sonames
RUN apt-get install -y --no-install-recommends \
      build-essential ca-certificates cmake gettext libasound2-dev libavcodec-dev \
      libavfilter-dev libavformat-dev libavutil-dev libbluetooth-dev \
      libcurl4-openssl-dev libfreeimage-dev libfreetype6-dev libgit2-dev \
      libgles-dev libharfbuzz-dev libicu-dev libpoppler-cpp-dev libpugixml-dev \
      libsdl2-dev patch pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY emulationstation-de-v3.4.1.tar.gz /tmp/source.tar.gz
COPY idle-frame-pacing.patch /tmp/idle-frame-pacing.patch
COPY --chmod=0755 collect-runtime.sh /usr/local/bin/collect-runtime
RUN mkdir /src /build \
    && tar -xzf /tmp/source.tar.gz -C /src --strip-components=1 \
    && cd /src \
    && patch -p1 < /tmp/idle-frame-pacing.patch \
    && cmake -S /src -B /build \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/opt/r46h/es-de \
      -DCMAKE_C_FLAGS_RELEASE='-O2 -DNDEBUG -ffile-prefix-map=/src=.' \
      -DCMAKE_CXX_FLAGS_RELEASE='-O2 -DNDEBUG -ffile-prefix-map=/src=.' \
      -DCMAKE_EXE_LINKER_FLAGS='-Wl,--build-id=none' \
      -DGL=OFF \
      -DGLES=ON \
      -DDEINIT_ON_LAUNCH=ON \
      -DAPPLICATION_UPDATER=OFF \
      -DVIDEO_HW_DECODING=OFF \
    && cmake --build /build --parallel 5 \
    && DESTDIR=/stage cmake --install /build --strip \
    && /usr/local/bin/collect-runtime

FROM scratch AS export
COPY --from=build /artifact/ /
