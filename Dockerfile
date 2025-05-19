FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive


# Set locale
RUN apt-get update && apt-get install -y locales
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

RUN apt-get install -y \
    freeglut3 \
    freeglut3-dev \
    libgl1-mesa-dev \
    libglu1-mesa-dev \
    libgstreamer-plugins-base1.0-dev \
    libgtk-3-dev \
    libjpeg-dev \
    libnotify-dev \
    libsdl2-dev \
    libsm-dev \
    libtiff-dev \
    libwebkit2gtk-4.0-dev \
    libxtst-dev \
    python3-dev \
    libhdf5-dev \
    build-essential \
    python3-venv \
    python3-pip

# === Install OpenSCAD via AppImage ===
RUN apt-get update && apt-get install -y \
    fuse \
    libfuse2 \
    wget

RUN wget https://files.openscad.org/OpenSCAD-2021.01-x86_64.AppImage -O /usr/local/bin/openscad && \
    chmod +x /usr/local/bin/openscad


# Set working directory
WORKDIR /usr/local/app

# Install Python requirements
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy application files
COPY . .

# Optional: compile any extensions
RUN python3 setup.py build_ext --inplace || true  # ignore if setup.py isn't present

# Default command (optional)
# CMD ["python3", "tag.py"]