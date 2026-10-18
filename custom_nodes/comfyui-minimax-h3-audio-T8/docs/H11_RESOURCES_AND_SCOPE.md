# H11 资源与去重边界

## 可用资产配方，不另造加载器

[Sam Wasserman的80s Horror v1.0.0](https://github.com/wassermanproductions/wasserman-80s-horror-lora/releases/tag/v1.0.0)
是rank16、149144792字节的ComfyUI格式风格LoRA。使用现有LoRA Model Only loader；
作者起点强度1.0。`80s_horror_wk, shot on VHS.`和`80s_horror_wk, shot on 16mm film.`
是两种明确提示路线，不保证所有底模／附加LoRA组合都同效果。
作者资产SHA `9e8e820be3e1ad04ce904c0b3c774d08297bfde4341f5cce6fb47cb00451a8ac`。
这份资源卡不代表本地新风格视频验收；不照搬大尺寸／长片示例，不捆绑权重。
代码／文档Apache-2.0，权重为MiniMax H3 Community License，分别保留作者署名。

## 已有能力优先复用

| H11方向 | 实际入口／取舍 |
| --- | --- |
| 多人物与原声 | 既有Source PCM全局Plan/Window、Reference Join/Route；新增audio-only，不混DRIVE/FINAL |
| mask／人物／cut／道具 | 既有Person/Face/VM01、导演台连续账本及Prop Continuity Lint；同源片、mask与接触表供人审，不自动判画质 |
| 长片续接 | 既有accepted-picture尾39→RGB resize→LOW VAE、context22；旧independent_low_x0不改 |
| 模型格式矩阵 | 既有bounded header/ConvRot/LoRA能力卡，加Wuli四文件角色与25列／四头诊断，不按名字自动reshape |
| 加速配方 | Spark与Wuli增量；FastH3已审图保留，不重做全步数矩阵 |
| Veda R2VA | 既有Dense/Sparse接受及实际delegate审计；不从attention局部提速推整片性能 |
| working set | Spark独立显式Apply与FreeVideo phases；不自动改allocator或全局attention |
| UI/API | 新图实际Save／关闭／保存树重开／UI export／Run；无通用自动修JSON |
| 事实与异步提案 | 既有protected literals／默认保原稿／显式adopt；补scene/revision/request ticket，迟到回覆不跨镜采用 |
| 恢复 | 既有CAS/native NFE/Stage完整性与缺文件错误；autosave JSON不是计算断点，MP4不是native Stage |
| 放大 | 既有learned/LTX/RGB/FreeVideo HIGH保LOW音频；不替换既有放大器 |
| 交付 | 既有strict publisher/后处理packet与PCM/PTS检查；新验收卡明确native124与交付120、24fps及0–5s裁齐 |
| 外部参考库 | 既有v4/v5 RGB/PCM import、Join/Route；R01/JPEG包须实际样本与来源，不能伪造VAE等价 |

H3导出原始PCM样本一致、LATENT一致、AAC有损重编码、音频包复制是不同证据。
绿色参考图不是sampler MASK或像素锁定；所有接触表必须来自选定同源实际媒体。

## 条件项目不伪报完成

HarleyQ/Rent/角色与声音权利未证，不自动下载或分发。Union2 W4A8沿已有Loader/Apply；
真实权重/header/消费算子与当前硬件另核，不因文件写W4就授CUDA资格。
Wuli后续HQ/unlocked/6-step/混合路线另立明确配方，不静默塞进本批。
W6无已证consumer、mmgp非T8模块；AMD/Apple/SYCL/Ascend/多GPU需相应实际硬件。
Apple VOSR非商用路线和大型Omarchy整合包不纳本机Windows NVIDIA首批。
训练框架不等同本项目推理功能；QuantFunc/Nunchaku不恢复，暂停的Sol/Strata及H09 Frozen Cache不动。
