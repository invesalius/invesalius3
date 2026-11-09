from unittest import mock

from invesalius.segmentation.deep_learning import utils


def _devices(names, cuda=True):
    fake = mock.MagicMock()
    fake.cuda.is_available.return_value = cuda
    fake.cuda.device_count.return_value = len(names)
    fake.cuda.get_device_name.side_effect = lambda dev=None: names[0 if dev is None else dev]
    with mock.patch.dict("sys.modules", {"torch": fake}):
        return utils.get_torch_devices()


def test_two_different_gpus():
    d = _devices(["RTX 3060", "GTX 1050"])
    assert d == {
        "RTX 3060 (cuda:0)": "cuda:0",
        "GTX 1050 (cuda:1)": "cuda:1",
        "CPU": "cpu",
    }


def test_two_identical_gpus():
    d = _devices(["RTX 4090", "RTX 4090"])
    assert sorted(v for v in d.values() if v != "cpu") == ["cuda:0", "cuda:1"]


def test_single_gpu_label_unchanged():
    assert _devices(["RTX 3060"]) == {"RTX 3060": "cuda:0", "CPU": "cpu"}


def test_no_cuda_only_cpu():
    assert _devices([], cuda=False) == {"CPU": "cpu"}

