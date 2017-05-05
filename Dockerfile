FROM ubuntu:16.04

RUN apt-get update
RUN apt-get install -y \
    cython \
    python-concurrent.futures \
    python-gdcm \
    python-matplotlib \
    python-nibabel \
    python-numpy \
    python-pil \
    python-psutil \
    python-scipy \
    python-serial \
    python-skimage \
    python-vtk6 \
    python-vtkgdcm \
    python-wxgtk3.0 \
    xvfb # For a virtual X server.

WORKDIR /usr/local/app

COPY . .

RUN python setup.py build_ext --inplace

RUN Xvfb :10 -ac -screen 0 1024x768x24 &
