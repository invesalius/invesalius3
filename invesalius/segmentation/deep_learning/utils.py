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


def prepare_plaidml():
    # Linux if installed plaidml with pip3 install --user
    if sys.platform.startswith("linux"):
        local_user_plaidml = pathlib.Path("~/.local/share/plaidml/").expanduser().absolute()
        if local_user_plaidml.exists():
            os.environ["RUNFILES_DIR"] = str(local_user_plaidml)
            os.environ["PLAIDML_NATIVE_PATH"] = str(
                pathlib.Path("~/.local/lib/libplaidml.so").expanduser().absolute()
            )
    # Mac if using python3 from homebrew
    elif sys.platform == "darwin":
        local_user_plaidml = pathlib.Path("/usr/local/share/plaidml")
        if local_user_plaidml.exists():
            os.environ["RUNFILES_DIR"] = str(local_user_plaidml)
            os.environ["PLAIDML_NATIVE_PATH"] = str(
                pathlib.Path("/usr/local/lib/libplaidml.dylib").expanduser().absolute()
            )
    elif sys.platform == "win32":
        if "VIRTUAL_ENV" in os.environ:
            local_user_plaidml = pathlib.Path(os.environ["VIRTUAL_ENV"]).joinpath("share/plaidml")
            plaidml_dll = pathlib.Path(os.environ["VIRTUAL_ENV"]).joinpath(
                "library/bin/plaidml.dll"
            )
            if local_user_plaidml.exists():
                os.environ["RUNFILES_DIR"] = str(local_user_plaidml)
            if plaidml_dll.exists():
                os.environ["PLAIDML_NATIVE_PATH"] = str(plaidml_dll)


def prepare_ambient(backend, device_id, use_gpu):
    if backend.lower() == "plaidml":
        os.environ["KERAS_BACKEND"] = "plaidml.keras.backend"
        os.environ["PLAIDML_DEVICE_IDS"] = device_id
        prepare_plaidml()
    elif backend.lower() == "theano":
        os.environ["KERAS_BACKEND"] = "theano"
        if use_gpu:
            os.environ["THEANO_FLAGS"] = "device=cuda0"
            print("Use GPU theano", os.environ["THEANO_FLAGS"])
        else:
            os.environ["THEANO_FLAGS"] = "device=cpu"
    else:
        raise TypeError("Wrong backend")


def get_plaidml_devices(gpu=False):
    prepare_plaidml()

    import plaidml

    ctx = plaidml.Context()
    plaidml.settings._setup_for_test(plaidml.settings.user_settings)
    plaidml.settings.experimental = True
    devices, _ = plaidml.devices(ctx, limit=100, return_all=True)
    out_devices = []
    for device in devices:
        points = 0
        if b"cuda" in device.description.lower():
            points += 1
        if b"opencl" in device.description.lower():
            points += 1
        if b"nvidia" in device.description.lower():
            points += 1
        if b"amd" in device.description.lower():
            points += 1
        out_devices.append((points, device))

    out_devices.sort(reverse=True)
    return {
        device.description.decode("utf8"): device.id.decode("utf8")
        for points, device in out_devices
    }
