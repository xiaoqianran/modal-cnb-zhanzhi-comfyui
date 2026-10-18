# v1.98.0 · H09／Veda R2VA 已审配方（EXP）

保存[9张短名工作流](../examples/workflows/86-h09-reviewed/README.md)，对应7项人工接受的具体案例。
旧697个节点的接口、默认值和注册顺序保留，追加23个入口至720；旧工作流不覆盖。

- Veda R2VA新增独立Bundle／Apply／Audit，预测器读取`models/veda_r2va`，生成区和参考区预算分别处理；旧T2VA不变。采用T8 Flex，不是作者INT8，也不承诺提速。
- FreeVideo新增独立prepared ConvRot INT8路线，四档采样、Stage保存／冷加载和外置LoRA／EAV／Prompt Relay；Light为LOW8＋外置learned1.2×＋HIGH3。旧FP8、8+2、4+4及四档入口不替换。
- Person Remover V1提供逐帧外部MASK预览、窗口计划／选择、原生条件、累计音画等分离入口。绿色参考不是采样mask，原声须显式旁路；不回贴输出或承诺像素锁定。
- 原声全局PCM切口／DRIVE与FINAL分离；已验证原声两段2.5秒，不做ASR／TTS或自动声纹识别。
- 参考包显式有序Join后继续使用旧Route，保留图像／声音的独立开关，不伪转换外部RefMod强度。
- 可选FreeToken提案使用独立prepared Qwen3-VL-4B，默认保原稿，显式采用前核请求和提案身份，不自动更换对白／事实或排队。
- 制作配方复用导演台候选／原稿流程，新增同源白名单模块路由，兼容插件目录改名；不改用户素材接线或自动采用候选。
- 分支安全追加原生Guide，保留每条条件分支自己的旧锚点、参考及区间；不修改共享ComfyUI Core。

## 已验收范围与限制

2026-10-11七项人审：Veda Dense／Sparse、FP8／INT8 Light8+3、原声切窗、人物移除续接、导演候选、参考Join路由、文字提案。
生成案例完整5秒、基础864×480（0.41472MP），双采HIGH实际1024×576；原声切窗各2.5秒，后三个文字／路由条目不冒称生成视频。
来源画布已保存、导出API、关闭重开并实际执行。公开模板仅适配资源入口和拆出完整依赖分支，未再次执行，不继承新素材质量资格。

人物工作流需ComfyUI-VideoHelperSuite读取逐帧MASK目录，并需要来自相同素材及生成历史的**四份准确原生AV前缀检查点**，只续接W4／W5；不是从零六窗生成图。
参考图A/B来自同一素材的F0/F60，C视觉关闭／原声保留；输入检查点未采样。提案通过的是指定格式整理／原稿保留，不证明场景改善、图片模式或普遍事实准确。
EAV代表例为`report_only`，不认证增强效果；两种精度所用作者版本不同，不是严格单变量性能比较。

本次发布复用既有CPU／小内核／原生画布及人审证据，只新增发行副本／归档的安装与兼容性检查，不重复采样或旧CPU矩阵。
Frozen Cache仍为[未实现的条件研究](H09_FROZEN_RESEARCH.md)，不包含缓存节点或性能承诺，不把全部H09研究标为完成。
模型、原素材、运行配置、检查点、失败样片、人工反馈及私有roadmap／SKILL不上传、不打包。GitHub发布和Comfy Registry审核／可安装状态独立。

## 来源与感谢

感谢[Veda-Sparse／Miowtion](https://github.com/veda-sparse/Veda-on-ComfyUI)、[FlashML-org／FreeVideo](https://github.com/FlashML-org/FreeVideo)、
OpenVDN、[Akatz Labs](https://huggingface.co/akatz-ai/MiniMax-H3-Person-Remover-LoRA)、[wordbrew H3 Toolkit](https://github.com/wordbrew/ComfyUI-H3-Toolkit)、FreeToken、Qwen与MiniMax作者。
代码和模型许可分别适用；原有第三方署名与许可保留，不捆绑上游权重或Sage派生INT8内核。详见[第三方说明](../THIRD_PARTY_NOTICES.md)。

## English

Seven specifically accepted cases, nine saved short-name templates and23 additive nodes (697→720).
Independent Veda R2VA Flex, prepared FreeVideo INT8, separated Person Remover windows, source PCM cuts,
reference joins, optional unadopted FreeToken proposals and retained Director drafts. Old workflows,
schemas/defaults/order, FP8/4+4 routes and external EAV/Relay remain intact. Person resume requires four
matching native prefixes; text/routing approvals are not generation, identity, speed or all-input certificates.
Frozen Cache remains conditional and unimplemented. No bundled weights, private evidence or automatic adoption.
