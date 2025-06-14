FROM ubuntu:22.04

# Install required packages for image building
RUN apt-get update && apt-get install -y \
    wget \
    xz-utils \
    fdisk \
    mount \
    util-linux \
    parted \
    dosfstools \
    && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /builder

# Copy scripts and configs
COPY scripts/ ./scripts/
COPY configs/ ./configs/
COPY build_image_docker.sh ./build_image.sh

# Make scripts executable
RUN chmod +x ./build_image.sh ./scripts/*.sh

# Default command
CMD ["./build_image.sh", "default"]
