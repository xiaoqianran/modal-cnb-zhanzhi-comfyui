import re
import shutil

# 配置文件路径（根据你的实际路径调整，默认适配ComfyUI目录）
TARGET_FILE = "/workspace/ComfyUI/custom_nodes/comfyui-easy-use/py/nodes/image.py"
BACKUP_FILE = TARGET_FILE + ".bak"  # 备份原文件

def patch_image_py():
    # 1. 备份原文件（防止出错）
    print("正在备份原文件...")
    shutil.copy2(TARGET_FILE, BACKUP_FILE)
    print(f"原文件已备份到: {BACKUP_FILE}")

    # 2. 读取文件内容
    with open(TARGET_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # 3. 第一步：在imageRemBg的remove方法开头插入全局Config修复代码
    # 正则匹配：remove方法定义 + new_images + masks + device定义（严格匹配缩进）
    pattern1 = re.compile(
        r'(  def remove\(self, rem_mode, images, image_output, save_prefix, torchscript_jit=False, add_background=\'none\', refine_foreground=False, prompt=None, extra_pnginfo=None\):\n'
        r'    new_images = list\(\)\n'
        r'    masks = list\(\)\n'
        r'    device = torch.device\("cuda" if torch.cuda.is_available\(\) else "cpu"\))',
        re.MULTILINE
    )

    # 插入的修复代码（保持原缩进：4空格）
    fix_code = r'\1\n' + r"""    # 全局修复Transformers Config缺失is_encoder_decoder属性的问题
    from transformers.configuration_utils import PretrainedConfig
    if not hasattr(PretrainedConfig, "is_encoder_decoder"):
        PretrainedConfig.is_encoder_decoder = False"""

    # 执行替换
    content = pattern1.sub(fix_code, content)

    # 4. 第二步：替换RMBG-2.0分支内的模型加载代码（双重保险）
    # 正则匹配原模型加载代码
    pattern2 = re.compile(
        r'        from transformers import AutoModelForImageSegmentation\n'
        r'        model = AutoModelForImageSegmentation.from_pretrained\(model_path, trust_remote_code=True\)',
        re.MULTILINE
    )

    # 替换后的代码（保持原缩进：8空格）
    replace_code = r"""        from transformers import AutoModelForImageSegmentation, AutoConfig
        config = AutoConfig.from_pretrained(model_path, trust_remote_code=True)
        if not hasattr(config, "is_encoder_decoder"):
            config.is_encoder_decoder = False
        model = AutoModelForImageSegmentation.from_pretrained(model_path, config=config, trust_remote_code=True)"""

    # 执行替换
    content = pattern2.sub(replace_code, content)

    # 5. 写回修改后的内容
    with open(TARGET_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print("补丁应用成功！")
    print("请重启ComfyUI后测试节点。")

if __name__ == "__main__":
    try:
        patch_image_py()
    except Exception as e:
        print(f"补丁应用失败：{str(e)}")
        print("请检查文件路径是否正确，或手动恢复备份文件。")