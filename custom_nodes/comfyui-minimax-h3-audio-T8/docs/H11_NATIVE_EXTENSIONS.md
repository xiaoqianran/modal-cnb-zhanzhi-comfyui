# H11 原生增量（实验）

保留旧工作流／参数；新增入口不会自动安装、下载、改稿或排队。
v1.99.0新增入口；2026-10-12七项人工审核通过，[八份已审来源工作流](../examples/workflows/87-h11-reviewed/README.md)已保存。验收仅对应本例完整媒体／接口，不代表所有模型、双采阶段或硬件；资源路径适配未重新采样。

## Spark：已有模型的显式注意力补丁

感谢 [zechengtang/Spark-H3 v0.1.2](https://github.com/zechengtang/Spark-H3/releases/tag/comfyui-v0.1.2)。
不需要新的训练checkpoint；T8只使用固定官方 backend/reblock 数学模块，不注册作者整套Sol/BSA/cache节点。
本机实际使用Python3.12、Torch2.10/cu130、RTX4060Ti SM89和
`comfy-kitchen 0.2.37+spark.h3.sm89.cu130.1`。其他ABI／GPU没有借用本机资格。

`tools/prepare_h11_spark_runtime.py` 显式读取官方ZIP、核内容SHA并准备运行时清单。
默认不安装；`--install-main` 是明确替换主解释器轮子的操作，先备份原包和dist-info。
本次应用户要求装入主环境，仅此distribution变化，没有升级Torch或修改Core。

接线：选定MODEL→Spark Apply→原有Guider／Sampler；该阶段实际SIGMAS同时接Apply。
LOW/HIGH分别Apply，不串联共享逻辑step状态。EAV／Relay／Bridge保持外置。
已有block owner／mask／bias／未知callable保留并委托；因此不保证所有层都稀疏。
真实kernel错误直接传出，不回退成dense成功。Audit必须依赖采样后latent，
`actual_sparse_calls=0`只说明委托，不是Spark验收。

实际逻辑step取current sigma＋完整sample_sigmas，不按forward次数；同sigma额外EAV调用不前进step。
源ZIP SHA `88a2e15be0b6f61ffb62ff1236ffe24f12190e5adbd0058fec110423c4aea770`；
所选轮子SHA `76f2bbeeeb111b70666ac841279a0a006d931f439e617b95bd9a3dbab5731620`。
已完成同配置5秒Dense/Spark真实UI各一片，Spark343次实际稀疏、57次明确dense预算委托，0异常。
两次cold/cache/compile状态不同，不给提速百分比。本例两段完整音画已获人工接受，不推论其他硬件或模型。

## Wuli：原生8步与4步不是同一份LoRA

感谢 [Wuli-art](https://huggingface.co/Wuli-art/MiniMax-H3-Turbo) 和
[sandpies原生ComfyUI转换](https://huggingface.co/sandpies/Wuli-MiniMax-H3-Turbo-ComfyUI/tree/82f86823abcd6288370d73bc19a98e636282ad28)。
只接固定4／8步资产，不默纳入作者后续6步、HQ、unlocked或hybrid混合。
已是Comfy格式，不另造Diffusers加载器或forward计数头库。

| 配方 | 原生文件／顺序 | 时钟与轨迹 |
| --- | --- | --- |
| Native8 | UNETLoader选择完整Wuli8；实际25列AdaLN，不是普通8列pruned | video12/audio3、simple8、Euler、CFG1、denoise1 |
| Native4 | 原始full FL2VA→trunk→heads_widen→heads_set，三文件强度1 | video6/audio3、simple4、Euler、CFG1、denoise1 |

`Wuli8 Recipe`仅明确原生clock/grid/sampler；普通模型加载器仍外置。
25列shape不是整模型SHA证明，不按文件名自动换模型。能力卡显示这一边界。
`Wuli4 Compose`核三原件完整SHA，用Core现有LoRA parser按顺序追加；
缺文件／错SHA／实际目标未完全映射会报错，不禁止合法manual加载或用户附加补丁。
trunk单独不是完整四步；widen负责真实reshape，set是绝对head bank，不是任意强度风格混合。
Core已有sigma＋sample_sigmas的头选择。8／4首次各仅一条约0.4MP完整单采5秒，
不为测试强加未经资格的二采1.2×。partial/HIGH/resume可接原生接口，但不自动授作者配方资格。

## 只需音频VAE的参考入口

`Audio-only Reference`明确稳定role、standalone或paired-video来源与Qwen-only grounding。
Qwen可看图／视频，DiT只收到原生音频latent；没有video VAE编码。
paired来源保留标记及原PCM，不自动改成另一人物的独立音色；来源按声明顺序映射Audio编号。
这是执行内准备件，不是新的持久参考包格式；旧Reference Create／Route／Conditioning不变。

`No-visual-latent Conditioning`输出普通positive／AV latent和原生raw text recipe，
Sampler、Bridge、EAV和Relay可以继续外置。DRIVE、FINAL、voice reference分别连接；
`reference_only`不把voice自动注入驱动；FINAL只透传，不自动覆盖采样生成音频。
不认证声纹锁定、人物像素保真或长窗接缝。新增数值路径仅一条5秒定向验收，
原Ref2VA完整轨迹，不拿FL2VA加速模型的结果冒充这个分支。

## FreeVideo阶段报告

原FP8／四档／INT8 source pins、配置、sigma、NFE、内核及旧回执验证不改。
两个现有worker仅加host phase记录：preflight、imports/conditioning、tables/policy/LoRA、
engine load、sampling、latent validation/transport、release和receipt integrity。
有界`phase.json`允许查看加载过程；阶段切换绝不推进NFE，只有原step callback记录完成。

Quality／INT8的画布还会出现可关闭的“FreeVideo 实时阶段”只读提示：准备输入、
核源码、加载模型、采样及收尾分别显示；实际NFE仍来自原Core进度回调。
第一步可能包含编译，提示不把加载／host秒数变成采样百分比，不推算ETA，
不中断／自动重启。提示不修改节点控件、尺寸或序列化值，旧图无需重接。
worker写回执后仍等待父进程SHA／原生Stage核验，不能仅凭阶段“收尾”判成功。
未知第三方progress callable仍保留原调用，不额外挂观察钩子。

Phase Card只接经原验证器验证的完成Stage。load／sampling／H2D来自作者现有计时；
compile只读已存在的PyTorch host counters，不调用编译器、不加CUDA同步。
VAE／mux接明确对应报告才显示；这些外部JSON是用户明确提供的报告，不是Stage自动认证的媒体耗时。
旧收据或未测字段是不可用，不是0。
并行／nested host/CUDA计时不能相加或推算端到端提升；不虚报ETA，不自动重启、idle compile或更新源码。
新增遥测的worker源码剥除独立遥测语句后，与原数学／request／sampler AST一致。

## Bridge参数侧车与镜头提案票据

Sidecar Preset读取Trainer schema1的`inference_settings.json`，核完整选定权重SHA；
model_file只是label，内嵌固定application_contract优先。坏SHA、NaN或公式冲突拒绝这个提案。
默认不采用；明确采用只输出现有BridgeConfig，不自动Apply。原Legacy0.10、chunk256、
既有内容SHA预设和多桥顺序保留。0.12／training bounds／trial alpha不是视频校准或最优值。
来源：[T8 Semantic Bridge Trainer v0.2.2](https://github.com/T8mars/MinimaxH3_Semantic_Bridge_Trainer-T8/releases/tag/v0.2.2)。

Scene Ticket沿用旧FreeToken Request／provider，只追加scene_id、scene_revision、request_id与request SHA绑定。
新异步提交需明确新request_id。Rewrite在发出前绑定票据；返回仍归原镜头历史。
Adopt默认保当前原稿；镜头／版本／请求不符的迟到提案可看，但不能采用。
它不自动维护导演台事实，不上传云端；旧三个节点与prepared配置不变。
