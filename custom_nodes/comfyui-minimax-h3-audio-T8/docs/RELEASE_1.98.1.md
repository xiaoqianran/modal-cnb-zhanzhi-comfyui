# v1.98.1 · 已审采样准入记录补齐

补齐v1.98.0已真实运行、人工接受的FreeVideo INT8 LOW、HIGH及共用worker三个精确采样调用记录。
旧128项基线和已审布局退役检查原样保留，未知新调用、同哈希不同路径或已知调用改变仍会使CI失败。
新增一个无依赖CPU回归，核精确三项增量、独立LOW／HIGH及外置EAV／Relay接线、未知调用拒绝。

没有改变节点、模型、采样参数、运行时源码或任何工作流；720个节点、旧697接口、9张已审短名图均保持。
复用原完整5秒Light8+3及人审证据，LOW／HIGH保存内容曾分别冷加载核验，**不声称新增独立冷启动HIGH采样**。
EAV代表例为report_only，不认证增强效果；不新增GPU运行或重复原CPU矩阵。

[v1.98.0功能与限制](RELEASE_1.98.0.md) · [9张工作流](../examples/workflows/86-h09-reviewed/README.md)。
Frozen Cache仍条件研究未实现；GitHub发布不等于Comfy Registry已经Active或可安装。

## English

Records only the three already reviewed INT8 LOW/HIGH/shared-worker callsites missing from the release gate.
All128 previous entries and layout tripwires remain; unknown calls still fail closed. One dependency-free
regression binds the exact delta and independent effects topology. Runtime, parameters,720 schemas and
all workflows are unchanged. Reuses existing acceptance; no new GPU run or cold-HIGH generation claim.
