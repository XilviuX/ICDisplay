ARG BUILD_FROM
FROM $BUILD_FROM

# Install dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-pillow \
    i2c-tools \
    gcc \
    python3-dev \
    musl-dev \
    linux-headers

# Install Python packages
RUN pip3 install --break-system-packages \
    luma.oled \
    requests

# Copy app
COPY run.py /
COPY fonts/ /fonts/

CMD ["python3", "/run.py"]
