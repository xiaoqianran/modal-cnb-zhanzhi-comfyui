"""CPU-only regression for issue #30; vendor probes are explicitly faked."""
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from h3_audio_t8_pkg import topaz_contract as contract, topaz_media as media, topaz_fi_worker as fi
from tests.test_topaz_contract import runtime  # noqa: F401
from tests.test_topaz_interpolation import prepare_fi
from tests.test_topaz_media import video
from tests.test_topaz_worker_dimensions import video_probe


@pytest.mark.parametrize(('codec', 'software', 'expected'), [
    ('h264', True, 'h264'), ('hevc', True, 'hevc'),
    ('h264', False, 'h264_cuvid'), ('hevc', False, 'hevc_cuvid'),
    ('ffv1', False, None),
])
def test_discovery_never_uses_implicit_qsv(runtime, monkeypatch, tmp_path, codec, software, expected):  # noqa: F811
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'fake')
    calls = []

    def external(command, *, stdout, stderr, timeout, **kwargs):
        calls.append(command)
        assert timeout == 30 and kwargs['shell'] is False
        if '-decoders' in command:
            names = ('h264', 'hevc') if software else ('h264_cuvid', 'hevc_cuvid')
            stdout.write(('\n'.join(' VFS..D ' + name + ' decoder' for name in names)).encode())
            return SimpleNamespace(returncode=0)
        selected = command[command.index('-codec:v') + 1]
        assert 'qsv' not in selected
        if selected.split('_')[0] != codec:
            stderr.write(b'Codec type or id mismatches')
            return SimpleNamespace(returncode=1)
        stdout.write(json.dumps({'streams': [{'codec_name': codec}]}).encode())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(media.subprocess, 'run', external)
    assert media.video_decoder(runtime, source, {}, tmp_path, 'source') == expected
    assert len(calls) <= 3


@pytest.mark.parametrize('failure', ['crash', 'gpu', 'corrupt', 'timeout', 'wrong_codec', 'missing_decoder'])
def test_discovery_errors_never_fall_back(runtime, monkeypatch, tmp_path, failure):  # noqa: F811
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'fake')
    calls = []

    def external(command, *, stdout, stderr, **kwargs):
        calls.append(command)
        if '-decoders' in command:
            if failure != 'missing_decoder':
                stdout.write(b' V..... h264_cuvid decoder\n V..... hevc_cuvid decoder\n')
            return SimpleNamespace(returncode=0)
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(command, 30)
        if failure == 'wrong_codec':
            stdout.write(b'{"streams":[{"codec_name":"ffv1"}]}')
            return SimpleNamespace(returncode=0)
        stderr.write(b'No CUDA capable device' if failure == 'gpu' else b'Invalid data')
        return SimpleNamespace(returncode=3221225477 if failure == 'crash' else 1)

    monkeypatch.setattr(media.subprocess, 'run', external)
    with pytest.raises((RuntimeError, subprocess.TimeoutExpired)):
        media.video_decoder(runtime, source, {}, tmp_path, 'source')
    assert len(calls) == (1 if failure == 'missing_decoder' else 2)


def test_input_flags_are_before_input_not_encoder(runtime, tmp_path):  # noqa: F811
    prepare_fi(runtime)
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'fake')
    commands = [
        contract.regular_command(runtime, source, tmp_path / 'up.mp4', 'iris-3', 512, 256, decoder='hevc_cuvid'),
        contract.interpolation_command(runtime, source, tmp_path / 'fi.mp4', 'apo-8', 48, decoder='hevc_cuvid'),
    ]
    for command in commands:
        assert command.index('-codec:v') < command.index('-i') < command.index('-c:v')
        assert command[command.index('-codec:v') + 1] == 'hevc_cuvid'
        assert command[command.index('-c:v') + 1] == 'h264_nvenc'
    for packets in (False, True):
        command = media.probe_command(runtime, source, frames=not packets, packets=packets, decoder='hevc_cuvid')
        assert command[command.index('-codec:v') + 1] == 'hevc_cuvid'
    assert contract.decoder_options(None) == []
    with pytest.raises(ValueError, match='decoder'):
        contract.decoder_options('h264_qsv')


def test_complete_decoded_frame_formats_fix_cuvid_main10_not_bad_frames():
    probe = video(pix_fmt='nv12', bits=10)
    for frame in probe['frames']:
        frame['pix_fmt'] = 'p010le'
    assert media.analyze_video(probe, allowed_bit_depths=(10,))['bit_depth'] == 10
    for malformed in ('mixed', 'incomplete', 'wrong_bits', 'vfr'):
        broken = deepcopy(probe)
        if malformed == 'mixed':
            broken['frames'][0]['pix_fmt'] = 'nv12'
        elif malformed == 'incomplete':
            broken['frames'][0].pop('pix_fmt')
        elif malformed == 'wrong_bits':
            broken['streams'][0]['bits_per_raw_sample'] = '8'
        else:
            broken['frames'][2]['best_effort_timestamp'] += 100
        with pytest.raises(ValueError):
            media.analyze_video(broken, allowed_bit_depths=(10,))


def test_audio_only_pcm_command_also_pins_video_decoder(runtime, monkeypatch, tmp_path):  # noqa: F811
    calls = []
    def popen(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=io.BytesIO(b'\0' * 32), wait=lambda **kw: 0, poll=lambda: 0)
    monkeypatch.setattr(media.subprocess, 'Popen', popen)
    probe = {'streams': [{'codec_type': 'audio', 'index': 1}]}
    result = media.decoded_pcm_digests(runtime, tmp_path / 'source.mp4', probe, {},
        tmp_path / 'pcm.stderr', decoder='hevc_cuvid')
    assert result[0]['bytes'] == 32
    assert calls[0].index('-codec:v') < calls[0].index('-i')
    assert calls[0][calls[0].index('-map') + 1] == '0:1'


def test_interpolation_worker_pins_source_and_output_through_all_reads(runtime, monkeypatch, tmp_path):  # noqa: F811
    prepare_fi(runtime)
    source, job = tmp_path / 'source.mp4', tmp_path / 'job'
    source.write_bytes(b'fake')
    job.mkdir()
    request = job / 'request.json'
    spec = {'install': str(runtime.install), 'definitions': str(runtime.definitions), 'data': str(runtime.data),
        'job': str(job), 'source': media.file_identity(source), 'installation': {'executables': []},
        'model': {'definition': media.file_identity(runtime.definitions / 'apo-8.json'), 'candidate_weights': []},
        'settings': {'model_id': 'apo-8', 'multiplier': 2, 'device': 1, 'vram': .8, 'duplicate_threshold': .01}}
    request.write_text(json.dumps(spec))
    monkeypatch.setattr(fi.sys, 'argv', ['worker', str(request)])
    monkeypatch.setattr(fi, 'local_module', lambda name: {'topaz_contract': contract, 'topaz_media': media}[name])
    pcm = []
    def pcm_decode(*args, decoder):
        pcm.append(decoder)
        return []
    monkeypatch.setattr(media, 'decoded_pcm_digests', pcm_decode)
    calls = []
    def external(command, *, stdout, stderr, **kwargs):
        calls.append(command)
        if '-decoders' in command:
            stdout.write(b' V..... h264_cuvid decoder\n V..... hevc_cuvid decoder\n')
        elif 'stream=codec_name' in command:
            stdout.write(b'{"streams":[{"codec_name":"h264"}]}')
        elif '-show_frames' in command:
            original = command[-1] == str(source)
            probe = video_probe(512, 256)
            if not original:
                probe['streams'][0]['r_frame_rate'] = '48/1'
                probe['frames'] = [{'width': 512, 'height': 256, 'best_effort_timestamp': i * 256} for i in range(4)]
            stdout.write(json.dumps(probe).encode())
        elif '-show_packets' in command:
            stdout.write(b'{"streams":[],"packets":[]}')
        elif '-h' in command:
            stdout.write(b'Encoder h264_nvenc [NVIDIA]:')
        elif '-vf' in command:
            Path(command[-1]).write_bytes(b'fake-output')
            assert 'device=1' in command[command.index('-vf') + 1]
        elif '-xerror' not in command:
            pytest.fail(f'Unexpected command: {command}')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(fi.subprocess, 'run', external)
    fi.main()
    assert (job / 'enhanced.mp4').exists()
    assert pcm == ['h264_cuvid', 'h264_cuvid']
    for command in calls:
        if '-i' in command or '-show_frames' in command or '-show_packets' in command:
            assert command[command.index('-codec:v') + 1] == 'h264_cuvid'
    assert json.loads((job / 'result.json').read_text())['input_decoders']['output'] == 'h264_cuvid'
