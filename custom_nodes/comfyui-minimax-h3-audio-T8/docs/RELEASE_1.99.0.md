# v1.99.0 — H11 已审原生增量（EXP）

新增13个独立节点，保留原720个节点的接口、默认值与注册顺序，不迁移旧工作流。模型下载只使21个动态资源菜单追加准确Wuli选项。

- Spark：独立MODEL→MODEL补丁、只读预检和采样后Audit。固定官方v0.1.2、Windows CP312/Torch2.10-cu130/SM89；实际343次Sparse、57次明确Dense预算委托，0异常。未知owner/mask保留委托，真实kernel错误传出；不捆绑轮子或自动安装。
- Wuli原生8步及4步三文件配方：8步完整25列模型；4步full FL2VA→trunk→heads_widen→heads_set，Core原生reshape/set/head-bank。两例实际8/4调用，不另造Diffusers加载器；后续HQ/unlocked/6步与HIGH/partial不继承资格。
- Audio-only Reference／Conditioning：Qwen可看图，DiT只用原生音频latent，不做video-VAE参考编码。稳定paired/standalone角色；DRIVE／FINAL／voice明确分离，成片仍使用生成声音。
- FreeVideo只读阶段卡和实时提示：有界host观察，不推进NFE，不改旧数值、配置或源码pin，不自动重启／编译。缺失字段不是0，旧完成Stage不是本次耗时，阶段提示不修改保存图。
- Bridge权重SHA绑定的参数侧车：内嵌固定契约优先，默认不采用，明确选择只输出旧BridgeConfig；既有手工、auto、多桥顺序保留。
- Scene/revision/request票据：旧FreeToken provider前绑定当前镜头，迟到提案不跨镜采用，默认保原稿。

[八份工作流](../examples/workflows/87-h11-reviewed/README.md)来自真实保存画布。七项人工审核全部通过；五段完整成片为864×480／24fps／120帧／5秒，原生124帧明确裁齐；另三项为接口审核，不冒充新增视频或训练效果。资源路径适配未重新采样，原参数和接线保持。30项新增与2项受影响旧CPU合同通过；发行收口另核示例、包、接口及源码，不重跑已通过的GPU采样。

两次Spark运行冷载／缓存状态不同，不能以总耗时计算公平提速。Audio-only样例角色A/B来自同一声音，不认证双人声纹；该任务原history后来丢失，保存图、原完成日志、Core资产job_id及完整媒体证据保留，不伪造编码统计。Bridge使用开发者Wushu说明fixture，不授新训练效果；Phase只读既有FP8/INT8完成Stage；Scene展示没有新provider调用或采用提案。

感谢[zechengtang/Spark-H3](https://github.com/zechengtang/Spark-H3)、[Wuli-art](https://huggingface.co/Wuli-art/MiniMax-H3-Turbo)、[sandpies](https://huggingface.co/sandpies/Wuli-MiniMax-H3-Turbo-ComfyUI)、[FlashML FreeVideo](https://github.com/FlashML-org/FreeVideo)、T8 Semantic Bridge Trainer与Sam Wasserman。见[许可与署名](../THIRD_PARTY_NOTICES/H11-SOURCES.md)。资源／权重单独下载，不分发私有素材、测试产物或roadmap。

QuantFunc／Nunchaku不恢复；暂停的Sol／Strata与H09 Frozen Cache研究不纳入。其他硬件、授权未证资产和未验证组合仅记录明确边界，不假报完成。

GitHub main与正式发行不等于Comfy Registry已Active或Manager可安装；Registry审核进度单独报告，不重复上传、不绕过审核。
