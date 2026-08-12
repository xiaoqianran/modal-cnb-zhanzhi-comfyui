#!/bin/bash

# --- 变量定义 ---
WORKFLOWS_DIR="/workspace/工作流"
ASSETS_DIR="/workspace/assets"
INDEX_FILE="$ASSETS_DIR/workflow_index.md"

# --- 步骤 1: 统计工作流总数 ---
echo "正在统计工作流总数..."
WORKFLOW_COUNT=$(find "$WORKFLOWS_DIR" -type f -name "*.json" | wc -l)
echo "合计找到 ${WORKFLOW_COUNT} 个工作流。"

# --- 步骤 2: 确保输出目录存在 ---
echo "正在确保输出目录 $ASSETS_DIR 存在..."
mkdir -p "$ASSETS_DIR"

# --- 步骤 3: 生成<最终坚固版>的Markdown索引文件 ---
echo "正在生成最稳妥、确保显示正确的最终版索引: $INDEX_FILE ..."
{
    # --- Markdown 内容生成开始 ---
    
    echo "# 📖 精品工作流"
    echo ""
    echo "合计 **${WORKFLOW_COUNT}** 个ComfyUI工作流都能正常运行，并内置了相关的素材更方便打开就能用。"
    echo ""
    echo "---"
    echo ""

    # 2. 遍历所有分类目录
    find "$WORKFLOWS_DIR" -mindepth 1 -maxdepth 1 -type d | sort | while read -r category_dir; do
        category_name=$(basename "$category_dir")
        
        ICON_CATEGORY=""
        case "$category_name" in
          *"最近更新"*) ICON_CATEGORY="🌟" ;; *"图片图像"*) ICON_CATEGORY="🎨" ;; *"Ai 动画"*) ICON_CATEGORY="🪄" ;;
          *"视频动画"*) ICON_CATEGORY="🎬" ;; *"音频语音"*) ICON_CATEGORY="🎧" ;; *"提示词"*) ICON_CATEGORY="💡" ;;
          *"Sora"|*"Veo"*) ICON_CATEGORY="🤖" ;; *"开发测试"*) ICON_CATEGORY="🧪" ;; *) ICON_CATEGORY="📂" ;;
        esac

        # 输出二级标题 (主分类)
        echo "## ${ICON_CATEGORY} ${category_name}"
        echo ""

        # 3. 处理主分类下的直接文件
        find "$category_dir" -maxdepth 1 -type f -name "*.json" | sort | while read -r workflow_file; do
            workflow_name=$(basename "$workflow_file" .json)
            stars=""
            # 使用更宽容的匹配来处理星号和空格
            if [[ "$workflow_name" == "★★★"* ]]; then stars="★★★ | "; fi
            clean_name=$(echo "$workflow_name" | sed -E 's/^[★]{1,3}[｜| ]*//')
            echo "- ${stars}${clean_name}"
        done
        
        # 4. 遍历并处理子目录 (优化缩进部分)
        find "$category_dir" -mindepth 1 -maxdepth 1 -type d | sort | while read -r subdir_path; do
            subdir_name=$(basename "$subdir_path")
            
            if find "$subdir_path" -maxdepth 1 -type f -name "*.json" | read -r; then
                echo ""
                # --- [优化修改核心点] ---
                # 1. 不使用 '>'，去掉竖线。
                # 2. 使用 '- **名字**' 将子目录作为父级列表项，加粗突出显示。
                echo "- **${subdir_name}**"

                # 5. 处理子目录下的文件
                find "$subdir_path" -maxdepth 1 -type f -name "*.json" | sort | while read -r workflow_file; do
                    workflow_name=$(basename "$workflow_file" .json)
                    stars=""
                    if [[ "$workflow_name" == "★★★"* ]]; then stars="★★★ | "; fi
                    clean_name=$(echo "$workflow_name" | sed -E 's/^[★]{1,3}[｜| ]*//')
                    
                    # 3. 关键修改：在 '-' 前面加 4 个空格。
                    # 这会让 Markdown 识别为“二级列表”，自动缩进对齐，没有竖线，颜色正常。
                    echo "    - ${stars}${clean_name}"
                done
            fi
        done
        echo ""
    done

} > "$INDEX_FILE"

# =======================================================
# --- [功能恢复与新增] 步骤 4: 更新统计数字 ---
# =======================================================

# [原有功能恢复] 4.1 更新 README.md
echo "正在更新 README.md 中的工作流数量..."
README_FILE="/workspace/README.md"

if [ -f "$README_FILE" ]; then
    # 使用 sed 精确匹配 "已调试完成 [数字] 个工作流" 并进行替换
    sed -i "s/已调试完成 [0-9]* 个工作流/已调试完成 ${WORKFLOW_COUNT} 个工作流/" "$README_FILE"
    echo "✅ README.md 已更新: 已同步为 ${WORKFLOW_COUNT} 个工作流。"
else
    echo "⚠️ 警告: 未找到 $README_FILE，跳过 README 更新。"
fi

# [新增功能] 4.2 更新 update.md
echo "正在更新 update.md 中的工作流数量..."
UPDATE_MD_FILE="/workspace/assets/update.md"

if [ -f "$UPDATE_MD_FILE" ]; then
    # 精确匹配 "# 🧠 已调试完成 [数字] 个工作流" 这一行
    sed -i "s/已调试完成 [0-9]* 个工作流/已调试完成 ${WORKFLOW_COUNT} 个工作流/" "$UPDATE_MD_FILE"
    echo "✅ update.md 已更新: 已同步为 ${WORKFLOW_COUNT} 个工作流（目标更新行：## 🧠 已调试完成...）。"
else
    echo "⚠️ 警告: 未找到 $UPDATE_MD_FILE，跳过 update.md 更新。"
fi
# ================= [功能结束] ========================


# --- 步骤 5: 完成 ---
echo "操作完成！索引文件已生成: $INDEX_FILE"
