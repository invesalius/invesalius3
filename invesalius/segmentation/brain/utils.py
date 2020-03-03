def get_plaidml_devices(gpu=False):
    import plaidml

    ctx = plaidml.Context()
    plaidml.settings._setup_for_test(plaidml.settings.user_settings)
    plaidml.settings.experimental = True
    devices, _ = plaidml.devices(ctx, limit=100, return_all=True)
    if gpu:
        for device in devices:
            if b"cuda" in device.description.lower():
                return device
        for device in devices:
            if b"opencl" in device.description.lower():
                return device
    for device in devices:
        if b"llvm" in device.description.lower():
            return device
