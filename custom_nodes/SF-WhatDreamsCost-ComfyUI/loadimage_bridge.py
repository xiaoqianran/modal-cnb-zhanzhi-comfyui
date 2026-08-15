"""让 ComfyUI 原生 LoadImage / LoadImageMask / LoadImageOutput 等节点支持外部绝对路径。

万象等第三方软件在「链接工作流」时，会把图片路径填成它自己的临时目录绝对路径
（如 C:\\Users\\Public\\WXApp_7d272424\\...\\2(1).png）。原生 LoadImage 只认
ComfyUI input 目录下的相对路径，会报 "Invalid image file: ..."。

本补丁在 folder_paths 层透明桥接：
- 当传入的是「真实存在的绝对路径」时，直接返回该路径 / True；
- 其他情况（正常的相对路径）完全走原逻辑，对其它工作流零副作用。

由于 LoadImage / LoadImageMask / LoadImageOutput 的 VALIDATE_INPUTS、load_image、
IS_CHANGED 全部通过 folder_paths 的这两个函数解析路径，patch 它们即可让所有
LoadImage 子类自动支持外部绝对路径，无需逐个改类、也无需万象识别自定义节点。
"""
import logging
import os

import folder_paths as _fp

log = logging.getLogger(__name__)


def _is_external_image(name):
    return (
        isinstance(name, str)
        and os.path.isabs(name)
        and os.path.isfile(name)
    )


try:
    # 先保存原始函数引用；patched 函数必须调用这些原始引用，
    # 绝不能通过已被覆盖的 _fp.xxx 调用，否则会无限递归。
    _orig_get = _fp.get_annotated_filepath
    _orig_exists = _fp.exists_annotated_filepath

    def _patched_get_annotated_filepath(name, default_dir=None):
        if _is_external_image(name):
            return os.path.abspath(name)
        return _orig_get(name, default_dir)

    def _patched_exists_annotated_filepath(name):
        if _is_external_image(name):
            return True
        return _orig_exists(name)

    _fp.get_annotated_filepath = _patched_get_annotated_filepath
    _fp.exists_annotated_filepath = _patched_exists_annotated_filepath

    log.info(
        "[SF-LoadImageBridge] 已启用：原生 LoadImage 现在支持外部绝对路径 "
        "（万象等第三方软件兼容）"
    )
except Exception as e:  # 补丁失败不应影响插件的其它功能
    log.warning("[SF-LoadImageBridge] 补丁启用失败（不影响其它功能）: %s", e)
