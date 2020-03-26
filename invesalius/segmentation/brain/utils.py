import os
import pathlib
import sys

def prepare_plaidml():
    # Linux if installed plaidml with pip3 install --user
    if sys.platform.startswith("linux"):
        local_user_plaidml = pathlib.Path("~/.local/share/plaidml/").expanduser().absolute()
        if local_user_plaidml.exists():
            os.environ["RUNFILES_DIR"] = str(local_user_plaidml)
            os.environ["PLAIDML_NATIVE_PATH"] = str(pathlib.Path("~/.local/lib/libplaidml.so").expanduser().absolute())
    # Mac if using python3 from homebrew
    elif sys.platform == "darwin":
        local_user_plaidml = pathlib.Path("/usr/local/share/plaidml")
        if local_user_plaidml.exists():
            os.environ["RUNFILES_DIR"] = str(local_user_plaidml)
            os.environ["PLAIDML_NATIVE_PATH"] = str(pathlib.Path("/usr/local/lib/libplaidml.dylib").expanduser().absolute())

def prepare_ambient(backend, device_id, use_gpu):
    if backend.lower() == 'plaidml':
        os.environ["KERAS_BACKEND"] = "plaidml.keras.backend"
        os.environ["PLAIDML_DEVICE_IDS"] = device_id
        prepare_plaidml()
    elif backend.lower() == 'theano':
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
    return {device.description.decode("utf8"): device.id.decode("utf8") for points, device in out_devices }
