ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and dependencies
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
    zlib-dev

# Install Python packages
RUN pip3 install --break-system-packages \
    luma.oled \
    requests \
    pillow

# Copy app
COPY run.py /run.py

CMD ["python3", "/run.py"]
