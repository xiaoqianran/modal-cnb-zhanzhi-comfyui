# H14：生成音频／视频token行的LoRA作用域（EXP）

新节点独立外置，不替换旧LoRA loader、735个旧接口或任何已存工作流。
当前开发通过8项CPU合同、真实画布保存/重开/API语义往返和两段5秒完整音画运行。2026-10-15用户实际反馈r2接受普通LoRA与generated_audio两段指定音画；不扩为任意模型、声纹隔离、另一模态不变或提速认证。

已审来源工作流：[普通LoRA对照](../examples/workflows/89-h14-reviewed/H14_Ordinary.json)、[生成音频行作用域](../examples/workflows/89-h14-reviewed/H14_AudioScope.json)。参数、资源和全部接线与实际运行保持，仅更新说明与来源标记，未重新采样；[目录说明](../examples/workflows/89-h14-reviewed/README.md)列出用法与资格边界。

## 接线

MODEL → **H3 LoRA · 生成音频/视频行作用域** → 原Guider／普通采样器。
同一MODEL和实际采样LATENT再接 **H3 LoRA · 实际行作用域审计**，其LATENT原样送解码。
LOW/HIGH各自显式放置；多语义桥、EAV、Prompt Relay仍按原接线外置，不藏进此节点。

- `generated_audio`只在`audio`生成行加直接残差；不直接作用text、cond_audio或ref_audio。
- `generated_video`只在`video`生成行加直接残差；不直接作用cond或ref_img。
- `all_eligible_rows`是仅所支持token层全行的数值对照，不等普通完整模型所有层的LoRA。
- `disabled`或strength0原MODEL对象透传、不打开文件；负strength保留。
- 同一policy可串联不同plain LoRA，已作用同份内容再次添加明确报错；普通loader放在前或后重复同内容也检查。

共享attention会继续传播影响，因此选音频行**不保证最终画面不变**，也不保证隔离声纹。作用域不是音频锁或另一模态的冻结算法。

## 支持合同与融合计算

复用原T8／Core的plain LoRA解析、fused QKV与SwiGLU结构转换。每个源tensor都须被消费，目标必须完整落在实际H3 block的qkv/out/fc1/fc2，并匹配真实矩阵形状。AdaLN、text-refiner、heads、门控set权重以及DoRA／LoHa／LoKr／LoCon不在此算法范围，明确拒绝整份文件而不是悄悄漏层；旧loader仍可单独选择。

当前Core的融合fc2可能绕过module.forward。本实现只观察实际fc1输出的选定行，使用Core的SwiGLU计算其fc2残差，在实际MLP输出补入；原`linear_input_act`／量化融合照常执行，不替换全局算子、不偷偷设置force-forward或关闭融合。

临时hook位于每个block的try/finally事务内，注册中途/执行/取消异常都清理；底层module锁和ContextVar分开保护共享clone与并行无scope调用。已知原生fresh输出可局部写入，alias输出先复制，原输入/权重不变。实际未经过全部目标的运行不能冒充完整scope。

未知block owner／自定义forward／外来module hook保留。默认`delegate_without_scope`执行原实现并警告、报告未生效，不清空用户LoRA/Sage/Sol。明确要求`require_scope`时，本算法不能证明scope则正常报错，不偷偷改为普通全模态加载。后置效果也可能接管owner，最终以Audit真实调用为准，不能只看Apply报告。

Audit显示真实block/目标调用、row计数、最大直接残差、委托原因和剩余hook。它不是采样完整步数或成片质量证明；LATENT只保证执行顺序，不篡改采样结果。内容指纹每次读完整LoRA SHA，不依赖mtime/size；opaque运行状态不授跨任务可移植缓存资格。

## 最低验证范围

本批8个新CPU合同涵盖实际native小块、fc2.forward被绕过时的全行权重数学、生成行/参考行、部分注册与执行异常、同module第二请求、并发无scope调用、真实parser／完整覆盖、同内容重复、两LoRA组合、同mtime同size替换与opaque缓存。CUDA未初始化，作者测试不计入这些数量。

已有`minimax_h3_five_view_512_s1500.safetensors`完整200 tensor、50块100 attention目标已实际在Wuli8原生INT8模型运行。普通权重patch／generated_audio两臂均真实画布Run，864×480、124原生帧→120帧/24fps/5秒、8步Euler/simple、相同种子/提示词/强度；完整RGB、时间戳及AAC解码均通过。作用域版实际400次block调用、100目标各8次、非零残差、无委托或遗留hook。它是已有五视角LoRA，不冒充新声音LoRA。

本次大模型GPU资产只有attention目标；MLP/fc2由真实Core小块CPU合同（包括绕过fc2.forward的融合路径）验证，不冒称大模型fc2权重或generated_video成片也获本次GPU资格。普通与scope的模型patch／加载缓存不同，两段耗时不构成公平提速对比；scope产生的Core编译graph break也保留在原日志，没有为测试隐藏关闭融合/编译。其他含text-refiner/AdaLN的文件可能不属于本功能，不能按文件名保证兼容。用户接受的是这两段指定画质与对白，更换素材、资源或作用域仍须自行判断。

Flow target-band只保留独立研究：缺本项目真实失败／匹配carry时不替换已审RGB尾部续拍策略、不追加示范采样。其他37方向是旧能力及反例材料，不重复建设。QuantFunc／Nunchaku不恢复，Sol／Strata／Frozen研究不解暂停。

感谢[baslack/scripts_nodes PR2](https://github.com/baslack/scripts_nodes/pull/2)提出token行LoRA思路（MIT），及ComfyUI的原生LoRA、PackedLayout和融合算子。T8增加完整覆盖、生成行/参考分离、融合fc2观察、生命周期与真实报告；不声称上游认可或所有Core／补丁／设备兼容。
