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

RUN apt-get install -y locales
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

WORKDIR /usr/local/app

COPY . .

RUN python setup.py build_ext --inplace
