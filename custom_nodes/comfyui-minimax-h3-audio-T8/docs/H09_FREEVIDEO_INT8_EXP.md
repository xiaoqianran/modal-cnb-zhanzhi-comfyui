# FreeVideo prepared INT8（EXP）

当前交付：独立INT8节点及指定已审来源图随[v1.98.0](RELEASE_1.98.0.md)发布。下方“尚未发布”是来源验收时的历史状态；旧FP8／4+4路线及四档／七任务资格边界保持。

这是新增的独立执行路线，不替换旧FP8、8+2、4+4、四档质量或audio-v3。
原生ComfyUI单体模型不能改名当成prepared INT8；已有FP8 Stage也不能转标签继续HIGH。

## 模型与运行时

- 引擎：[FlashML-org/FreeVideo](https://github.com/FlashML-org/FreeVideo/tree/ebc94ecdeec3cbfe74040fe69a5116a62bf01dcd)，v0.3.20固定提交。
- 模型：[OpenVDN/vdn-minimax-h3-edge](https://huggingface.co/OpenVDN/vdn-minimax-h3-edge/tree/da37681f5a1f7015fdb63482142b865111b687d3/int8-convrot/cache)，独立`int8_convrot`目录，278文件，共22,929,329,625字节。
- rowwise INT8、ConvRot group=256；原件逐文件完整SHA检查，不二次转换或下载整个模型仓库。
- 复用精确匹配的隔离Python／VDN依赖和纯JSON模型结构，不复用FP8主体、配置身份或内核资格。
- 下载不发生在Loader内。`prepare_h09_freevideo_int8.py`显式下载原件；`prepare_h09_int8_runtime.py`创建新的运行配置。仅`--probe-only`生成的文件不是可加载模型。
- 需要自己的`linear-int8`旋转／量化／GEMM和cuDNN探针，`probe_h09_int8_kernels.py`每种只做一次小探针；旧FP8“finite”不算INT8证据。来源、环境及日志改变时重新检查资格，未变不重跑。

专用配置默认为`ComfyUI/user/default/T8/freevideo-runtime-int8-v1.json`，也可在新Loader明确选择路径或设置`T8_FREEVIDEO_INT8_RUNTIME_CONFIG`。旧环境变量和配置不变。

## 八个独立节点

新Loader → 可选INT8 LoRA／EAV／Prompt Relay → INT8四档采样。

| 质量 | 终态与接线 |
| --- | --- |
| Light | 完整LOW8 → Stage Save（可选）→ 外置latent放大 → 独立HIGH3 → 解码 |
| Standard／High／Max | 12／16／20步单采终态，直接解码，不接Light HIGH3 |

Stage Save／Load使用新的INT8自有类型及内容收据。HIGH3要求Light完整LOW8，保持其音频逐值不变，不能接任意LATENT或未完成MID。
EAV／Relay外置、LoRA按顺序追加；零强度不增加权重效果。未知用户组合按补丁策略报告，不以“未认证”阻止执行；真正的靶点／尺寸／坏SHA／缺内核错误正常报出。
外置多事件Relay已有独立INT8计算身份绑定的masked-attention小探针；它不是多窗对白成片通过资格，不能把单事件透传称为多窗对白已通过。

## 预算与执行证据

向作者planner传实际`precision=int8`、几何、步数、参考video/audio token数及LoRA工作区，保留其stream／pin／resident选择。不能为避免OOM静默缩尺寸、减步数或改音轨。
HIGH3的原LOW表先移CPU、换入三步表；GPU预算按较大表而非两套相加，额外host内存仍需实测。
每次隔离执行核安装的`Int8Linear`及真实INT8权重／scale形状，并委托记录实际成功ConvRot／GEMM调用及逐NFE覆盖。不修改forward或清除LoRA/hook，不把“全部靶点已安装”写成“全部靶点都实际执行”。异常正常传出、观察器恢复、输入和来源再次验SHA后才生成完成收据。

## 当前验证边界

独立节点、Stage内容／冷热保存、外置描述符、资源策略和实际调用观察器已接入。新增／受影响CPU合同通过，旧共享源码和工作流不变。
Windows RTX4060Ti上已完成一个小形状INT8探针及一个cuDNN探针；不是整模型运行、提速或画质认证。
整套278原件已完整准备；新增alltasks-v3配置包含四档及`t2va/i2va/l2va/fl2va/ref2va/ref2va_audio/ref2va_av`所需20组去重后的作者精确表，2589项实际库存及独立Loader合同核验通过。新配置不覆盖旧INT8-v1或FP8配置；表准备完成不等于七种任务全部成片验证。
实际计算环境与原两个小探针一致，未重跑它们。另做恰一次带加性bias的cuDNN小探针（Q=131，K=519，分块128+3），相对CPU FP64 RMSE约0.000174，完整结果绑定INT8计算身份，不借用FP8日志。
已完成一份真实画布Light双采：LOW864×480／8步 → learned1.2×实际1024×576 → HIGH3，交付120帧／24fps／5秒H264音画。保存、API导出及关闭重开输入一致；两个Stage冷加载内容校验通过，HIGH音频与LOW latent逐值一致。实际逐NFE量化调用及外置多事件Relay有执行证据，EAV仅report_only，不宣称增强效果。全片帧与音频完整解码通过；2026-10-11集中反馈revision15的A2已接受这份Light8+3音画案例，不扩大到四档／七任务或全部Relay对白资格。
同条件FP8样例也已出片并在同项获接受，但两路作者版本不同，不是严格单变量精度或性能对照。[FP8／INT8短名图](../examples/workflows/86-h09-reviewed/README.md)已保存，只将私有runtime路径留空供明确选择，原参数／外置效果接线不变，资源适配版未重新采样，尚未发布；其他未审研究图不收入推荐配方。
编译、传输、采样、解码和端到端分别计时；host RAM、VRAM、磁盘分别计量。作者其他系统／大卡数据不能当作本机收益。

代码与模型许可分别遵守，模型不随插件分发。感谢FreeVideo／OpenVDN及MiniMax作者。
