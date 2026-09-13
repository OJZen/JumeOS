FROM arkos4clone/r46h-ppsspp-builder:v1.20.4
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsdl2-dev libavcodec-dev libavutil-dev libopus-dev libevdev-dev libudev-dev \
    libcurl4-openssl-dev libssl-dev libexpat1-dev libasound2-dev uuid-dev libavahi-client-dev \
    && rm -rf /var/lib/apt/lists/*
COPY . /src/moonlight
RUN cc -DHAVE_SDL $(pkg-config --cflags sdl2) /src/moonlight/tests/r46h-hud.c \
      $(pkg-config --libs sdl2) -o /hud-check \
    && SDL_VIDEODRIVER=dummy /hud-check \
    && cmake -S /src/moonlight -B /build -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/opt/r46h-moonlight-test -DCMAKE_INSTALL_LIBDIR=lib \
    -DENABLE_X11=OFF -DENABLE_CEC=OFF -DENABLE_PULSE=OFF \
    && cmake --build /build -j4 && DESTDIR=/payload cmake --install /build \
    && cp -a /usr/lib/aarch64-linux-gnu/libavahi-common.so.3* \
      /usr/lib/aarch64-linux-gnu/libavahi-client.so.3* /payload/opt/r46h-moonlight-test/lib/ \
    && install -Dm644 /usr/share/doc/libavahi-common3/copyright \
      /payload/opt/r46h-moonlight-test/share/licenses/avahi \
    && install -Dm644 /src/moonlight/LICENSE \
      /payload/opt/r46h-moonlight-test/share/licenses/moonlight \
    && dpkg-query -W > /payload/build-packages.txt \
    && tar -C /payload -czf /moonlight-test.tar.gz .
