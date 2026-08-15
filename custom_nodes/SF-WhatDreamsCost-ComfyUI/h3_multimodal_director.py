import json
import logging
import math
import os
import re
import secrets
import time
from pathlib import Path

import av
import numpy as np
import torch
from PIL import Image
from aiohttp import web

import folder_paths
from comfy_api.latest import io
from comfy_extras.nodes_minimax_h3 import (
    MiniMaxH3ReferenceToVideo,
    adapt_canvas,
)
from server import PromptServer


log = logging.getLogger(__name__)

FPS = 24.0
UPLOAD_SUBFOLDER = "sf_h3_director"
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
MAX_UPLOAD_BYTES = {
    "image": 30 * 1024 * 1024,
    "video": 50 * 1024 * 1024,
    "audio": 15 * 1024 * 1024,
}


def _input_root() -> Path:
    return Path(folder_paths.get_input_directory()).resolve()


def _upload_root() -> Path:
    root = (_input_root() / UPLOAD_SUBFOLDER).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_media_path(relative_name: str) -> Path:
    if not relative_name:
        raise ValueError("参考素材缺少文件名。")
    candidate = (_input_root() / str(relative_name).replace("\\", "/")).resolve()
    if os.path.commonpath([str(_input_root()), str(candidate)]) != str(_input_root()):
        raise ValueError("参考素材路径超出 ComfyUI 输入目录。")
    if not candidate.is_file():
        raise FileNotFoundError(f"找不到参考素材：{relative_name}")
    return candidate


def _media_kind(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in ALLOWED_IMAGE_EXTENSIONS:
        return "image"
    if ext in ALLOWED_VIDEO_EXTENSIONS:
        return "video"
    if ext in ALLOWED_AUDIO_EXTENSIONS:
        return "audio"
    raise ValueError(f"不支持的素材格式：{ext or '未知'}")


def _probe_media(path: Path, kind: str) -> dict:
    info = {"kind": kind, "width": 0, "height": 0, "duration": 0.0, "has_audio": False}
    if kind == "image":
        with Image.open(path) as image:
            info["width"], info["height"] = image.size
        return info

    with av.open(str(path)) as container:
        if kind == "video" and container.streams.video:
            stream = container.streams.video[0]
            info["width"] = int(stream.width or 0)
            info["height"] = int(stream.height or 0)
            if stream.duration is not None and stream.time_base is not None:
                info["duration"] = float(stream.duration * stream.time_base)
            elif container.duration is not None:
                info["duration"] = float(container.duration / av.time_base)
            info["has_audio"] = bool(container.streams.audio)
        elif kind == "audio" and container.streams.audio:
            stream = container.streams.audio[0]
            if stream.duration is not None and stream.time_base is not None:
                info["duration"] = float(stream.duration * stream.time_base)
            elif container.duration is not None:
                info["duration"] = float(container.duration / av.time_base)
    return info


@PromptServer.instance.routes.post("/sf_h3_director/upload")
async def upload_h3_reference(request):
    reader = await request.multipart()
    field = await reader.next()
    while field is not None and field.name != "file":
        field = await reader.next()
    if field is None or not field.filename:
        return web.json_response({"error": "没有收到素材文件。"}, status=400)

    original_name = os.path.basename(field.filename)
    try:
        kind = _media_kind(original_name)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)

    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original_name).stem).strip("._") or "media"
    ext = Path(original_name).suffix.lower()
    stored_name = f"{int(time.time() * 1000)}_{secrets.token_hex(3)}_{safe_stem}{ext}"
    target = _upload_root() / stored_name
    total = 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = await field.read_chunk(size=1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES[kind]:
                    limit_mb = MAX_UPLOAD_BYTES[kind] // (1024 * 1024)
                    raise ValueError(f"单个{ {'image': '图片', 'video': '视频', 'audio': '音频'}[kind] }不能超过 {limit_mb}MB。")
                output.write(chunk)
        info = _probe_media(target, kind)
        if kind in ("video", "audio"):
            _validate_reference_duration(info["duration"], original_name, kind)
    except Exception as exc:
        if target.exists():
            target.unlink(missing_ok=True)
        return web.json_response({"error": str(exc)}, status=400)

    relative_name = f"{UPLOAD_SUBFOLDER}/{stored_name}"
    return web.json_response(
        {
            "name": relative_name,
            "original_name": original_name,
            "size": total,
            **info,
        }
    )


def _load_image(path: Path) -> torch.Tensor:
    with Image.open(path) as image:
        array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def _load_video(path: Path) -> torch.Tensor:
    frames = []
    with av.open(str(path)) as container:
        if not container.streams.video:
            raise ValueError(f"视频没有画面轨道：{path.name}")
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        canvas_w, canvas_h = adapt_canvas(int(stream.width), int(stream.height))
        source_rate = float(stream.average_rate) if stream.average_rate else FPS
        previous = None
        previous_time = 0.0
        next_time = 0.0
        decoded_index = 0
        for frame in container.decode(stream):
            frame_time = frame.time
            if frame_time is None:
                frame_time = decoded_index / max(source_rate, 1.0)
            decoded_index += 1
            if frame_time > 15.05:
                break
            current = frame.reformat(width=canvas_w, height=canvas_h, format="rgb24").to_ndarray()
            if previous is None:
                previous = current
                previous_time = float(frame_time)
            while next_time <= float(frame_time) + 1e-6 and len(frames) < int(15 * FPS):
                use_current = abs(float(frame_time) - next_time) <= abs(previous_time - next_time)
                frames.append(current if use_current else previous)
                next_time += 1.0 / FPS
            previous = current
            previous_time = float(frame_time)
    if not frames:
        raise ValueError(f"无法解码参考视频：{path.name}")
    array = np.stack(frames).astype(np.float32) / 255.0
    return torch.from_numpy(array)


def _load_audio(path: Path) -> dict:
    chunks = []
    sample_rate = 32000
    with av.open(str(path)) as container:
        if not container.streams.audio:
            raise ValueError(f"素材没有音频轨道：{path.name}")
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=sample_rate)
        for frame in container.decode(stream):
            for converted in resampler.resample(frame):
                chunks.append(torch.from_numpy(converted.to_ndarray().copy()))
        for converted in resampler.resample(None):
            chunks.append(torch.from_numpy(converted.to_ndarray().copy()))
    if not chunks:
        raise ValueError(f"无法解码参考音频：{path.name}")
    waveform = torch.cat(chunks, dim=-1).float()
    return {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}


def _grid_dims(layout: str) -> tuple[int, int]:
    match = re.search(r"(\d+)\s*x\s*(\d+)", str(layout or ""), re.I)
    if match:
        return max(1, int(match.group(1))), max(1, int(match.group(2)))
    return 3, 2


def _split_storyboard(images: torch.Tensor | None, layout: str, crop_strength: float) -> list[torch.Tensor]:
    if images is None:
        return []
    cols, rows = _grid_dims(layout)
    count = cols * rows
    if int(images.shape[0]) > 1:
        return [images[index : index + 1] for index in range(min(count, int(images.shape[0])))]

    source = images[:1]
    _, height, width, _ = source.shape
    strength = max(0.0, min(3.0, float(crop_strength)))
    result = []
    for index in range(count):
        col = index % cols
        row = index // cols
        x0 = int(round(col * width / cols))
        x1 = int(round((col + 1) * width / cols))
        y0 = int(round(row * height / rows))
        y1 = int(round((row + 1) * height / rows))
        inset_x = int(round((x1 - x0) * 0.012 * strength))
        inset_y = int(round((y1 - y0) * 0.012 * strength))
        if x1 - x0 > inset_x * 2 + 16:
            x0, x1 = x0 + inset_x, x1 - inset_x
        if y1 - y0 > inset_y * 2 + 16:
            y0, y1 = y0 + inset_y, y1 - inset_y
        result.append(source[:, y0:y1, x0:x1, :])
    return result


def _save_storyboard_previews(cells: list[torch.Tensor]) -> list[dict]:
    if not cells:
        return []
    preview_dir = Path(folder_paths.get_temp_directory()) / UPLOAD_SUBFOLDER
    preview_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{int(time.time() * 1000)}_{secrets.token_hex(3)}"
    previews = []
    try:
        for index, cell in enumerate(cells):
            array = cell[0].detach().float().clamp(0, 1).mul(255).byte().cpu().numpy()
            image = Image.fromarray(array, mode="RGB")
            image.thumbnail((640, 640), Image.Resampling.LANCZOS)
            filename = f"grid_{run_id}_{index + 1}.jpg"
            image.save(preview_dir / filename, "JPEG", quality=86, optimize=True)
            previews.append({"filename": filename, "subfolder": UPLOAD_SUBFOLDER, "type": "temp"})
    except Exception as exc:
        log.warning("无法生成 H3 宫格预览：%s", exc)
        return []
    return previews


def _parse_storyboard_text(text: str) -> list[str]:
    clean = str(text or "").strip()
    if not clean:
        return []
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.I)
    try:
        value = json.loads(clean)
        if isinstance(value, dict):
            for key in ("segments", "shots", "scenes", "storyboard", "分镜", "镜头"):
                if isinstance(value.get(key), list):
                    value = value[key]
                    break
        if isinstance(value, list):
            result = []
            for item in value:
                if isinstance(item, str):
                    result.append(item.strip())
                elif isinstance(item, dict):
                    result.append(str(item.get("prompt") or item.get("text") or item.get("description") or "").strip())
            return [item for item in result if item]
    except Exception:
        pass
    marker = re.compile(r"(?:^|\n)\s*(?:分镜|镜头|画面|shot)\s*[一二三四五六七八九十\d]+\s*[:：.、-]?\s*", re.I)
    matches = list(marker.finditer(clean))
    if matches:
        result = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(clean)
            result.append(clean[match.end() : end].strip())
        return [item for item in result if item]
    return [part.strip() for part in re.split(r"\n\s*\n|\n", clean) if part.strip()]


# --- SF 增强：宫格分镜文本识别（第X个镜头锚点 + 方位词→格位 + X秒时长 + 正面词标签剥离）---
# 方位词 -> grid_index（按布局，行优先：从左到右、从上到下），与宫格切图顺序严格对应，
# 4/6/9 宫格一致；与 LTX 导演台（ltx_director.py）使用同一套映射，避免两个节点行为分裂。
_GRID_POSITION_MAPS = {
    (2, 2): {
        "左上": 0, "上左": 0, "右上": 1, "上右": 1,
        "左下": 2, "下左": 2, "右下": 3, "下右": 3,
    },
    (3, 2): {
        "左上": 0, "上左": 0, "中上": 1, "上中": 1, "右上": 2, "上右": 2,
        "左下": 3, "下左": 3, "中下": 4, "下中": 4, "右下": 5, "下右": 5,
    },
    (3, 3): {
        "左上": 0, "上左": 0, "中上": 1, "上中": 1, "右上": 2, "上右": 2,
        "左中": 3, "中左": 3, "中中": 4, "中心": 4, "正中": 4, "中间": 4, "中央": 4, "居中": 4,
        "右中": 5, "中右": 5, "左下": 6, "下左": 6, "中下": 7, "下中": 7, "右下": 8, "下右": 8,
    },
}
_GRID_POSITION_WORDS = sorted(
    {w for m in _GRID_POSITION_MAPS.values() for w in m}, key=len, reverse=True
)


def _position_to_index(word: str | None, cols: int, rows: int):
    if not word:
        return None
    mp = _GRID_POSITION_MAPS.get((cols, rows)) or _GRID_POSITION_MAPS[(2, 2)]
    idx = mp.get(word)
    if idx is None or not (0 <= idx < cols * rows):
        return None
    return idx


def _strip_global_label(text: str) -> str:
    # 去掉 "正面词：" / "全局提示词：" / "视频提示词：" 等引导标签，只保留真正的全局内容
    t = re.sub(
        r"^\s*(?:正面词|正面|全局提示词|全局词|全局|总提示词|总词|总览词|概述|总览|视频提示词|视频词)\s*[:：]\s*",
        "", text or "", flags=re.I,
    )
    return t.strip()


def _parse_segment_body(body: str, cols: int, rows: int) -> dict:
    b = body or ""
    position = None
    for word in _GRID_POSITION_WORDS:
        if word in b:
            idx = _position_to_index(word, cols, rows)
            if idx is not None:
                position = idx
                break
    dur = None
    # 不能用 \b：\b 是 ASCII 边界，中文"秒"不算单词字符，会导致 "3秒，" 匹配失败；
    # 用否定前瞻 (?![0-9a-zA-Z]) 保证单位后不紧跟字母/数字即可。
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:秒钟|秒|s)(?![0-9a-zA-Z])", b, flags=re.I)
    if m:
        dur = float(m.group(1))
    prompt = b
    # 剔除方位词（已用于格位映射）与时长"X秒"（已驱动时间线，内联冗余）；保留景别
    for word in _GRID_POSITION_WORDS:
        prompt = prompt.replace(word, "")
    prompt = re.sub(r"\d+(?:\.\d+)?\s*(?:秒钟|秒|s)(?![0-9a-zA-Z])", "", prompt, flags=re.I)
    # 折叠被剔除词留下的连续标点，避免"中景，，李强"
    prompt = re.sub(r"[，,。、；;：:\s]+", "，", prompt)
    prompt = re.sub(r"^，+|，+$", "", prompt)
    prompt = re.sub(r"\s+", " ", prompt).strip()
    return {"prompt": prompt, "position": position, "duration_seconds": dur}


def _recognize_storyboard(text: str, cols: int, rows: int):
    """SF 增强识别宫格分镜文本。

    返回 (global_prompt, cells, durations, recognized)：
    - cells/durations 长度 = cols*rows，按格位对齐（空格为 ""/None）；
    - 识别到方位的段落落到对应格，未识别/冲突的顺次补空位（行优先），与切图顺序一致；
    - 没有 "第X个镜头" 锚点时 recognized=False，调用方回退到 _parse_storyboard_text。
    """
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text or "").strip(), flags=re.I)
    if not clean:
        return "", [], [], False
    anchor_re = re.compile(
        r"第\s*([0-9]+|[一二三四五六七八九十]+)\s*个?\s*(?:镜头|镜|画面|分镜|shot)", re.I
    )
    anchors = list(anchor_re.finditer(clean))
    if not anchors:
        return "", [], [], False

    global_prompt = _strip_global_label(clean[: anchors[0].start()])
    count = cols * rows
    placed, queue = {}, []
    for i, a in enumerate(anchors):
        start = a.end()
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(clean)
        seg = _parse_segment_body(clean[start:end], cols, rows)
        pos = seg["position"]
        if pos is not None and pos not in placed:
            placed[pos] = seg
        else:
            queue.append(seg)
    cells = [""] * count
    durations = [None] * count
    for idx in range(count):
        if idx in placed:
            cells[idx] = placed[idx]["prompt"]
            durations[idx] = placed[idx]["duration_seconds"]
    qi = 0
    for idx in range(count):
        if not cells[idx] and qi < len(queue):
            cells[idx] = queue[qi]["prompt"]
            durations[idx] = queue[qi]["duration_seconds"]
            qi += 1
    if qi < len(queue):
        log.warning("SF-H3: 分镜文本有 %d 段超出 %d 宫格，超出部分已忽略。", len(queue) - qi, count)
    return global_prompt, cells, durations, True


def _h3_text_signature(text: str, cols: int, rows: int) -> str:
    """与前端 h3TextSig 完全一致的签名：`djb2(text)@colsxrows`（djb2 按 UTF-16 码元）。

    前端从接口同步分镜后把该签名写进 timeline_data 的 `_textSig`；
    后端执行时重算签名：不一致说明 storyboard_text 已更新（典型：万象回填了新文本，
    而工作流里保存的 timeline_data 还是上一会话的旧内容），此时一切以当前文本为准，
    避免"视频提示词传不进去"（旧时间线内容架空新文本）。
    """
    h = 5381
    data = (text or "").encode("utf-16-le", "surrogatepass")
    for i in range(0, len(data) - 1, 2):
        h = ((h * 33) + (data[i] | (data[i + 1] << 8))) & 0xFFFFFFFF
    return f"{format(h, 'x')}@{cols}x{rows}"


def _align_frame_count(seconds: float) -> int:
    frames = max(5, int(round(max(4.0, min(15.0, float(seconds))) * FPS)))
    while frames % 17 != 5:
        frames += 1
    return frames


ASPECT_RATIOS = {
    "21:9 超宽屏": 21 / 9,
    "16:9 横屏": 16 / 9,
    "4:3 横屏": 4 / 3,
    "1:1 方形": 1.0,
    "3:4 竖屏": 3 / 4,
    "9:16 竖屏": 9 / 16,
}


def _canvas_size(
    aspect_name: str,
    first_visual: torch.Tensor | None,
    megapixels: float,
    multiple: int,
) -> tuple[int, int]:
    ratio = ASPECT_RATIOS.get(aspect_name)
    if ratio is None and first_visual is not None:
        ratio = float(first_visual.shape[2]) / max(1.0, float(first_visual.shape[1]))
    ratio = ratio or (16 / 9)
    megapixels = max(0.1, min(16.0, float(megapixels)))
    multiple = max(8, min(128, int(multiple)))
    total_pixels = megapixels * 1024 * 1024
    width = max(multiple, round(math.sqrt(total_pixels * ratio) / multiple) * multiple)
    height = max(multiple, round(math.sqrt(total_pixels / ratio) / multiple) * multiple)
    return width, height


def _timeline_items(raw: str) -> tuple[dict, list[dict]]:
    try:
        data = json.loads(raw) if raw else {}
    except Exception as exc:
        raise ValueError(f"导演台时间线数据损坏：{exc}") from exc
    if not isinstance(data, dict):
        data = {}
    items = data.get("items") or []
    return data, [item for item in items if isinstance(item, dict)]


def _duration_of_audio(audio: dict) -> float:
    waveform = audio.get("waveform")
    rate = float(audio.get("sample_rate") or 1)
    return float(waveform.shape[-1]) / rate if waveform is not None else 0.0


def _validate_reference_duration(duration: float, name: str, kind: str) -> None:
    label = "视频" if kind == "video" else "音频"
    if duration < 1.99:
        raise ValueError(f"参考{label}“{name}”只有 {duration:.2f} 秒，H3 要求单个素材至少 2 秒。")
    if duration > 15.01:
        raise ValueError(f"参考{label}“{name}”为 {duration:.2f} 秒，超过 H3 的 15 秒上限。")


def _compile_prompt(global_prompt: str, items: list[dict], tag_by_id: dict[str, str], actual_seconds: float,
                    storyboard_prompts: list[str], storyboard_count: int,
                    storyboard_durations: list | None = None) -> str:
    parts = []
    base = str(global_prompt or "").strip()
    if base:
        parts.append(base)

    reference_lines = []
    for item in items:
        if item.get("source") == "storyboard":
            continue
        tag = tag_by_id.get(str(item.get("id", "")))
        if tag:
            label = str(item.get("name") or item.get("originalName") or item.get("kind") or "参考素材")
            reference_lines.append(f"{tag}：{label}")
        audio_tag = tag_by_id.get(f"{item.get('id', '')}:audio")
        if audio_tag:
            reference_lines.append(f"{audio_tag}：{label}的原始声音")
    for index in range(storyboard_count):
        tag = tag_by_id.get(f"storyboard_{index}")
        if tag:
            reference_lines.append(f"{tag}：第{index + 1}张宫格分镜图")
    socket_labels = {
        "socket_image_": "接口参考图片",
        "socket_video_": "接口参考视频",
        "socket_audio_": "接口参考音频",
    }
    for item_id, tag in tag_by_id.items():
        if item_id.endswith(":audio"):
            continue
        for prefix, label in socket_labels.items():
            if item_id.startswith(prefix):
                number = int(item_id.rsplit("_", 1)[-1]) + 1
                reference_lines.append(f"{tag}：{label}{number}")
                paired_tag = tag_by_id.get(f"{item_id}:audio")
                if paired_tag:
                    reference_lines.append(f"{paired_tag}：接口参考视频{number}的原始声音")
                break
    if reference_lines:
        parts.append("参考素材对应关系：\n" + "\n".join(reference_lines))

    visual_items = [
        item for item in items
        if item.get("kind") in ("image", "video") and item.get("source") != "storyboard"
    ]
    timeline_lines = []
    for item in sorted(visual_items, key=lambda value: float(value.get("start", 0) or 0)):
        start = max(0.0, float(item.get("start", 0) or 0))
        duration = max(0.1, float(item.get("duration", 1) or 1))
        end = min(actual_seconds, start + duration)
        prompt = str(item.get("prompt") or "").strip()
        sound = str(item.get("sound") or "").strip()
        item_id = str(item.get("id", ""))
        tag = tag_by_id.get(item_id, "")
        audio_tag = tag_by_id.get(f"{item_id}:audio", "")
        references = " ".join(part for part in (tag, audio_tag) if part)
        description = " ".join(part for part in (references, prompt) if part).strip() or "保持参考素材的主体与场景连续。"
        if sound:
            description += f" 声音：{sound}"
        timeline_lines.append(f"[{start:.2f}秒-{end:.2f}秒] {description}")

    storyboard_items = {
        int(item.get("gridIndex", index)): item
        for index, item in enumerate(items)
        if item.get("source") == "storyboard"
    }
    if storyboard_count and (storyboard_prompts or storyboard_items):
        segment = actual_seconds / max(1, storyboard_count)
        # SF：文本中识别到 X秒 时，按识别时长的占比分配各格起止（等比缩放到实际总时长，
        # 适配 H3 的 4-15 秒上限）；未识别时长时保持原逻辑，尊重前端时间线的手动调整。
        text_timing = None
        if storyboard_durations and any(storyboard_durations):
            weights = []
            for i in range(storyboard_count):
                d = storyboard_durations[i] if i < len(storyboard_durations) else None
                weights.append(float(d) if d else 0.0)
            known = [w for w in weights if w > 0]
            avg = sum(known) / len(known) if known else 1.0
            weights = [w if w > 0 else avg for w in weights]
            scale = actual_seconds / sum(weights)
            text_timing = []
            cur = 0.0
            for w in weights:
                text_timing.append((cur, max(0.1, w * scale)))
                cur += w * scale
        for index in range(storyboard_count):
            item = storyboard_items.get(index, {})
            if text_timing is not None:
                start, duration = text_timing[index]
                end = min(actual_seconds, start + duration)
            else:
                start = max(0.0, float(item.get("start", segment * index) or 0))
                duration = max(0.1, float(item.get("duration", segment) or segment))
                end = min(actual_seconds, start + duration)
            tag = tag_by_id.get(f"storyboard_{index}", "")
            parsed_prompt = storyboard_prompts[index] if index < len(storyboard_prompts) else ""
            item_prompt = str(item.get("prompt") or "").strip()
            description = item_prompt or parsed_prompt or "保持该分镜的主体、动作和场景连续。"
            sound = str(item.get("sound") or "").strip()
            if sound:
                description += f" 声音：{sound}"
            timeline_lines.append(f"[{start:.2f}秒-{end:.2f}秒] {tag} {description}".strip())

    if timeline_lines:
        parts.append("时间线：\n" + "\n".join(timeline_lines))

    audio_lines = []
    for item in items:
        if item.get("kind") == "audio":
            tag = tag_by_id.get(str(item.get("id", "")), "")
            instruction = str(item.get("prompt") or item.get("sound") or "参考其音色、节奏或声音氛围").strip()
            audio_lines.append(f"{tag}：{instruction}".strip("："))
    if audio_lines:
        parts.append("声音参考：\n" + "\n".join(audio_lines))

    if not parts:
        parts.append("根据参考素材生成自然连贯的视频，保持人物、场景、动作和声音的一致性。")
    prompt = "\n\n".join(parts).strip()
    if len(prompt) > 7000:
        raise ValueError(f"编译后的提示词为 {len(prompt)} 个字符，超过 H3 的 7000 字符上限。")
    return prompt


def _compile_reference_prompt(reference_prompt: str, items: list[dict], tag_by_id: dict[str, str]) -> str:
    compiled = str(reference_prompt or "").strip()
    counters = {"image": 0, "video": 0, "audio": 0}
    labels = {"image": "图片", "video": "视频", "audio": "音频"}
    reference_lines = []

    for item in items:
        kind = str(item.get("kind") or "")
        if kind not in counters:
            continue
        counters[kind] += 1
        token = f"@{labels[kind]}{counters[kind]}"
        item_id = str(item.get("id") or "")
        tag = tag_by_id.get(item_id)
        if not tag:
            continue
        compiled = re.sub(rf"{re.escape(token)}(?!\d)", tag, compiled)
        name = str(item.get("name") or item.get("originalName") or token)
        reference_lines.append(f"{tag}：{name}")
        paired_audio_tag = tag_by_id.get(f"{item_id}:audio")
        if paired_audio_tag:
            reference_lines.append(f"{paired_audio_tag}：{name}的原始声音")

    unresolved = re.findall(r"@(图片|视频|音频)\s*(\d+)", compiled)
    if unresolved:
        tokens = "、".join(dict.fromkeys(f"@{kind}{number}" for kind, number in unresolved))
        raise ValueError(f"全能参考提示词引用了不存在的素材：{tokens}。请重新点击素材卡片插入引用。")

    socket_labels = {
        "socket_image_": "接口参考图片",
        "socket_video_": "接口参考视频",
        "socket_audio_": "接口参考音频",
    }
    for item_id, tag in tag_by_id.items():
        if item_id.endswith(":audio"):
            continue
        for prefix, label in socket_labels.items():
            if item_id.startswith(prefix):
                number = int(item_id.rsplit("_", 1)[-1]) + 1
                reference_lines.append(f"{tag}：{label}{number}")
                paired_audio_tag = tag_by_id.get(f"{item_id}:audio")
                if paired_audio_tag:
                    reference_lines.append(f"{paired_audio_tag}：{label}{number}的原始声音")
                break

    if not compiled:
        tags = [tag for item_id, tag in tag_by_id.items() if not item_id.endswith(":audio")]
        compiled = " ".join(tags) + " 根据所有参考素材生成自然连贯的视频，保持主体、动作、场景和声音一致。"
        compiled = compiled.strip()
    if reference_lines:
        compiled += "\n\n参考素材对应关系：\n" + "\n".join(reference_lines)
    if len(compiled) > 7000:
        raise ValueError(f"编译后的提示词为 {len(compiled)} 个字符，超过 H3 的 7000 字符上限。")
    return compiled


class SFH3MultimodalDirector(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SFH3MultimodalDirector",
            display_name="SF-H3 多模态参考导演台",
            category="SF-H3",
            description=(
                "H3 宫格分镜与全能参考导演台，支持图片、视频、音频和四/六/九宫格。"
                "SF 增强：宫格分镜文本支持『正面词：』标签剥离、『第X个镜头』锚点、"
                "方位词（左上/中上/中心/…）严格落格、『X秒』按占比分配各格时长。"
            ),
            inputs=[
                io.Model.Input("model", display_name="模型"),
                io.Clip.Input("clip", display_name="H3 文本编码器"),
                io.Vae.Input("video_vae", display_name="H3 视频 VAE"),
                io.Vae.Input("audio_vae", display_name="H3 音频 VAE"),
                io.Combo.Input(
                    "mode",
                    display_name="导演模式",
                    options=["宫格模式", "全能参考"],
                    default="宫格模式",
                ),
                io.Float.Input("duration_seconds", display_name="目标时长（秒）", default=5.0, min=4.0, max=15.0, step=0.1),
                io.Combo.Input(
                    "aspect_ratio",
                    display_name="输出比例",
                    options=["自动"] + list(ASPECT_RATIOS.keys()),
                    default="自动",
                ),
                io.Combo.Input(
                    "ref_image_size",
                    display_name="参考图精度",
                    options=["匹配输出（推荐）", "最高保真（更慢）"],
                    default="匹配输出（推荐）",
                ),
                io.String.Input("global_prompt", display_name="全局创作要求", multiline=True, default="", optional=True),
                io.String.Input("timeline_data", display_name="导演台数据", multiline=True, default="{}"),
                io.String.Input("storyboard_text", display_name="宫格分镜文本", multiline=True, force_input=True, optional=True),
                io.Combo.Input(
                    "grid_layout",
                    display_name="宫格格式",
                    options=["2x2 四宫格", "3x2 六宫格", "3x3 九宫格"],
                    default="3x2 六宫格",
                ),
                io.Float.Input("grid_border_crop", display_name="白边裁剪强度", default=1.0, min=0.0, max=3.0, step=0.05),
                io.Image.Input("storyboard_images", display_name="宫格图像/分镜批次", optional=True),
                io.Image.Input("reference_images", display_name="附加参考图片批次", optional=True),
                io.Image.Input("reference_video_1", display_name="参考视频 1", optional=True),
                io.Image.Input("reference_video_2", display_name="参考视频 2", optional=True),
                io.Image.Input("reference_video_3", display_name="参考视频 3", optional=True),
                io.Audio.Input("reference_video_audio_1", display_name="参考视频音轨 1", optional=True),
                io.Audio.Input("reference_video_audio_2", display_name="参考视频音轨 2", optional=True),
                io.Audio.Input("reference_video_audio_3", display_name="参考视频音轨 3", optional=True),
                io.Audio.Input("reference_audio_1", display_name="参考音频 1", optional=True),
                io.Audio.Input("reference_audio_2", display_name="参考音频 2", optional=True),
                io.Audio.Input("reference_audio_3", display_name="参考音频 3", optional=True),
                io.Float.Input(
                    "output_megapixels",
                    display_name="输出像素规模（MP）",
                    default=0.4,
                    min=0.1,
                    max=16.0,
                    step=0.1,
                    tooltip="按目标百万像素计算输出宽高；与原 Resolution Selector 的 megapixels 一致。",
                ),
                io.Int.Input(
                    "resolution_multiple",
                    display_name="尺寸对齐倍数",
                    default=32,
                    min=8,
                    max=128,
                    step=4,
                    tooltip="输出宽高对齐倍数；MiniMax H3 推荐保持 32。",
                ),
            ],
            outputs=[
                io.Model.Output(display_name="模型"),
                io.Conditioning.Output(display_name="正向条件"),
                io.Latent.Output(display_name="音视频潜空间"),
                io.String.Output(display_name="编译提示词"),
                io.Int.Output(display_name="帧数"),
                io.Float.Output(display_name="帧率"),
                io.Int.Output(display_name="输出宽度"),
                io.Int.Output(display_name="输出高度"),
            ],
        )

    @classmethod
    def execute(
        cls,
        model,
        clip,
        video_vae,
        audio_vae,
        mode,
        duration_seconds,
        aspect_ratio,
        ref_image_size,
        global_prompt="",
        timeline_data="{}",
        storyboard_text="",
        grid_layout="3x2 六宫格",
        grid_border_crop=1.0,
        storyboard_images=None,
        reference_images=None,
        reference_video_1=None,
        reference_video_2=None,
        reference_video_3=None,
        reference_video_audio_1=None,
        reference_video_audio_2=None,
        reference_video_audio_3=None,
        reference_audio_1=None,
        reference_audio_2=None,
        reference_audio_3=None,
        output_megapixels=0.4,
        resolution_multiple=32,
    ) -> io.NodeOutput:
        mode = "全能参考" if mode == "全能参考" else "宫格模式"
        data, items = _timeline_items(timeline_data)
        global_prompt = str(global_prompt or data.get("globalPrompt") or "").strip()
        reference_prompt = str(data.get("allReferencePrompt") or "").strip()
        frame_count = _align_frame_count(duration_seconds)
        actual_seconds = frame_count / FPS

        grid_mode = mode == "宫格模式"
        active_items = [
            item for item in items
            if (item.get("source") == "storyboard") == grid_mode
        ]
        storyboard_prompts = []
        storyboard_durations = []
        effective_durations = []
        if grid_mode:
            g_cols, g_rows = _grid_dims(grid_layout)
            # SF 增强识别：第X个镜头 + 方位词落格 + X秒时长 + 正面词标签剥离；
            # 无锚点（非该格式脚本）时回退到原版解析，行为与上游一致。
            text_global, sb_cells, storyboard_durations, sb_recognized = _recognize_storyboard(
                storyboard_text, g_cols, g_rows
            )
            if sb_recognized:
                storyboard_prompts = sb_cells
                sig = _h3_text_signature(storyboard_text, g_cols, g_rows)
                if str(data.get("_textSig") or "") != sig:
                    # 文本已更新（万象回填/换了文本节点），而 timeline_data 还是旧会话内容：
                    # 一切以当前文本为准——清空时间线残留的旧分镜提示词（让识别结果生效），
                    # 全局提示词也以文本为准，时长按文本识别占比分配。
                    if text_global:
                        global_prompt = text_global
                    for item in active_items:
                        if item.get("source") == "storyboard":
                            item["prompt"] = ""
                    effective_durations = storyboard_durations
                    log.info(
                        "SF-H3: 检测到分镜文本已更新（签名不一致），按当前文本重建：%d 格落位，时长 %s",
                        sum(1 for c in sb_cells if c),
                        [d for d in storyboard_durations],
                    )
                else:
                    # 时间线正是由当前文本生成（前端已同步）：尊重时间线上的手动编辑，
                    # 全局仅未填写时回填，时长尊重时间线起止。
                    if text_global and not global_prompt:
                        global_prompt = text_global
                    log.info("SF-H3: 分镜文本与时间线签名一致，保留时间线手动编辑。")
            else:
                storyboard_prompts = _parse_storyboard_text(storyboard_text)
        imported_grid = data.get("gridImage") if grid_mode else None
        storyboard_source = storyboard_images
        if isinstance(imported_grid, dict) and imported_grid.get("file"):
            storyboard_source = _load_image(_safe_media_path(str(imported_grid["file"])))
        storyboard_cells = (
            _split_storyboard(storyboard_source, grid_layout, grid_border_crop)
            if grid_mode else []
        )
        if grid_mode and not storyboard_cells:
            raise ValueError("宫格模式未导入宫格图像，请点击“导入宫格图”或连接宫格图像接口。")
        storyboard_previews = _save_storyboard_previews(storyboard_cells) if grid_mode else []
        image_entries: list[tuple[str, torch.Tensor]] = [
            (f"storyboard_{index}", tensor) for index, tensor in enumerate(storyboard_cells)
        ]
        socket_image_entries = []
        if not grid_mode and reference_images is not None:
            socket_image_entries = [
                (f"socket_image_{index}", reference_images[index : index + 1])
                for index in range(int(reference_images.shape[0]))
            ]

        uploaded_images = []
        uploaded_videos = []
        uploaded_audios = []
        for item in active_items:
            kind = str(item.get("kind") or "")
            if kind not in ("image", "video", "audio") or not item.get("file"):
                continue
            path = _safe_media_path(str(item["file"]))
            if kind == "image":
                uploaded_images.append((str(item.get("id")), _load_image(path)))
            elif kind == "video":
                video = _load_video(path)
                _validate_reference_duration(float(video.shape[0]) / FPS, path.name, "video")
                paired_audio = _load_audio(path) if bool(item.get("includeAudio")) and _probe_media(path, "video")["has_audio"] else None
                if paired_audio is not None:
                    _validate_reference_duration(_duration_of_audio(paired_audio), f"{path.name} 的原声", "audio")
                uploaded_videos.append((str(item.get("id")), video, paired_audio))
            else:
                audio = _load_audio(path)
                _validate_reference_duration(_duration_of_audio(audio), path.name, "audio")
                uploaded_audios.append((str(item.get("id")), audio))
        image_entries.extend(uploaded_images)
        image_entries.extend(socket_image_entries)
        if len(image_entries) > 9:
            raise ValueError(f"参考图片共 {len(image_entries)} 张，超过 H3 的 9 张上限。")

        video_entries = list(uploaded_videos)
        socket_videos = [] if grid_mode else [reference_video_1, reference_video_2, reference_video_3]
        socket_video_audios = [] if grid_mode else [
            reference_video_audio_1,
            reference_video_audio_2,
            reference_video_audio_3,
        ]
        for index, video in enumerate(socket_videos):
            if video is not None:
                video_duration = float(video.shape[0]) / FPS
                _validate_reference_duration(video_duration, f"接口参考视频 {index + 1}", "video")
                paired_audio = socket_video_audios[index]
                if paired_audio is not None:
                    _validate_reference_duration(
                        _duration_of_audio(paired_audio), f"接口参考视频音轨 {index + 1}", "audio"
                    )
                video_entries.append((f"socket_video_{index}", video[: int(15 * FPS)], paired_audio))
        if len(video_entries) > 3:
            raise ValueError(f"参考视频共 {len(video_entries)} 段，超过 H3 的 3 段上限。")

        audio_entries = list(uploaded_audios)
        socket_audios = [] if grid_mode else [reference_audio_1, reference_audio_2, reference_audio_3]
        for index, audio in enumerate(socket_audios):
            if audio is not None:
                _validate_reference_duration(_duration_of_audio(audio), f"接口参考音频 {index + 1}", "audio")
                audio_entries.append((f"socket_audio_{index}", audio))
        if len(audio_entries) > 3:
            raise ValueError(f"独立参考音频共 {len(audio_entries)} 段，超过 H3 的 3 段上限。")

        first_visual = None
        if first_visual is None and image_entries:
            first_visual = image_entries[0][1]
        if first_visual is None and video_entries:
            first_visual = video_entries[0][1][:1]
        width, height = _canvas_size(
            aspect_ratio,
            first_visual,
            output_megapixels,
            resolution_multiple,
        )

        if not image_entries and not video_entries and audio_entries:
            raise ValueError("H3 参考音频不能单独使用，请至少添加一张图片或一段视频。")

        video_duration = sum(float(video.shape[0]) / FPS for _, video, _ in video_entries)
        if video_duration > 15.01:
            raise ValueError(f"参考视频总时长为 {video_duration:.2f} 秒，超过 H3 的 15 秒上限。")
        paired_audio_count = sum(1 for _, _, audio in video_entries if audio is not None)
        all_audio = [(item_id, audio) for item_id, audio in audio_entries]
        if paired_audio_count + len(all_audio) > 3:
            raise ValueError(
                f"视频原声与独立音频共 {paired_audio_count + len(all_audio)} 段，超过 H3 的 3 段音频上限。"
            )
        audio_duration = sum(_duration_of_audio(audio) for _, _, audio in video_entries if audio is not None)
        audio_duration += sum(_duration_of_audio(audio) for _, audio in all_audio)
        if audio_duration > 15.01:
            raise ValueError(f"参考音频总时长为 {audio_duration:.2f} 秒，超过 H3 的 15 秒上限。")
        total_files = len(image_entries) + len(video_entries) + len(all_audio)
        if total_files > 12:
            raise ValueError(f"参考素材共 {total_files} 个，超过 H3 的 12 个文件上限。")

        ref_images = {}
        ref_videos = {}
        ref_video_audios = {}
        ref_audios = {}
        tag_by_id = {}
        for index, (item_id, image) in enumerate(image_entries, start=1):
            ref_images[f"ref_image_{index}"] = image
            tag_by_id[item_id] = f"<Picture {index}>"
        audio_number = 1
        for index, (item_id, video, paired_audio) in enumerate(video_entries, start=1):
            ref_videos[f"ref_video_{index}"] = video
            tag_by_id[item_id] = f"<Video {index}>"
            if paired_audio is not None:
                ref_video_audios[f"ref_video_audio_{index}"] = paired_audio
                tag_by_id[f"{item_id}:audio"] = f"<Audio {audio_number}>"
                audio_number += 1
        for index, (item_id, audio) in enumerate(all_audio, start=1):
            ref_audios[f"ref_audio_{index}"] = audio
            tag_by_id[item_id] = f"<Audio {audio_number}>"
            audio_number += 1

        prompt = (
            _compile_prompt(
                global_prompt,
                active_items,
                tag_by_id,
                actual_seconds,
                storyboard_prompts,
                len(storyboard_cells),
                effective_durations,
            )
            if grid_mode
            else _compile_reference_prompt(reference_prompt or global_prompt, active_items, tag_by_id)
        )
        result = MiniMaxH3ReferenceToVideo.execute(
            clip,
            video_vae,
            audio_vae,
            prompt,
            width,
            height,
            frame_count,
            ref_image_size="max" if ref_image_size.startswith("最高") else "match",
            ref_images=ref_images,
            ref_videos=ref_videos,
            ref_video_audios=ref_video_audios,
            ref_audios=ref_audios,
        )
        summary = (
            f"{mode}｜{len(ref_images)}图 {len(ref_videos)}视频 "
            f"{len(ref_video_audios) + len(ref_audios)}音频｜{frame_count}帧｜{width}x{height}"
        )

        return io.NodeOutput(
            model,
            result.result[0],
            result.result[1],
            prompt,
            frame_count,
            FPS,
            width,
            height,
            ui={
                "compiled_prompt": [prompt],
                "summary": [summary],
                "storyboard_previews": storyboard_previews,
            },
        )
