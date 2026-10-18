"""Mocked two-card telemetry; no GPU or NVML calls are executed by these tests."""
import sys
from types import SimpleNamespace

import pytest

from h3_audio_t8_pkg.topaz_resources import TopazResourceReader
from h3_audio_t8_pkg.dlss_fi_backend.resources import NvmlResourceReader


@pytest.fixture
def nvml(monkeypatch):
    events = []
    module = SimpleNamespace(
        nvmlInit=lambda: events.append('init'), nvmlShutdown=lambda: events.append('shutdown'),
        nvmlDeviceGetCount=lambda: 2,
        nvmlDeviceGetHandleByIndex=lambda index: events.append(index) or index,
        nvmlDeviceGetUUID=lambda handle: f'GPU-{handle}'.encode(),
        nvmlDeviceGetMemoryInfo=lambda handle: SimpleNamespace(total=16*1024**3, used=handle*1024**3, free=(16-handle)*1024**3),
        nvmlDeviceGetUtilizationRates=lambda handle: SimpleNamespace(gpu=handle*10),
    )
    monkeypatch.setitem(sys.modules, 'pynvml', module)
    monkeypatch.setitem(sys.modules, 'psutil', SimpleNamespace(virtual_memory=lambda: SimpleNamespace(total=64*1024**3, available=32*1024**3)))
    return module, events


@pytest.mark.parametrize('index', [0, 1])
def test_topaz_observes_selected_card_on_two_card_system(nvml, index):
    with TopazResourceReader(index) as reader:
        row = reader.sample()
        assert row['gpu_uuid'] == f'GPU-{index}'
        assert reader.device_index == index
        assert row['gpu_used_bytes'] == index*1024**3
    assert nvml[1] == ['init', index, 'shutdown']


def test_dlss_single_card_gate_is_unchanged(nvml):
    with pytest.raises(RuntimeError, match='DLSS FI route is single-GPU'):
        with NvmlResourceReader():
            pytest.fail('DLSS gate was relaxed')
    assert nvml[1] == ['init', 'shutdown']


@pytest.mark.parametrize('index', [-1, True, '1', 16])
def test_topaz_index_validation_does_not_initialize_nvml(nvml, index):
    with pytest.raises(ValueError):
        TopazResourceReader(index)
    assert nvml[1] == []


def test_unavailable_index_shuts_down_nvml_without_reading_wrong_card(nvml):
    with pytest.raises(RuntimeError, match='unavailable'):
        with TopazResourceReader(2):
            pytest.fail('Unavailable card was substituted')
    assert nvml[1] == ['init', 'shutdown']
