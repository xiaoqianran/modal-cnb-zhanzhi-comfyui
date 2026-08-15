# SF-H3 多模态参考导演台（SF-WhatDreamsCost-ComfyUI 3.0）

面向 MiniMax H3（海螺）视频生成的 ComfyUI 插件：宫格分镜自动拆分 + 全能参考（图片/视频/音频），并内置万象（Wanxiang）软件对接辅助节点。

## 🙏 感谢原作者

本插件基于以下两个项目改造，版权与许可证遵循原项目授权：

- **[WhatDreamsCost/WhatDreamsCost-ComfyUI](https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI)** —— 原始项目
- **[yg496/CS-H3-Multimodal-Director](https://github.com/yg496/CS-H3-Multimodal-Director)** —— H3 多模态参考导演台（CS 3.0）。本版本的 `SFH3MultimodalDirector` 节点同步自该项目，并做了独立命名隔离（节点类型、前端扩展名、后端接口路径、上传子目录均使用 `SF` 前缀），可与原版在 RunningHub 或本地环境同时存在，互不覆盖。

## ✨ 特性

- **宫格分镜自动拆分**：支持 2x2 四宫格、3x2 六宫格、3x3 九宫格，把一张宫格分镜图按格精确切片，作为 H3 的分镜参考图。
- **分镜文本智能识别**：识别"第X个镜头"锚点、方位词严格落格（4/6/9 宫格位置映射，支持"中中"等中心格写法）、"X秒"时长按占比分配到各分镜（缩放到 H3 4-15 秒上限）。
- **正面词/全局提示词剥离**：自动剥离"视频提示词:"前缀及"正面词/全局提示词"等标签，避免标签污染生成。
- **前端自动分镜**：连接宫格图像 + 分镜文本后，前端自动把图片落格预览、提示词按方位落格、时长按文本分配，所见即所得。
- **签名同步兜底**：`timeline_data` 携带文本签名，万象回填新文本时后端自动以文本为准重建分镜；前端手动编辑过时间线时则尊重手动调整。
- **等比缩略图**：时间线缩略图按原始宽高比显示（黑边填充），不再拉伸变形。
- **万象软件对接**：提供视频提示词槽、绝对路径图片加载等辅助节点，打通万象 → ComfyUI 工作流。

## 🎛 核心节点

- `SF-H3 多模态参考导演台`（`SFH3MultimodalDirector`）—— 主节点，宫格分镜 + 全能参考
- `SF 万象视频提示词槽`（`SFWanxiangPromptSlot`）—— 万象视频提示词中转
- `SF 绝对路径图片加载`（`SFLoadImageFromPath`）—— 支持绝对路径加载图片

> 插件同时保留 SF-LTX 系列节点（如 `SF-LTXGridDirector`，用于万象 1.0 契约兼容），此处不再展开介绍。

## 🚀 安装

```bash
git clone https://github.com/rickSF/SF-WhatDreamsCost-ComfyUI
```

将目录放入 `/ComfyUI/custom_nodes/` 后重启 ComfyUI，或通过 ComfyUI Manager 安装。

## 🔧 使用说明

1. 将宫格分镜图连接到 `SF-H3 多模态参考导演台` 的宫格图像输入；
2. 将分镜文本（形如"第1个镜头：…（2秒）"）填入宫格分镜文本字段；
3. 前端会自动完成落格预览与时长分配，确认后即可生成。

对接万象软件时，通过 `SF 万象视频提示词槽` 接收提示词，并用 `SF 绝对路径图片加载` 读取宫格图，即可在万象中直接驱动本工作流。
