FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.name="ShelfServe" \
  io.hass.description="Recipe storage, meal planning, and supermarket-sorted shopping lists" \
  io.hass.arch="${BUILD_ARCH}" \
  io.hass.type="app" \
  io.hass.version="${BUILD_VERSION}" \
  maintainer="Brad"

RUN apk add --no-cache \
    bash \
    python3 \
    py3-pip \
    py3-pillow \
    py3-virtualenv \
    zlib-dev \
    libjpeg-turbo-dev \
    gcc \
    musl-dev \
    python3-dev \
  && python3 -m venv /opt/shelfserve/venv

WORKDIR /opt/shelfserve/app

COPY app/requirements.txt /tmp/requirements.txt
RUN /opt/shelfserve/venv/bin/pip install --no-cache-dir --upgrade pip \
  && /opt/shelfserve/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

COPY app/ /opt/shelfserve/app/
COPY run.sh /run.sh
RUN chmod a+x /run.sh

ENV PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=shelfserve.settings \
    SHELFSERVE_DATA_DIR=/data \
    SHELFSERVE_PORT=8099

CMD ["/run.sh"]
