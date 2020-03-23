def get_plaidml_devices(gpu=False):
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
