# 兼容补丁：让原生 LoadImage 支持万象等软件传来的外部绝对路径
# （失败时仅告警，不影响插件其它功能）
try:
    from . import loadimage_bridge  # noqa: F401
except Exception:
    pass

from .ltx_keyframer import SFLTXKeyframer
from .multi_image_loader import SFMultiImageLoader
from .ltx_sequencer import SFLTXSequencer
from .speech_length_calculator import SFSpeechLengthCalculator
from .load_audio_ui import SFLoadAudioUI
from .load_video_ui import SFLoadVideoUI
from .ltx_director import SFLTXDirector, SFGridDirectorLegacy
from .ltx_director_guide import SFLTXDirectorGuide, SFLTXDirectorCropGuides
from .sf_load_image_path import SFLoadImageFromPath
from .wanxiang_prompt_slot import SFWanxiangPromptSlot
from .h3_multimodal_director import SFH3MultimodalDirector

NODE_CLASS_MAPPINGS = {
    "SFLTXKeyframer": SFLTXKeyframer,
    "SFMultiImageLoader": SFMultiImageLoader,
    "SFLTXSequencer": SFLTXSequencer,
    "SFSpeechLengthCalculator": SFSpeechLengthCalculator,
    "SFLoadAudioUI": SFLoadAudioUI,
    "SFLoadVideoUI": SFLoadVideoUI,
    "SFLTXDirector": SFLTXDirector,
    # 万象按 1.0 契约生成工作流：带连字符的类名必须注册
    "SF-LTXGridDirector": SFGridDirectorLegacy,
    "SF-LTXDirectorGuide": SFLTXDirectorGuide,
    "SFWanxiangPromptSlot": SFWanxiangPromptSlot,
    "SFLTXDirectorGuide": SFLTXDirectorGuide,
    "SFLTXDirectorCropGuides": SFLTXDirectorCropGuides,
    "SFLoadImageFromPath": SFLoadImageFromPath,
    # H3 多模态参考导演台（自 CS-H3-Multimodal-Director 3.0 同步，含 SF 分镜文本识别增强）
    "SFH3MultimodalDirector": SFH3MultimodalDirector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SFLTXKeyframer": "SF-LTX 关键帧",
    "SFMultiImageLoader": "SF 多图加载器",
    "SFLTXSequencer": "SF-LTX 序列引导",
    "SFSpeechLengthCalculator": "SF 语音时长计算",
    "SFLoadAudioUI": "SF 音频加载器",
    "SFLoadVideoUI": "SF 视频加载器",
    "SFLTXDirector": "SF-LTX 2.0 宫格导演台",
    "SF-LTXGridDirector": "SF-LTX 宫格导演台",
    "SF-LTXDirectorGuide": "SF-LTX 导演台引导",
    "SFWanxiangPromptSlot": "SF 万象视频提示词槽",
    "SFLTXDirectorGuide": "SF-LTX 导演台引导",
    "SFLTXDirectorCropGuides": "SF-LTX 裁剪引导帧",
    "SFLoadImageFromPath": "SF 绝对路径图片加载",
    "SFH3MultimodalDirector": "SF-H3 多模态参考导演台",
}

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
