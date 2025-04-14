import pytest
import torch
import onnxruntime
import numpy as np
from invesalius.segmentation.deep_learning.model import Unet3D 


@pytest.fixture(scope="module")
def models():
    # PyTorch model
    pytorch_model = Unet3D(in_channels=1, out_channels=1, init_features=8)
    pytorch_model.eval()

    # Export to ONNX
    dummy_input = torch.randn(1, 1, 48, 48, 48)
    onnx_file = "unet3d_test.onnx"
    torch.onnx.export(
        pytorch_model,
        dummy_input,
        onnx_file,
        input_names=["input"],
        output_names=["output"],
        opset_version=11,
    )

    # Load ONNX model
    onnx_session = onnxruntime.InferenceSession(onnx_file)
    return pytorch_model, onnx_session


def test_unet3d_conversion(models):
    pytorch_model, onnx_session = models
    num_tests = 100
    atol = 1e-5  # absolute tolerance for floating-point comparison

    for _ in range(num_tests):
        #random input
        input_tensor = torch.randn(1, 1, 48, 48, 48)
        input_numpy = input_tensor.numpy()

        # pytorch inference
        with torch.no_grad():
            pytorch_output = pytorch_model(input_tensor).numpy()

        # ONNX inference
        ort_inputs = {onnx_session.get_inputs()[0].name: input_numpy}
        onnx_output = onnx_session.run(None, ort_inputs)[0]

        # check if outputs are approximately equal
        np.testing.assert_allclose(
            pytorch_output,
            onnx_output,
            atol=atol,
            err_msg="PyTorch and ONNX outputs differ beyond tolerance"
        )