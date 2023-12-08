FROM ubuntu:22.04

USER root:root

# Install necessary dependencies and tools
# RUN sudo apt install wget build-essential libncursesw5-dev libssl-dev \
# libsqlite3-dev tk-dev libgdbm-dev libc6-dev libbz2-dev libffi-dev zlib1g-dev
ARG DEBIAN_FRONTEND=noninteractive
ARG TZ=Asia/Tokyo
RUN <<EOF
apt-get update -y
apt-get install software-properties-common wget make build-essential libssl-dev ca-certificates libasound2 -y
add-apt-repository ppa:deadsnakes/ppa
apt-get update -y
apt-get install -y python3.12 python3-pip python3.12-venv
EOF

# Set the working directory
WORKDIR /app

# Copy the requirements.txt file to the container
COPY requirements.txt .

RUN <<EOF
wget -O - https://www.openssl.org/source/openssl-1.1.1u.tar.gz | tar zxf -
cd openssl-1.1.1u
./config --prefix=/usr/local
make -j $(nproc)
make install_sw install_ssldirs
ldconfig -v
# export SSL_CERT_DIR=/etc/ssl/certs
EOF

ENV SSL_CERT_DIR=/etc/ssl/certs

RUN <<EOT bash
  python3.12 -m venv venv
  source ./venv/bin/activate
  pip install -r requirements.txt
EOT

COPY app .

# Create a virtual environment and activate it
# RUN python3.11 -m venv venv
# ENV PATH="/app/venv/bin:$PATH"

# Install Python packages from requirements.txt
# RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code to the container
# COPY . .

# Specify the command to run the application
COPY docker-entrypoint.sh /docker-entrypoint.sh
# ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
ENTRYPOINT ["/docker-entrypoint.sh"]
# CMD [ "python3", "./run.py" ]
# CMD [ "ls", "-lth" ]
# CMD [ "pip", "freeze" ]
# CMD [ "which", "python" ]
