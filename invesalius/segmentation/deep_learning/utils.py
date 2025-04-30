import os
import pathlib
import sys


def get_torch_devices():
    TORCH_DEVICES = {}

    try:
        import torch

        HAS_TORCH = True
    except ImportError:
        HAS_TORCH = False

    if HAS_TORCH:
        TORCH_DEVICES = {}
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                name = torch.cuda.get_device_name()
                device_id = f"cuda:{i}"
                TORCH_DEVICES[name] = device_id
        TORCH_DEVICES["CPU"] = "cpu"

    return TORCH_DEVICES
