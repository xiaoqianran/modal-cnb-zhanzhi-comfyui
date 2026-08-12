#!/bin/bash

# 检查是否传入了参数
if [ $# -ne 1 ]; then
  echo "Usage: $0 <GPU_TYPE>"
  echo "Example: $0 H20"
  exit 1
fi

GPU_TYPE="$1"
YAML_FILE=".cnb.yml"

# 判断输入合法性
if [[ "$GPU_TYPE" != "L40" && "$GPU_TYPE" != "H20" ]]; then
  echo "Invalid GPU type. Only L40 or H20 allowed."
  exit 1
fi

# 检查文件是否存在
if [ ! -f "$YAML_FILE" ]; then
  echo "Error: $YAML_FILE not found!"
  exit 1
fi

# 备份原始文件
cp "$YAML_FILE" "${YAML_FILE}.bak"

# 使用 sed 和正则表达式精确匹配并替换 tags 行
# 匹配以空白字符开头，包含 tags: cnb:arch:amd64:gpu: 开头的行
sed -i "s/^\([[:space:]]*tags:[[:space:]]*cnb:arch:amd64:gpu:\)[^[:space:]]*/\1$GPU_TYPE/" "$YAML_FILE"

# 检查是否成功替换
if grep -q "tags: cnb:arch:amd64:gpu:$GPU_TYPE" "$YAML_FILE"; then
  echo "✅ Successfully updated .cnb.yml with GPU type: $GPU_TYPE"
else
  echo "❌ Failed to update .cnb.yml. Please check the file format."
  # 恢复备份
  mv "${YAML_FILE}.bak" "$YAML_FILE"
  exit 1
fi
