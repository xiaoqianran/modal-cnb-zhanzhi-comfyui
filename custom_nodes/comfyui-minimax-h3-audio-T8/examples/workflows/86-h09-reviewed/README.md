# H09 / Veda R2VA：已审来源工作流

普通提示词副本：[本目录原版→普通版对照](../PLAIN_PROMPTS.md#86-h09-reviewed)。本目录 `*_普通提示词.json` 按原功能、采样和阶段命名，与原图同目录。完整描述一次填写，各阶段可分别编辑；原图保留。

人物前缀续接图的逐帧MASK目录读取使用外部`VHS_LoadImagesPath`，需要安装ComfyUI-VideoHelperSuite；该依赖不随T8发行包捆绑。其余模型、素材及检查点按下表自行配置。

以下7项来源案例于2026-10-11人工审核通过：A1–A4／B1为集中反馈revision15，B2／B3为定向复审revision3，共保存9张图，随[v1.98.0](../../../docs/RELEASE_1.98.0.md)交付。短名图保留实际保存图的采样参数、接线和音轨；只调整明确的资源路径、添加说明，或拆出已执行的独立分支。原图不覆盖，资源适配版未重新执行，不保证换素材后相同效果。

|工作流|用途与配置|
|---|---|
|[A1_Veda_Dense.json](A1_Veda_Dense.json)|864×480／8步／5秒dense基线；选择自己的参考图、Ref2VA／Turbo／Qwen／双VAE。|
|[A1_Veda_Sparse.json](A1_Veda_Sparse.json)|同例R2VA Sparse，32/32预算、显式nearest_exp；预测器放`models/veda_r2va`。不是作者INT8或提速认证。|
|[A2_FreeVideo_FP8_8plus3.json](A2_FreeVideo_FP8_8plus3.json)|原FP8 Light LOW8 → 外置learned1.2× → HIGH3；节点4选择实际prepared FP8 t=1配置。|
|[A2_FreeVideo_INT8_8plus3.json](A2_FreeVideo_INT8_8plus3.json)|独立INT8 Light路线；节点4选择自己的prepared INT8 t=1配置，不填FP8配置或Core单体模型。|
|[A3_Source_PCM_Windows.json](A3_Source_PCM_Windows.json)|从已成功画布独立拆出的原声切窗分支；24fps／5秒原片切成两段2.5秒，FINAL原声／DRIVE右补零，无H3采样。|
|[A4_Person_Prefix_Resume.json](A4_Person_Prefix_Resume.json)|已有四个原生AV检查点续接，仅W4/W5各12步。**不是从零生成图**；先配置逐帧MASK目录、干净首帧、原片及四份匹配检查点和完整SHA。|
|[B1_Director_Candidates.json](B1_Director_Candidates.json)|从已成功画布拆出的三镜候选／原稿展示；候选active=false，不自动采用，不生成持物交接视频。|
|[B2_Reference_Join_Route.json](B2_Reference_Join_Route.json)|独立参考Join／Route／原生条件分支；A/B取原片F0/F60，C视觉关闭、完整原声保留。不采H3，输入检查点仍未采样。|
|[B3_FreeToken_Proposal.json](B3_FreeToken_Proposal.json)|原稿→待审提案→显式采用；节点2选择自己的prepared Qwen3-VL-4B配置。默认confirm_adopt=false，审核通过不等于自动采用。|

FreeVideo原例LOW864×480（0.41472MP）→ HIGH1024×576；保留原生124帧后显式裁到120帧／24fps／5秒。HIGH的尺寸由放大器连线输入，未连入的旧显示控件不是实际生成尺寸。LOW／HIGH的EAV、Prompt Relay继续外置，EAV仅`report_only`，不宣称增强效果。两路作者版本不同，不是严格单变量精度／性能对照；没有四档／七任务或普适多窗对白的新质量资格。

人物移除需要同源一帧一张MASK，目标眼镜、散发、手中道具也须覆盖；不自动分割，不把绿色RGB当采样遮罩，不回贴输出，不保证未遮区域像素锁定。四份prefix必须来自相同模型、VAE、源时钟及自己的匹配生成历史；路径／SHA故意留空，避免误加载本机研究文件。不要拿有损MP4代替原生AV检查点，也不要直接运行空配置。新素材从零生成需按[人物移除用法](../../../docs/H09_PERSON_REMOVAL_EXP.md)搭完整窗口链，不能继承本例前缀或人审结论。

原声切窗的cue仍为空，仅验证这份原PCM切片，不认证自动句边界／双人声纹。导演台通过的是原稿保留与候选展示，不等于采用候选或证明20款风格效果。B2接受的是这份输入预览和有序路由，A/B来自同一双人素材，不证明个别人声锁定；B3接受的是这一份文字格式整理和原稿保留，不证明场景／画质提升、图片模式或所有改写。旧反馈、失败和旧工作流保留。Frozen Cache仍为条件研究、未实现，不包含在这9张已审图里。

参考：[Veda R2VA](../../../docs/VEDA_R2VA_EXP.md)、[prepared INT8](../../../docs/H09_FREEVIDEO_INT8_EXP.md)、[原声规划](../../../docs/H09_SOURCE_AUDIO_PLAN.md)、[制作配方](../../../docs/H09_PRODUCTION_RECIPES.md)。感谢Veda-Sparse／Miowtion、FlashML／FreeVideo／OpenVDN、Akatz Labs及MiniMax作者；权重和输入素材不随示例捆绑，各自许可独立适用。

新增用法：[参考Join／Route](../../../docs/H09_REFERENCE_JOIN.md)、[FreeToken提案](../../../docs/H09_PROMPT_PROVIDER.md)。感谢wordbrew H3 Toolkit、FreeToken及Qwen作者的相关公开工作；这里不复制RefMod MODEL hook算法、不捆绑模型权重。
