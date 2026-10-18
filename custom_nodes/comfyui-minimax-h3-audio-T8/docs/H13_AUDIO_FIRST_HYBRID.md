# H13 AudioFirst 与 Wuli Hybrid（实验增量，两项人工审核通过）

不替换旧 Speech、Source AV、Wuli4/8、FreeVideo 或任何已有工作流。
新增两个 AudioFirst 辅助节点；Wuli Hybrid 已是 ComfyUI 原生单体，沿用加载器。
两段实际成片已于2026-10-15通过用户审核；CPU合同、实际GPU与人审分别记录，不以其中一项替代其余项。
已审来源工作流见[88-h13-reviewed](../examples/workflows/88-h13-reviewed/README.md)，旧图和默认值不变；此增量随v1.100.0发布，Registry可安装性须另行确认。

## AudioFirst 怎么接

1. 原完整画幅条件与完整空 AV latent → **AudioFirst · 同条件Tiny投影**。
   第一期只支持 T2VA 或单首帧；首帧时同一原图接入原条件和新投影的 `first_frame`，
   `video_vae` 重新编码32×32。不是缩小旧 latent，不重复 Qwen/CLIP 编码。
2. Tiny positive / tiny AV → 外置普通采样器。它完成完整轨迹，生成音频。
3. 原完整空 AV 与 Tiny 完成输出 → 原 **Source AV Prepare**：
   `video_mode=regenerate`、`audio_mode=lock`、两种 strict，音频不补齐/裁切/转换dtype。
4. Prepared AV 与原完整条件 → 外置完整画幅采样器。MODEL、sigma、Sampler、
   Bridge、EAV、Prompt Relay 仍显式接线；Tiny和完整分支分别编译各自效果，
   不把原完整空间/已编译窗口 receipt 冒充 Tiny 资格。
5. **AudioFirst · 实际成片锁音审计** 接三项：Tiny完成AV、prepared AV、
   实际最终AV。核同帧钟、源→prepared音频exact、mask画面1/音频0、finite、
   最终音频最大绝对误差≤固定2e-5。返回最终对象原样，不拿Tiny替换成片音频。
6. 审计后的实际AV分别解码音画，再正常裁片/保存。Tiny解码音频可单独试听。

frame_count取自完整AV，不多填第二份length；24fps视频／40fps音频latent。
例如124帧对应207音频latent步；交付5秒时显式裁视频120帧、音频0–5秒。
固定误差是latent数值合同，不证明对白自然、口型、声纹或最终AAC听感。
接入者还须用实际history确认完整采样，而非拿中间x0当完成片。

多参考、末帧/多关键帧、空间mask/control、Visual Marker与已编译局部窗条件
不能直接投影到32×32；新增入口明确报出未转换字段，旧完整路线保持可用。
普通hooks、未知可执行组合与embedding引用不清空/深拷贝，未知元数据保留且报告未认证。
同一首帧的来源一致性由实际画布接线保证，投影不能从embedding逆推出原图。
不宣称已有 LoRA/Sage/Sol/EAV/Relay 任意组合的效果已全部验证。

项目原 Speech 已能创建32/64/128音频小画幅；本次新增价值是复用已有完整场景条件，
不是又造一套锁音算法或宣称首次 AudioFirst。

## Wuli 普通 Hybrid

[上游固定版本说明](https://huggingface.co/sandpies/Wuli-MiniMax-H3-Turbo-ComfyUI/blob/9df5eccfa095adcdbffba5ba8cbe4c0c66d15a7e/README.md)
：FL2VA unlocked + FlashGen0.5为底，blocks25–49换Ref2VA AdaLN并转换时间基。
只选普通版，完整文件25007719260字节，SHA256：

`a852255134e20112d63a23848be122bd0076e37b9ddac09e436d9d61abbba42b`

下载一份（无须转换，终端中的长文件名不是仓库工作流文件名）：

```powershell
hf download sandpies/Wuli-MiniMax-H3-Turbo-ComfyUI 8step-hybrid/wuli_h3_turbo_8step_v1_flbase_refadaln_b25-49_flashgen050_int8_convrot_hq.safetensors --revision 9df5eccfa095adcdbffba5ba8cbe4c0c66d15a7e --local-dir D:/T8-H13-model
```

用 `tools/prepare_h13_wuli_hybrid.py --source <下载文件> --models <ComfyUI/models> --receipt <新JSON>`
完整验SHA后放到`models/diffusion_models/`。不覆盖已有错误文件；不改Python/Torch/CK。
`UNETLoader`正常选择它，Ref2VA条件可接参考图；不接参考时上游也支持T2VA。
原生shift12/3、simple、Euler、8步、CFG1；不是Wuli4三件套，也不用额外FlashGen LoRA。

完整SHA仅证明所选文件，不能证明后面MODEL没有再被LoRA/其他节点修改。
25列时间表、旧模型metadata和文件名都不能唯一证明Hybrid身份。
Realism合并版、RefLoRA新变体不同，未自动下载或授予效果资格。
未知用户补丁保留；重复已烘焙权重须用户自行注意，不按文件名封禁组合。

## 范围和状态

- 新AudioFirst四CPU合同＋Wuli新反例/受影响旧合同＋导演台两窄合同，共8项通过，CUDA未初始化。
- Wuli三件套资源每次调用重算完整SHA，修复跨任务旧stat缓存误命中；不声称消除后续加载的所有TOCTOU。
- 导演台原生路径本地已有`ui-modules`修复，本批只验收，不重复算新增功能。
- 两段真实画布完整5秒／864×480、120帧／24fps已完成，各只跑一片；完整RGB/PTS及AAC解码通过。
- AudioFirst实际Tiny8步→strict锁音→完整画幅8步，最终音频latent与源exact（最大误差0）；
  实际AAC对Tiny原FLAC的零偏移相关性约0.9981，AAC有损编码不声称逐位一致，也没以FLAC换轨。
- 普通Hybrid真实Ref2VA、simple8/Euler/12:3/CFG1完整出片；不泛化Realism、其他步数或任意HIGH质量。
- 单首帧另用6节点、零Sampler画布核真实VAE32×32输出[1,24,1,2,2]，投影自身CLIP0/VAE1；
  不额外生成第三段视频，不等于单首帧完整影片画质已经人审。
- 2026-10-15集中人工审核r2：A1 AudioFirst、A2普通Hybrid均通过，反馈与原媒体SHA绑定。
  两张短名推荐来源图已保存，执行参数与全部边保持；只更新说明和来源标记，不重采、不重跑已完成CPU合同。
  只确认这两片，不泛化单首帧完整影片或全部外置效果组合。
- Spark0.1.3确有六种wheel，本批不覆盖已验0.1.2；其新适配需另行资格。
- 参考角色、时钟、裁剪、provider确认、输出失败保留等沿用既有功能，不重复造节点。

感谢[AudioFirst作者sepiablue-ai](https://github.com/sepiablue-ai/ComfyUI-H3-AudioFirst-X2-Stream)、
Wuli-art、sandpies、FlashGen作者与Kijai原生转换、smhfacct混合方法。
代码与权重许可分别见[来源说明](../THIRD_PARTY_NOTICES/H13-SOURCES.md)。
