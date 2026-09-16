# selflift-Avatar

**当前公开版本：`v0.1.1-experimental`** · [发布说明](https://github.com/slmonker/selflift-Avatar/releases/tag/v0.1.1-experimental) · [下载 ZIP](https://github.com/slmonker/selflift-Avatar/releases/download/v0.1.1-experimental/selflift-Avatar-v0.1.1-experimental.zip) · [更新记录](CHANGELOG.md)

用于 ComfyUI / MiniMax H3 的 **SelfLift 独立实验分支**，重点适配音视频双流遮罩和原始音频保留。与原版节点使用不同的注册 ID，可以并存。

> **实验版本，非官方项目。** v0.1.1 已通过 28 项 CPU 测试；维护者反馈当前工作流试用可用。尚无系统性的口型准确率、性能或多模型组合验证，不保证所有音频与角色都能准确同步。

## v0.1.1 的重点

上一版能够解析遮罩并保留输出音频，但缺少 H3 原生音频条件标签和模型输入侧的已知音频注入。本版补齐这条路径：让音频在低清与高清采样时都参与条件输入，而不只是最终恢复声音。

同时分离高清阶段的带噪恢复状态和干净音频约束。此修复解决的是条件传递问题，不代表上采样器、模型、提示词或其他设置对口型的影响已经消除。

## 安装

需要一套已经能够运行 MiniMax H3 的 ComfyUI，以及该工作流本来需要的模型、VAE 和可选 latent upscaler。此项目不包含模型权重，也不安装新的依赖。

在 `ComfyUI/custom_nodes` 下执行：

```bash
git clone https://github.com/slmonker/selflift-Avatar.git
```

或下载 Release 中的 ZIP，将其中的 `selflift-Avatar` 文件夹放入 `ComfyUI/custom_nodes`。之后重启 ComfyUI 后端并刷新页面。

## 更新

**Git 安装：**在本插件目录执行 `git pull --ff-only`，然后重启 ComfyUI 后端。若有自己的代码修改，请先备份或提交，不要强制覆盖。

**ZIP 安装：**先将旧版备份到 `custom_nodes` 之外，再把新版 `selflift-Avatar` 文件夹放回 `custom_nodes` 并重启。不要将两个 Avatar 副本同时放在 `custom_nodes` 下，以免节点重复注册。原版 SelfLift 使用不同的节点 ID，可以保留。

从 v0.1.0 升级时，已有 Avatar 节点的 ID 和输入接口不变，不需要重新接线；只刷新网页不足以加载新的 Python 代码。

## 使用

1. 搜索 `selflift-Avatar`，添加 **selflift-Avatar Sampler (MiniMax H3)**。
2. 把原 SelfLift 采样器的输入和输出改接到新节点。原节点和工作流不会自动替换。
3. 使用标准 **Euler**；带 `noise_mask` 时设置 **`highres_tiling=false`**。
4. 建议复制工作流，以固定 seed、短片段、相同其他参数进行对比。
5. 如果采用外部 H3 latent upscaler，可保留 `rho=0`；`upscaler_model=none` 时，H3 节点仍要求 `rho>0`。

| 注册 ID | 显示名称 |
| --- | --- |
| `SelfLiftAvatarH3Sampler` | selflift-Avatar Sampler (MiniMax H3) |
| `SelfLiftAvatarImageSampler` | selflift-Avatar Sampler (Image) |
| `SelfLiftAvatarH3TST` | selflift-Avatar H3 TST |

音频遮罩仍通过 latent 字典的 `noise_mask` 提供，没有新增单独的 mask 输入端口。

## 使用输入音频驱动角色

典型连接方式如下（节点显示名称可能随 ComfyUI 版本变化）：

```text
输入音频 → 裁剪到目标片段 → H3 音频 VAE 编码
                                ↓
SolidMask(value=0) → SetLatentNoiseMask
                                ↓
H3 视频 latent ──────────→ 合并音视频 latent
                                ↓
                 selflift-Avatar Sampler (MiniMax H3)
```

- 音频 mask 为 0 时，保留输入音频；为 1 时，允许生成音频。视频和音频可以使用不同遮罩。
- 音频长度、视频帧数和最终输出 FPS 应对应同一目标片段。编码音频与最终合成的音频也应来自同一次裁剪。
- 若最终合成节点直接使用原音频，听到正确声音不等于采样时音频条件正确；判断口型需要看实际生成的视频。
- 与 H3 条件节点配套连接模型、正负条件及视频 VAE；本插件不是独立的后期对口型工具。

## 遮罩支持

- 普通视频/图片 Tensor：BHW、BCHW、BCTHW；通道为 1 或实际 latent 通道数。
- H3 `NestedTensor(video_mask, audio_mask)`：分别解析音视频，保留多通道权重。
- 严格匹配音视频展平尺寸的 `[B,1,N]` 遮罩。
- 音频 T、BT、BST、BCST 布局；维度为 1 可广播。
- 视频空间尺寸不匹配时进行双线性缩放；不猜测时间轴、不对音频时间轴自动重采样。
- 普通 Tensor 默认只约束视频，缺省音频遮罩按全 1 处理。

**0=保留原内容，1=生成，0~1=软约束。** 必须有对应的已初始化 latent 才能保留实际内容。

### SolidMask 加到音频的兼容处理

`SolidMask → SetLatentNoiseMask → 合并音视频 latent` 可能给音频附加图像尺寸的恒定遮罩，例如 `[1,1,928,1664]` 全零。

本版本确认每个批次/通道在空间上严格恒定后，压缩为 `[B,C,1,1]` 广播到音频 latent。全零保留整段输入音频，全一生成音频，恒定软权重也不变。非恒定图像图案不擅自解释为音频时间遮罩。

## 采样约束与修复

- 低清和高清阶段分别应用对应视频 mask；音频 mask 不随空间分辨率缩放。
- v0.1.1 在条件构建前通过 ModelPatcher 的 OUTER_SAMPLE wrapper 传入正确打包的 mask，让 H3 生成 `audio_denoise_mask` 条件标签。
- 使用原生 `KSamplerX0Inpaint` 和 H3 `scale_latent_inpaint` 在模型输入侧注入已知音频，不再只在预测后恢复音频。
- 高清阶段把带噪 resume 状态与干净 inpaint anchor 分开，保留原始采样状态，避免将残余噪声当成原音频。
- 约束原内容时调用实际采样模型的 `process_latent_in`，包含 H3 的音频尺度转换。
- 返回前仅对 `mask==0` 的位置恢复原始 latent，不重复混合软遮罩。
- 修复纯像素 anchor 模式（`rho=w_min=w_max=1`）带 mask 时的 None 运算问题。
- 报错包含实际 mask 类型、各流形状和 latent 形状。

## 口型效果排查

音频保留不等于口型质量保证。外部 latent upscaler 包含时间卷积且不直接接收目标音频，放大过程和剩余高清采样步数可能影响嘴部细节；当前没有量化归因。

固定模型、音频片段、seed、提示词、帧数及输出 FPS，先与原生全分辨率采样比较，再分别测试更多高清采样步数或不使用外部 upscaler 的像素 anchor 路径，避免同时更改多个参数。不同路径随机数消耗可能不同，需多个 seed 复核。

## 已知限制

- 带 mask 时不支持 `highres_tiling`。
- 只应用静态输入遮罩，不执行上游 `denoise_mask_function` 的动态调度；检测到时会警告。
- `model_hires` 必须使用兼容架构、latent 格式和采样尺度设置；跨架构/尺度切换未验证。
- 保留的是输出 latent 区域，不承诺 VAE 解码后像素或波形逐点相同。
- TST、分块和外部 upscaler 继承上游的实验限制；没有重新验证这些功能的所有组合。

## 测试

从安装在 ComfyUI 下的插件目录运行，使用 ComfyUI 对应的 Python：

```bash
python tests/test_avatar.py
```

28 项 CPU 测试包括音视频打包、真实 H3 音频尺度转换、全零/全一遮罩、前段保留、软遮罩、多通道、恒定图像尺寸音频遮罩和两阶段流程。

两阶段测试使用真实 Euler、原生 inpaint 调用链、合成 denoiser 与模拟 VAE lift。新增检查确认低清/高清阶段均产生音频遮罩条件，且模型输入在撤销音频 carry 变换后与被保留的音频一致。测试不加载大模型权重，也不衡量实际口型质量。

## 来源与许可说明

基于 [facok/comfyui-SelfLift](https://github.com/facok/comfyui-SelfLift) 的本地副本修改，保留[上游说明](docs/upstream/README.md)和[中文说明](docs/upstream/README_CN.md)。来源哈希见 `PROVENANCE.json`。

上游包含 SelfLift、TST 和可选 MiniMax H3 latent upscaler 的参考与致谢；这些研究和权重不由本项目声明所有权。本次上传检查时，上游未声明许可证；本项目未擅自新增开源许可证，不能仅凭本仓库存在推断获得原代码或模型的再分发授权。

## 回退

[v0.1.0-experimental](https://github.com/slmonker/selflift-Avatar/releases/tag/v0.1.0-experimental) 保留供对比和回退，但不包含本版原生音频条件修复。也可在工作流中换回原版 SelfLift 节点。

卸载时关闭 ComfyUI，将本文件夹移出 `custom_nodes`。本项目不会修改原版插件或 ComfyUI 核心文件。
