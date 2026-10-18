# v1.100.0 — H13 AudioFirst与普通Wuli Hybrid（EXP）

追加两个独立AudioFirst节点，保留原733个接口、默认值、注册顺序与旧工作流。模型安装只让十个动态资源菜单增加准确普通Hybrid选项，总注册735。

- 同条件Tiny投影复用完整场景embedding，不重编码CLIP。T2VA或单首帧；单首帧从同一原图真实VAE编码32×32，不把缩小latent当新编码。多参考／空间引导及已编译窗口不静默丢弃，保持旧完整路线。
- Tiny普通采样器→原Source AV Prepare strict regenerate/lock→完整画幅普通采样器。新审计对照Tiny源、prepared遮罩和实际最终AV，原样返回最终对象，不替换成片声音。
- 普通Wuli FL-base／Ref-AdaLN b25–49 Hybrid已是ComfyUI原生单体，使用原加载器。固定SHA准备工具只验证和安装该文件，不升级环境；原生simple8/Euler/shift12:3/CFG1，无须再叠已烘焙FlashGen0.5。
- Wuli权重每次调用重算完整SHA，修复同size／恢复mtime等stat信号误命中缓存；不声称消除后续所有TOCTOU。

[两份工作流](../examples/workflows/88-h13-reviewed/README.md)均来自真实画布保存、重开、完整GPU运行；用户于2026-10-15审核通过。每片864×480、120帧、24fps、5秒，原生124帧显式裁0–5秒。AudioFirst是Tiny8步＋完整画幅8步，实际音频latent exact／最大差0，最终AAC对Tiny原FLAC相关约0.9981，没有换轨；普通Hybrid为Ref2VA完整八步。

原八项CPU合同通过，发行收口只检查来源导出、实际发行包及注册，不重跑采样。单首帧另核真实VAE编码、零第三段影片；不授单首帧完整视频、多参考、Realism、所有EAV／Relay组合或公平提速资格。参考图片和权重不分发，使用前选择自己的合法素材。

感谢sepiablue-ai／AudioFirst、Wuli-art、sandpies、FlashGen／Kijai、smhfacct与MiniMax；见[接线](H13_AUDIO_FIRST_HYBRID.md)和[来源许可](../THIRD_PARTY_NOTICES/H13-SOURCES.md)。导演台路径本地已有修复，本批只核验，不重复算新功能。

QuantFunc／Nunchaku不恢复，Spark0.1.3适配、Realism／RefLoRA、多参考空间转换、Sol／Strata／Frozen研究不混入。GitHub正式发行不代表Registry已Active或Manager可安装；不重复上传或绕过审核。
