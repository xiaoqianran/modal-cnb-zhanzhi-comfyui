# v1.101.0 — H14 LoRA 生成行作用域（EXP）

新增两个独立节点：`MiniMaxH3TokenLoRAApplyEXPT8`、`MiniMaxH3TokenLoRAAuditEXPT8`。原735节点接口、默认值、顺序及全部旧工作流保持，总注册737。

- MODEL → 行作用域 → 原 Guider／Sampler。可分别选择生成音频行、生成视频行；参考／条件／文本行不在生成行策略中直接添加残差。全 eligible 行仅供数值对照，不等完整模型所有层。
- 使用原生 plain LoRA 解析和结构映射，要求整份文件目标完整支持。AdaLN、text-refiner、heads 等不支持目标不静默漏掉，DoRA／LoHa／LoKr／LoCon 不当 plain 使用；旧 loader 保持可选。
- 保留 Core 原融合计算，在实际 MLP 边界补 fc2 选定行残差，不全局替换算子或隐藏关闭融合。事务 hook 清理、共享底层模块与调用作用域保护、重复应用检查和内容 SHA 身份独立记录。
- 未验证的外来 owner／hook 原样保留并明确报告无 scope，或由显式 `require_scope` 报错；不清空用户补丁、全局禁用 LoRA／Sage／Sol 或默默退成普通全模态加载。
- 采样后审计透传 LATENT，报告实际目标调用、行计数、委托及清理；不是仅凭 Apply 成功就认为已生效。

[两张已审来源工作流](../examples/workflows/89-h14-reviewed/README.md)保留真实画布保存→重开→API往返→完整运行的参数与接线。用户于2026-10-15接受普通 LoRA 对照和 generated_audio 两片；均864×480、120帧、24fps、5秒，原生124帧显式裁0–5秒，对白“你好，今天天气不错。”。scope 实际400次block／100目标各8次、非零残差、0委托／0遗留hook。

8个原生CPU合同涵盖融合fc2、行选择、异常注册清理、同module下一任务、并发、完整解析与内容身份。本次GPU资产是既有五视角 attention LoRA，不是新声音模型；大型fc2权重和generated_video成片不继承此次GPU／人工质量资格。共享attention仍可能传播变化，不保证另一模态最终不变、声纹隔离或公平提速。LOW/HIGH、EAV、Prompt Relay继续外置，不强加二采或迁移旧图。

感谢baslack／Scriptorium、ComfyUI、Wuli-art／sandpies和权重原作者；见[用法与限制](H14_TOKEN_SCOPE.md)、[来源说明](../THIRD_PARTY_NOTICES/H14-SOURCES.md)及保留的MIT许可。权重、人物图、视频、人工反馈和本地交接文件不分发。

本版不引入Flow target-band算法，不改变已审续接数值；不恢复已移除或暂停的研究项目。GitHub正式发布与Comfy Registry激活独立，上传成功不代表Manager可安装，不重复上传或绕过安全审核。
