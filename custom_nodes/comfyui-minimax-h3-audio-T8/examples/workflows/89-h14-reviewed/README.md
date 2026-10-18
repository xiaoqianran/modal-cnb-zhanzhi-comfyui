# H14：已审 LoRA 行作用域来源工作流（EXP）

2026-10-15 两项人工审核通过。两张图均来自实际画布保存、重开和完整运行；仅更新说明与来源标记，不修改执行参数、接线或旧图，也不重新采样。

| 工作流 | 用途 |
| --- | --- |
| [H14_Ordinary.json](H14_Ordinary.json) | 普通 LoRA 全权重应用的同条件对照 |
| [H14_AudioScope.json](H14_AudioScope.json) | 仅生成音频行施加直接低秩残差；采样后 Audit 核真实调用和清理 |

两片均 864×480、120 帧、24fps、5 秒，原生 124 帧显式裁到 0–5 秒，对白“你好，今天天气不错。”。使用相同 Wuli8 原生 INT8、五视角 LoRA 0.8、seed904512、8 步 Euler/simple、shift12:3；不强加二采。

需要现有 `wuli_h3_turbo_8step_v1_comfyui_int8_convrot.safetensors` 放在 `models/diffusion_models`，`minimax_h3_five_view_512_s1500.safetensors` 放在 `models/loras`，Qwen 与音视频 VAE 按图选择。模型不随仓库分发，不会隐式下载；更换资源后不继承本次质量结论。

五视角 LoRA 不是声音 LoRA。共享 attention 仍可能传播变化，本功能不保证最终画面不变、声纹隔离或提速。作用域图使用 `require_scope`，无法证明作用域会明确报错，不静默改成普通全模态应用。文件含 AdaLN、text-refiner 等不支持目标时须整文件预检失败，可另选旧 loader；不悄悄漏层。

本次 GPU 资产仅有 attention 目标；大型 fc2 权重和 generated_video 成片没有继承这两段的人工资格。LOW/HIGH 可各自显式放置，EAV／Prompt Relay 保持外置；旧工作流不迁移。详见[专题文档](../../../docs/H14_TOKEN_SCOPE.md)和[来源与许可](../../../THIRD_PARTY_NOTICES/H14-SOURCES.md)。感谢 baslack／Scriptorium、ComfyUI、Wuli-art／sandpies 及权重原作者。
