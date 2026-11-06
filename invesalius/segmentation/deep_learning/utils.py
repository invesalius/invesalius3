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
            count = torch.cuda.device_count()
            for i in range(count):
                name = torch.cuda.get_device_name(i)
                device_id = f"cuda:{i}"
                # Disambiguate when several GPUs exist (also covers identical models)
                label = f"{name} ({device_id})" if count > 1 else name
                TORCH_DEVICES[label] = device_id
        TORCH_DEVICES["CPU"] = "cpu"

    return TORCH_DEVICES
