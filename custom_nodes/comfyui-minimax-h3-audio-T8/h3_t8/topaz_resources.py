"""Topaz-only NVIDIA telemetry; does not change the qualified DLSS FI gate."""
from .dlss_fi_backend.resources import NvmlResourceReader


class TopazResourceReader(NvmlResourceReader):
    """Observe the explicitly selected physical NVIDIA index without allocating CUDA.

    The index is in nvidia-smi/NVML order. A heterogeneous vendor installation
    whose Topaz GPU order differs needs its exported device mapping checked;
    this observer is not a claim of universal vendor/CUDA ordinal equivalence.
    """
    def __init__(self, device_index):
        if type(device_index) is not int or not 0 <= device_index <= 15:
            raise ValueError('Select a Topaz NVIDIA device index in 0..15')
        self.device_index = device_index

    def __enter__(self):
        import psutil
        import pynvml
        self.nvml, self.psutil = pynvml, psutil
        pynvml.nvmlInit()
        try:
            count = pynvml.nvmlDeviceGetCount()
            if self.device_index >= count:
                raise RuntimeError(f'Topaz NVIDIA monitor index {self.device_index} is unavailable ({count} visible devices); check nvidia-smi and the Topaz exported device index')
            self.device = pynvml.nvmlDeviceGetHandleByIndex(self.device_index)
            uuid = pynvml.nvmlDeviceGetUUID(self.device)
            self.uuid = uuid.decode('ascii') if isinstance(uuid, bytes) else str(uuid)
        except BaseException:
            pynvml.nvmlShutdown()
            raise
        return self
