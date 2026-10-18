# H09 可选 FreeToken 提案（实验）

当前交付：三独立提案节点、准备工具及指定格式整理图随[v1.98.0](RELEASE_1.98.0.md)发布。仍默认保原稿，旧候选／待定是历史证据，不因发布而自动采用或升级事实资格。

三个新增分离节点：**原稿与图片声明 → 单次待审提案 → 显式采用／保原稿**。这是 FreeVideo 内的 FreeToken portable ops＋Transformers 子集，不是完整 FreeToken 平台，更不是新的 H3 模型或现有 Qwen 编码器的替换品。

2026-10-11定向复审revision3／B3通过这份文字格式整理及默认保留原稿：[独立短名工作流](../examples/workflows/86-h09-reviewed/B3_FreeToken_Proposal.json)。只清除本机prepared配置路径、添加使用说明，接线／原稿／字面对白保护／confirm_adopt=false不变；适配版未重复执行，尚未发布。人审接受不等于自动采用或证明场景改善。

## 资源准备

固定 FreeVideo 源 `ebc94ecdeec3cbfe74040fe69a5116a62bf01dcd`；作者 `prompt_vlm/model.json` 指定 [Qwen3-VL-4B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct/tree/ebb281ec70b05090aa6165b016eac8ec08e71b17)，revision `ebb281ec70b05090aa6165b016eac8ec08e71b17`，12文件共8,887,284,080字节。它需要原 HF 模型／tokenizer 格式，不能把现有 ComfyUI FP8 Qwen 文件改名顶替。

显式运行 `tools/prepare_h09_prompt_provider.py`，给出 `--source-root`、`--model-root`、`--python`、`--home` 和新 `--output-config`。使用已匹配的隔离 Python，缺件才下载；全文件核SHA，有界Range续传，保留8GiB磁盘余量。不安装依赖／启动器，不在节点内下载，不覆盖旧配置。源／模型／自有实现与解释器核SHA，依赖版本另绑定；不是全部 site-packages 字节的安全签名。

## 画布用法

1. Request 填原稿、1–60秒和 `protected_literals_json`，例如 `["你好，今天天气不错。"]`。保护内容必须是原稿中的字面子串。
2. 可选接 CPU float32 RGB IMAGE batch（总上限256MiB），`image_roles_json` 逐张列 `first/last/reference`，最多8张。不把 reference 与 first/last 混用；first会按原作者规则排在last之前，普通参考保原顺序。不接受视频／音频混合输入。
3. Rewrite 明确选择新 prepared 配置，产生 pending proposal、候选文字及报告。每次运行独立子进程，offline HF、`trust_remote_code=False`；正常完成、取消、超时或失败只释放该进程树。没有常驻模型。
4. Adopt 默认 `confirm_adopt=false`，仍输出原稿。确认后才选候选；原稿／参考像素／提案内容或来源身份改变会拒绝旧提案。它不自动改现有导演台事实、LoRA、素材接线或队列。

最小文字接口 `tools/run_h09_prompt_proposal.py --config 配置.json --request 请求.json --output-dir 新目录` 只生成新候选文件。请求字段为 `text/seconds/protected_literals`，不会自动采用或采H3。

## 不把格式检查当作事实确认

作者 validator 主要检查段落、时间与媒体标签。T8追加字面对白／歌词／文字出现次数保护，并拒绝未声明的 `<d>` 语音；但无法自动判定所有新增视觉事实、未标记对白、持物手、动作或因果。文字改写也可能增加原稿没有指定的细节，必须看候选再选，不将推测写成已确认事实。

首个CLI文字案例真实CUDA执行，但候选新增“右手拿杯”等细节，未采用，不作质量通过。第二个更明确的请求已真实画布保存／导出／关闭重开并运行成功：92输出token、rewrite约20.875秒、worker约96.062秒、峰值allocated约9.00GB、0 allocator OOM，子进程退出。画布整体375.39秒包含原件完整哈希等准备，不能冒称纯推理耗时或加速。候选保留正常中文句子一次，默认输出与原稿逐字一致、未采用；上述定向反馈接受这一份格式整理与原稿保留。这不是H3采样、图片模式资格或优于原稿的证明，不替代原导演台或自动开全局改写。

感谢 FlashML-org/FreeVideo、FreeToken 和 Qwen 作者。portable ops 原始来源 [FreeToken固定提交](https://github.com/FlashML-org/FreeToken/tree/555efd89447232a555e05d187256b76a51c1aaa0)，Apache-2.0；源代码与模型分别保留各自许可和署名，不随插件捆绑权重。

2026-10-11用户对B3标“待定：啥也没看到啊，不明白啥意思”。新定向表并排显示实际原稿／候选，并提供中文释义（不是节点原始输出）。本次正文与原稿逐字一致，只增加`integrated_multimodal_description: [Shot 1]`、环境声N/A和配乐N/A；不是场景／画质提升证明。默认下游仍为原稿，无新提案或H3采样；人工语义接受仍待确认，不代替用户采用。

后续同日新定向反馈revision3明确pass，取代上述待定状态；旧反馈和未采用的首个问题候选仍保留。新图的节点2配置故意留空，需选择自己用准备工具生成的准确Qwen3-VL-4B配置，不能用旧ComfyUI Qwen权重路径替代。默认仍保原稿，必须逐次查看新素材的候选后再显式采用，不把本例接受升级为全部改写的事实认证。
