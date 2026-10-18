# H09 Frozen Cache 启动条件（尚未实现）

这是条件候选，不是已完成的缓存节点，也不默认加入人物移除或原声精修。

## 已核来源

实际实现为 [fblissjr/ComfyUI-h3-explorations 的 frozen_video_cache.py](https://github.com/fblissjr/ComfyUI-h3-explorations/blob/7e1285ee93c528e47e7fbbca7d9d10f367764e42/frozen_video_cache.py)：Git blob `97a6732a50713fc69542236793ffcbc76adfb781`，44627字节，SHA256 `f96f027c79a74fb3d6febd04d82f6ccd1b4b5aab101077aae4543f6e0c4c9df9`。符号包括 `_gate`、`_rows`、`_make_diffusion_wrapper`、`_cached_block` 和 `attach`。已读选中实现／准入及 MIT 许可，未执行、复制进运行路径或运行作者bench。它另保留 Adudeguyman MIT 派生部分的署名。

不要把 `3550496` 计时记录提交冒充恢复实现 pin；0.226撤回磁盘mask／窗口成片复用也不等于这个 session内在线近似缓存全撤回。

## 与当前人物移除的差别

作者从 **Core实际传入** 的 denoise_mask/audio_denoise_mask 判断冻结行：无mask、无混合生成／冻结、live share超0.5或有context_window等情况回stock。先完整构建每层hidden，后续只重算live行，冻结hidden不再响应变化行，这是近似，不是逐位等价。

T8人物移除当前明确 `sampler_mask_attached=false`，绿色RGB guide不是denoise mask。不能为了让缓存命中把人物遮罩擅自接成采样mask，或把有历史／参考直接当成大比例冻结。先在真正的原生执行中核实际mask／layout／调用，再决定是否存在适用冻结任务；静态接线不能冒称缓存已命中或必然加速。

## 后续只在前置满足后继续

人物移除原配方完整成片先通过；确有适用的混合mask任务及采样瓶颈后，才开发独立 opt-in Cache Apply／Audit。原图默认off，Stage／磁盘复用身份与这个运行内缓存分开。

只做一组同配置off/on，记录实际build/cached/stock调用、完整采样及端到端时间、host RAM和VRAM、遮罩边界／主体／音轨。没有明确端到端收益或质量有损就停止，不加大量seed／模型矩阵。作者11.32–14.60GiB是host RAM，不是显存；30–42%不是本机成绩。

未知用户hook组合保留／委托并报告unverified，必要时只禁用本缓存回原实现，不能沿搬作者准入硬禁用户使用整张图。真实坏尺寸、内容身份或内核错误仍正常抛出；不清空LoRA／DiT hook来制造缓存“兼容”。这项前置尚未满足，不能在“全部完成”里偷偷打勾。
