# H09 制作配方（实验）

当前交付：制作配方工具及三镜候选展示图随[v1.98.0](RELEASE_1.98.0.md)发布；下方“尚未发布”是历史验收状态。仍不自动采用候选或认证生成持物一致性。

这不是新的导演台或自动分镜器。`tools/import_h09_recipe.py` 把用户声明的角色、道具起止状态、允许变化和字面对白，送入现有导演台 Skill／待审候选流程。原稿、素材接线、事实证据和旧编译默认不变。

## 使用

1. 从现有项目 JSON 取实际 `id`、`revision` 和按顺序排列的镜头 `id`。
2. 配方使用 `t8.h09.production-recipe.v1`。顶层必须是 `schema/project_id/revision/roles/props/shots`。
3. `roles` 每项为 `role_id/description/asset_ids`；`props` 为 `prop_id/description`。ID 用稳定 ASCII 标识，不由姓名或图片自动推断。素材 UUID 必须已绑定在相应镜头的参考或素材托盘里；工具不自动改接线。
4. `shots` 每项为 `shot_id/start_state/end_state/changes/dialogue`。两份 state 都逐个声明所有道具：`{"cup":{"holder":"A","state":"同一个白杯，完整"}}`。holder 为角色 ID、`scene` 或 `unknown`；变化须列入 `changes`，下一镜起点须等于上一镜终点。对白为 `[{"role_id":"A","text":"杯子给你。"}]`。
5. 在项目目录运行：`python tools/import_h09_recipe.py --project 原项目.json --recipe 配方.json --output-dir 新目录`。

输出 `project.json` 和 `report.json`，只产生 **pending** 候选，不保存覆盖原项目、不采样、不自动采用。查看候选后使用现有导演台显式采用／撤回。已采用的候选不会被覆盖；原稿或已绑定素材内容改变后，沿用原候选失效检查。

每项声明上限4096字符，但每镜合并后的完整 ledger 也须不超过现有 Skill 的4096字符预算。超出直接提示精简，不静默截断。最多32镜、32角色／道具；这不是推荐一次填满的数量。

## LoRA 配方边界

`production_recipe.selected_lora_card("loras", 实际安装名, 显式strength)` 复用已存在的资源卡，只读取当前选定文件的 header 与证据来源。训练 rank/alpha、运行 strength、Semantic Bridge alpha 分开；不按文件名猜、不统一写1、不应用或下载模型。

交接包的20款风格／角色 LoRA 是候选资料，不是20款都已下载、可商用或获画质认证。角色IP、许可证、作者配方和底模兼容性需按实际所选款核查，不能用 Person Remover 的卡片测试替代风格效果验证。

## 验证边界

有三镜道具交接的实际旧编译器／显式采用／保存重开合同，以及 CLI 创建新目录检查。真实导演台UI另已导入、保存revision1并导出项目；三份原稿保留、三个候选均active=false，真实画布编译仍输出原稿。2026-10-11集中反馈revision15的B1已通过，仅接受候选展示／原稿保留流程，未授权采用候选。它们不证明生成视频中的持物、因果或角色一致性；20款风格也未获整体资格。用户声明不会升级为已观察事实；最终仍需看成片。

[三镜候选展示短名图](../examples/workflows/86-h09-reviewed/B1_Director_Candidates.json)已按成功画布的完整依赖单独保存，剔除原声／参考待审分支，三个project输入和active=false保持。它不是生成视频验收，不自动保存／采用新的导演台项目，尚未发布。
