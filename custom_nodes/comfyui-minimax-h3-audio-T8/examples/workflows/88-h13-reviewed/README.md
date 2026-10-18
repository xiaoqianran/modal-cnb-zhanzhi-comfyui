# H13：已审来源工作流（EXP）

2026-10-15两项人工审核通过。以下工作流来自实际画布保存、重开和完整运行；导出仅更新说明与来源标记，不改执行参数、接线或旧工作流，不重新采样。

| 工作流 | 用途与资源 |
| --- | --- |
| [H13_AudioFirst.json](H13_AudioFirst.json) | 同完整场景条件的Tiny32×32先生成音频，再Source AV strict锁音生成完整画幅；使用完整Wuli原生8步模型 |
| [H13_Hybrid.json](H13_Hybrid.json) | 普通Wuli FL-base / Ref-AdaLN Hybrid原生Ref2VA八步；选择自己的合法参考图 |

两片均864×480、120帧、24fps、5秒；原生124帧显式裁到0–5秒，对白“你好，今天天气不错。”。AudioFirst是Tiny8步＋完整画幅8步，不是4+4双采；实际最终音频latent与Tiny源exact，AAC对原FLAC相关性约0.9981，不用原FLAC换轨冒充生成通过。Tiny音频单独试听，不要与视频同时播放。

模型放在`models/diffusion_models`，文本编码器与音视频VAE按画布选择。两个图使用不同Wuli模型，不要互换；普通Hybrid完整SHA及固定下载方法见[专题文档](../../../docs/H13_AUDIO_FIRST_HYBRID.md)，它已是ComfyUI原生单体，不需转换。模型已烘焙FlashGen0.5，无须再叠同LoRA。图片不随仓库分发，`H13_reference.png`只是已审来源文件名，使用前须在LoadImage选择自己的图片；换图后的结果须自行确认。

本次只接受这两段媒体，不授予提速、Realism变体、多参考、单首帧完整影片、长窗或所有外置EAV／Prompt Relay组合质量资格。MODEL／条件／SIGMAS／Sampler仍显式外置，旧工作流不迁移。单首帧只额外验证了真实32×32 VAE编码，不是第三段已审视频。

感谢sepiablue-ai、Wuli-art、sandpies、FlashGen、Kijai和smhfacct；[来源与许可](../../../THIRD_PARTY_NOTICES/H13-SOURCES.md)分别说明代码与权重范围。
