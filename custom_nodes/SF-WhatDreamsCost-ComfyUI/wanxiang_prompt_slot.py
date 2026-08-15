import re

from comfy_api.latest import io


# 与 ltx_director._strip_global_label 保持一致的引导标签集合，
# 用于在透传给下游前先剥掉"正面词："等标签，避免标签泄漏进全局/分镜提示词。
_STRIP_LABEL_RE = re.compile(
    r"^\s*(?:正面词|正面|全局提示词|全局词|全局|总提示词|总词|总览词|概述|总览|视频提示词|视频词)\s*[:：]\s*",
    re.I,
)


def _strip_leading_label(text: str) -> str:
    """只剥掉整段文本开头的『正面词：』类引导标签，保留正文（含后续各分镜行）。"""
    return _STRIP_LABEL_RE.sub("", (text or "").lstrip("\ufeff")).strip()


class SFWanxiangPromptSlot(io.ComfyNode):
    """万象视频提示词专用槽位。

    万象 AI 链接工作流时，会扫描整个工作流中哪个节点的文本内容含有『正面词』，
    并把用户填写的视频提示词注入那个节点。本节点被设计成唯一的『正面词』载体：
    - 默认文本以『正面词：』开头，方便万象自动识别；
    - 万象注入后，本节点会先剥掉开头的『正面词：』标签再输出，
      避免标签污染下游 SFLTXDirector 的全局/分镜提示词；
    - 输出 STRING，接到 SFLTXDirector 的『宫格分镜文本』即可；
    - 如果全工作流只有这一个节点出现『正面词』三个字，万象就不会找错目标。
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SFWanxiangPromptSlot",
            display_name="SF 万象视频提示词槽",
            category="SF-WhatDreamsCost",
            description=(
                "专门给万象 AI 回填视频提示词的槽位。把这个节点接到 "
                "SFLTXDirector 的『宫格分镜文本』输入，并确保全工作流只有这个节点的文本里出现『正面词』三个字。"
                "万象注入的『正面词：』标签会在输出前自动剥离。"
            ),
            inputs=[
                io.String.Input(
                    "positive_prompt",
                    display_name="正面词",
                    multiline=True,
                    default="正面词：\n在此粘贴或让万象自动填入视频提示词（含全局提示词 + 各宫格分镜）。",
                    tooltip="万象会把这个字段的内容替换为用户输入的视频提示词。请保持全工作流唯一。输出前会自动剥掉开头的『正面词：』标签。",
                ),
            ],
            outputs=[
                io.String.Output("prompt", display_name="视频提示词"),
            ],
        )

    @classmethod
    def execute(cls, positive_prompt):
        # 万象回填的整段文本通常以『正面词：』开头。这里剥掉该标签再透传，
        # 让下游 SFLTXDirector 的脚本识别只拿到干净正文（全局提示词 + 各分镜），
        # 避免『正面词』三个字泄漏进全局提示词或某个分镜里。
        return (_strip_leading_label(positive_prompt),)
