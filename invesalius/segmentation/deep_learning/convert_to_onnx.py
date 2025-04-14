import torch
from model import Unet3D 

def convert_to_onnx():
    model = Unet3D(in_channels=1, out_channels=1, init_features=8)
    model.eval()

    #dummy input with the correct shape (batch, channels, D, H, W)
    dummy_input = torch.randn(1, 1, 48, 48, 48)

    # Export to ONNX
    onnx_file = "unet3d.onnx"
    torch.onnx.export(
        model,
        dummy_input,
        onnx_file,
        input_names=["input"],
        output_names=["output"],
        opset_version=11,
        verbose=True,
    )
    print(f"Model exported to {onnx_file}")

if __name__ == "__main__":
    convert_to_onnx()