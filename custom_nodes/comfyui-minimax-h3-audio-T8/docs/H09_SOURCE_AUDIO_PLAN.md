# H09 原声切口与角色归属（实验）

当前交付：两独立PCM节点及已审切窗图随[v1.98.0](RELEASE_1.98.0.md)发布；下方“尚未发布”是历史验收状态。原声与旧采样数学保持，不是自动ASR／声音生成。

两个可外接节点：`MiniMaxH3SourceAudioPlanEXPT8` 与 `MiniMaxH3SourceAudioWindowEXPT8`。它们为已有原声准备精确切片，不改旧采样器、Temporal Chunk 对白修复或旧分段拼接数学，不做 ASR／TTS／变声。

## 用法

1. Plan 接 CPU float32 原始 AUDIO（单个 mono/stereo、8–192kHz、上限256MiB）。`cuts_json` 填24fps全局帧端点，如 `[0,120,240]`，必须从0开始且在真实原声内。
2. `voices_json` 显式给出1–3个不同角色 ID 与实际声音参考序号，例如 `[{"role_id":"A","reference_ordinal":1},{"role_id":"B","reference_ordinal":2}]`。这是声明，不是识别或声纹锁定；真实参考仍单独经原 Reference Route 接入。
3. `cues_json` 每项为 `id/role_id/start_sample/end_sample/guard_before_samples/guard_after_samples/text`。sample 是全局原PCM位置，text 是字面台词；呼吸保护范围也必须在请求范围内。不得填估计值后当作对齐已认证。
4. 默认 `strict` 拒绝把切口放在已声明台词／呼吸内部。显式 `shift_after_phrase` 才可在 `max_shift_frames` 范围内向后移动切口，移动记录可见；不会默默跨过下一切口或裁掉台词。
5. Window 同时接 plan、同一 source_audio 与窗口序号：`drive_audio` 接已有 Drive 入口，`final_audio` 是该窗原声精确切片。声音参考不接到这两条音轨上。

DRIVE 为原声片段加可见的右侧静音，适配原生 `5+17k` 帧网格；输出 `native_frames` 和 `keep_frames`，解码视频后显式裁回 keep_frames。FINAL 不含补齐静音、不生成新声音。不要把 DRIVE 当最终音轨，也不要把多余原声尾部悄悄丢掉：report 列出忽略的尾样本数。

两边共用 `round(global_frame * sample_rate / 24)` 全局端点。32000／44100／48000Hz合同验证了各窗 FINAL 能逐样本拼回请求区间的原PCM，避免累加局部取整漂移。44100Hz补齐 DRIVE 的全局长度可能与本地帧时长取整相差1样本；原生编码／最终音画同步仍需真实媒体检查，CPU逐样本保持不等于成片同步或双人归属通过。

实际画布已保存、API导出、关闭重开并执行：864×480／24fps／5秒原片，切口[0,60,120]，32000Hz全局端点[0,80000,160000]。两段FINAL各80000样本，逐样本等于原声切片；DRIVE各97333样本，仅右侧补零。四份FLAC完整解码并按显式16-bit量化容差检查，不冒称导出后float字节相同；两份2.5秒AV全60帧与音轨完整。对白cue故意留空，不声称自动找句边界或双人声纹归属。

2026-10-11集中反馈revision15的A3已通过上述两段2.5秒原声音画。接受范围是这份原PCM切片／试听案例，不是自动句边界、双人声纹归属或新生成声音认证。[原声切窗短名图](../examples/workflows/86-h09-reviewed/A3_Source_PCM_Windows.json)已从成功保存画布按完整依赖拆出，剔除其他待审分支，原执行参数及剩余连线不变，未重采，尚未发布；旧图、音频默认和现有 Reference Route 都保持。
