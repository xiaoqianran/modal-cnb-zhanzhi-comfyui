# H09 参考包显式合并（实验）

当前交付：独立Join节点及指定路由展示图随[v1.98.0](RELEASE_1.98.0.md)发布；下方“尚未发布”是历史验收状态。不扩大为生成质量／多人声纹资格。

新增 `MiniMaxH3ReferenceJoinEXPT8`，把 **已由现有入口验证的** 原生参考包、v4/v5 RGB/PCM 重编码导入结果，按输入包及成员的原顺序合并。它不建立另一套参考库，不再编码 VAE，不修改 MODEL hooks、LoRA 或参考强度。

2026-10-11定向复审revision3／B2通过这份输入预览、Join／Route及条件去向：[独立短名工作流](../examples/workflows/86-h09-reviewed/B2_Reference_Join_Route.json)。来源为已成功的实际画布，分支拆出后仅做静态接线校验、未重复执行；尚未发布，不认证新生成视频或多人声纹。

## 接线

各现有 Capture／Import → Join qualified packages → 现有 Reference Route → Apply／Conditioning。EAV 和 Prompt Relay 继续外置。

例如 A 人物图、B 人物图、C 参考视频及 C 声音分别导入后，Join 的 `merge_roles_json` 填 `["C"]`，显式声明两包的 C 是同一稳定角色 ID。然后 Route 中 A/B 可见、C 只启用 voice：C 视频的视觉路径不会偷偷保留，声音编号由原 Route 实际生成。

默认重复角色会提示明确归组；同角色／同种类／同源内容重复加入会报错，不作为隐式“增强强度”。同类型 VAE producer 必须一致，错误时用当前选定 VAE 重建参考。最多15成员，输入不变，新包拥有自己的 tensor 副本及成员映射报告。

## 外部 RefMod 的真实边界

`refmod_bridge.assess_external(文件, 预期SHA, strength)` 只读核文件与 bounded header，不执行嵌入配置，不自动导入。encode、unit strength 只是可交给现有精确 RGB/PCM importers 的候选；仍需它们的完整数据验证及实际所选 VAE 重编码。

社区 MultiRefMod 的 slot strength 是原 MODEL 参考细节／模糊语义，不等于 LoRA strength 或原生 latent 乘数。非1、trained／未知模式继续保留原外部 MODEL 路线，不伪转换；0明确跳过。现有外部入口及其合法组合没有被禁用。

参考来源：[wordbrew H3 Toolkit 的 multi-node 变更](https://github.com/wordbrew/ComfyUI-H3-Toolkit/commit/a9119c5964419c1c4a8c0b098047f8d322eacd08)。本实现复用 T8 原有导入／包／路由合同，未复制其 MODEL hook 算法。实际44节点画布已保存、导出、关闭重开并执行成功：当前VAE重建A/B图像与C视频／音频，四成员有序合并；Route保留A/B图像与C声音、移除C视觉，原生864×480条件核过。C视频参考显式取22帧，全5秒原声不裁短。未采H3，不能据此认证多人声纹或生成视觉质量；上述定向复审接受的是明确的路由及输入展示。

2026-10-11用户对B2标“待定：啥也没看到啊，不明白啥意思”。因此只改审核展示：实际source第0／60帧并排显示，C原素材供试听，去向表明确两个Picture及一个Audio、C视频视觉关闭。两图来自同一双人素材，不冒称分别裁出角色或声纹锁定；没有新生成H3视频。原反馈保留，待定不写成通过，已通过的其他五项不重审。

后续同日新定向反馈revision3明确pass，取代上述待定状态；旧反馈与展示问题记录保留。独立图仅删除无关PCM／导演台分支，保留所有依赖、成员顺序、Route选择和条件输入，不改变任何保留执行值。选择自己的至少120帧／24fps源片、Qwen和双VAE后再使用；未采样的输入检查点不要当作生成结果。
