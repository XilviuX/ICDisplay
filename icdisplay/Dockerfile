ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache \
    python3 \
    py3-pip \
    gcc \
    python3-dev \
    musl-dev \
    linux-headers \
    i2c-tools \
    freetype \
    freetype-dev \
    jpeg-dev \
    zlib-dev \
    ttf-dejavu \
    wget \
    unzip

# Silkscreen — police bitmap pixel-perfect pour petits écrans
RUN mkdir -p /usr/share/fonts/silkscreen && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/silkscreen/Silkscreen-Regular.ttf" \
         -O /usr/share/fonts/silkscreen/Silkscreen-Regular.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/silkscreen/Silkscreen-Bold.ttf" \
         -O /usr/share/fonts/silkscreen/Silkscreen-Bold.ttf

RUN pip3 install --break-system-packages \
    luma.oled \
    requests \
    pillow

COPY run.py /run.py

CMD ["python3", "/run.py"]
