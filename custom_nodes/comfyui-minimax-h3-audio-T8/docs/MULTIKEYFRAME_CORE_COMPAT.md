# 多关键帧与本机工作流索引维护

## 多关键帧独立强度

新版 ComfyUI 将原先位于 MiniMax H3 `_forward` 内的条件嵌入操作提取到
`_embed_and_pack`。T8 同时识别这两种结构，不因这一重构跳过独立关键帧强度。
适配保留视频／音频遮罩时间步、普通／curve 时间嵌入及原有双时钟输出约定；
默认条件强度须与实际 Core 的前向结果对照，而不是只验证补丁能够安装。

报告中的 `per_condition_forward_requested` 表示请求；`per_condition_forward_patch`
表示实际安装。第三方 forward 保持用户选择，未安装独立强度适配时只提示，不能
谎报启用，也不因为组合未验证禁止用户运行。

CPU 测试使用缩小的真实 Core 网络与随机权重，涵盖条件行、独立强度、遮罩、
curve 及旧 Core 对照；它不替代完整模型 GPU 性能、画质或远端环境验证。

## 本机已安装索引

仓库 `examples/workflows/README.md` 是总目录，含本机可能未安装的分类。
不能为了通过一致性检查而把整个研究目录安装到用户工作流目录。

`tools/workflow_installed_index.py --installed-root <用户工作流目录>` 只输出建议的
`T8_INSTALLED_INDEX.md` 内容。它扫描实际含 JSON 的分类，合并仓库中的重复分类
说明，保留未知本机分类，不改工作流、素材或原 README。

审核输出后，仅更新独立索引；原 README 可追加索引入口，原内容保持。随后运行：

```text
python tools/workflow_installed_index.py --installed-root <用户工作流目录> --check <用户工作流目录>/T8_INSTALLED_INDEX.md
```

新增／移除本机示例后重新生成并核对。索引中的 JSON 数量表示安装数量，不是
模型兼容性或画质验收数量。相关回归仍核对 H3-World 工作流接线、默认参数、
素材存在及本机对应 JSON 与源文件一致；不再错误要求两份总 README 全文相同。
