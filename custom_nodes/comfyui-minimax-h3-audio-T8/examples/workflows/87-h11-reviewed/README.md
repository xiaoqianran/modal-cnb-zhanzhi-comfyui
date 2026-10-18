# H11：已审来源工作流（EXP）

2026-10-12七项人工审核全部通过。八份图来自真实画布保存、重开及UI运行，不覆盖旧工作流；资源路径适配没有重新采样。五段视频均为864×480、24fps、120帧、5秒，原生124帧明确裁齐0–5秒。

| 工作流 | 用途与先配置的资源 |
| --- | --- |
| [H11_Spark_Dense.json](H11_Spark_Dense.json) | 固定FastH3 V2的Dense对照；两个runtime_config填自己的Spark准备清单 |
| [H11_Spark_Sparse.json](H11_Spark_Sparse.json) | 同模型、seed和轨迹的Spark；查看采样后真实调用Audit，不能把委托当Sparse |
| [H11_Wuli8.json](H11_Wuli8.json) | 完整Wuli原生8步模型，video12/audio3、simple8、Euler、CFG1 |
| [H11_Wuli4.json](H11_Wuli4.json) | 准确full FL2VA→trunk→heads_widen→heads_set，强度1；video6/audio3、simple4 |
| [H11_AudioOnly.json](H11_AudioOnly.json) | 上传自己的正常视频；Qwen看图、DiT只用音频latent，原Ref2VA40步；DRIVE／FINAL不混 |
| [H11_BridgeSidecar.json](H11_BridgeSidecar.json) | 配置对应桥和inference_settings.json；显式false/true比较，不Apply或采样 |
| [H11_PhaseCard.json](H11_PhaseCard.json) | 分别填写自己的FP8／INT8完成Stage manifest和完整SHA；只读已有耗时，不采样 |
| [H11_SceneTickets.json](H11_SceneTickets.json) | 同一原稿的两镜票据展示；0provider调用，默认不采用提案 |

Spark只验收Windows CP312／Torch2.10-cu130／SM89匹配官方轮子；使用[显式准备工具](../../../tools/prepare_h11_spark_runtime.py)，不会自动安装或替换注意力。已有hook、mask和不支持路径保留委托；真实kernel错误正常传出。两片缓存／冷载状态不同，不能用总时间宣称提速百分比。

Wuli四资产已经是ComfyUI格式，可用[固定原件下载工具](../../../tools/download_h11_wuli.py)。4步三文件不是普通风格LoRA，顺序不能省；8步25列shape不是整模型SHA证明。partial／HIGH／长窗、后续6步／HQ／unlocked不继承本例画质资格。

AudioOnly示例源视频不捆绑。A、B本次来自同一个声音，只验证paired/standalone角色传递，不认证两人声纹。FINAL仅透传试听；保存成片连接的是生成声音，不能用原声替换来冒充声音生成通过。

Bridge图第二分支显式true是对照的选择，不改变节点默认false。留空sidecar_path只检查所选权重同目录；本次使用开发者Wushu说明fixture，不代表新Trainer训练效果。Phase图必须提供真实原生Stage而非MP4；旧回执缺phase／compile／VAE／mux显示不可用，不是0，不相加nested计时。

Scene实际接法为Ticket→Rewrite→Adopt，并把当前Ticket接Adopt；新提交更新request_id，迟到提案不跨scene/revision/request采用。该图仅展示票据，不能当生成视频或改稿效果证明。

LOW/HIGH及EAV／Prompt Relay仍可独立外置，旧工作流不迁移。本批单采视频不等于所有双采组合认证。参见[完整接线与边界](../../../docs/H11_NATIVE_EXTENSIONS.md)、[资源与条件范围](../../../docs/H11_RESOURCES_AND_SCOPE.md)及[作者署名](../../../THIRD_PARTY_NOTICES/H11-SOURCES.md)。
