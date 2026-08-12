import json
import os
import shutil

# 定义 zj.json 中新增的、而 source.json 中没有的数据
patch_data = {
    "path_dict": {
        "全部模型": {
            "unet": "models/unet"
        },
        "lightx2v": {
            "Wan2.2-Lightning": "models/loras"
        },
        "fuliai": {
            "diy_models": "models"
        }
    },
    "checkpoints": {
        "AllInOne/wan2.2-i2v-rapid-aio-v10-nsfw.safetensors": "https://cnb.cool/ai-models/Phr00t/WAN2.2-14B-Rapid-AllInOne/-/lfs/3ead1d9bfd24cc650052dcd310be32bcfd0dd6175418323c41a9208bbc027081",
        "AllInOne/wan2.2-i2v-rapid-aio-v10.safetensors": "https://cnb.cool/ai-models/Phr00t/WAN2.2-14B-Rapid-AllInOne/-/lfs/fe9cb6ce4abfa2beed7a954d33550828d68dd48ff2d17cbb5e583b962dea7809",
        "AllInOne/wan2.2-t2v-rapid-aio-v10-nsfw.safetensors": "https://cnb.cool/ai-models/Phr00t/WAN2.2-14B-Rapid-AllInOne/-/lfs/f0c372b0d45fb4888aaebb7ac534b7106dd93e5bff26b53def4c2f8bac0af994",
        "AllInOne/wan2.2-t2v-rapid-aio-v10.safetensors": "https://cnb.cool/ai-models/Phr00t/WAN2.2-14B-Rapid-AllInOne/-/lfs/3759940a8a3591defbad23950269ff3120a7fdc71c22695161a449418e82c193"
    },
    "diffusion_models": {
        "Wan2.2-T2V-A14B-4steps-250928-dyno-high-lightx2v.safetensors": "https://cnb.cool/ai-models/lightx2v/Wan2.2-Lightning/-/lfs/1cf8032c0094bd98c66c25b7c7b48652fc831056eaf67d0795a78618d01a5458"
    },
    "upscale_models": {
        "4x-ClearRealityV1.pth": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/a4cd3a25b00e0be949d4302fc774eb4d7f2ed5f47cdb51551e2d75fa6562e51e"
    },
    "Qwen-Image-Lightning": {
        "Qwen-Image-Lightning-8steps-V2.0-bf16.safetensors": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/5bdbf69912280a9944be9b3aacd8db0cfbb429fcbd66c994d7b38b5a37e357ee"
    },
    "unet": {
        "Qwen-Image-Edit-2509-Q8_0.gguf": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/f8f0773e56f94f7f4508ca15a5bc9acf1d6ca2863bebaba7a1b80fbf76198e02",
        "Wan2_2_Animate_14B_Q4_K_M.gguf": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/c28b05ae5beb7384d43d4bfec7478cf3ab76ebe516b4a20befe78d3713f5bfea",
        "Wan2_2_Animate_14B_Q8_0.gguf": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/b747dda4d89aea033dcd49e18e26d78d7e0854296136c2ccc0b14e85df7e77cd",
        "Hearts_K.safetensors": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/c3244561fd7afad543a08fe50ee1316a6c8042312fe7a8f10fbf1429abd18770"
    },
    "diy_models": {
        "SDMatte/SDMatte_plus.pth": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/f9da31d2f665299fe0b76e984e2931146a80c0aee7f8a2aad1a978e52ad4442e",
        "SEEDVR2/seedvr2_ema_3b_fp8_e4m3fn.safetensors": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/3bf1e43ebedd570e7e7a0b1b60d6a02e105978f505c8128a241cde99a8240cff",
        "SEEDVR2/ema_vae_fp16.safetensors": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/20678548f420d98d26f11442d3528f8b8c94e57ee046ef93dbb7633da8612ca1",
        "ckpts/TheMistoAI/MistoLine/Anyline/MTEED.pth": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/a3c2d8a8ce9422555c787160bd46362d761325a565333c0e3f6a53e0bae2abdb",
        "ckpts/depth-anything/Depth-Anything-V2-Large/depth_anything_v2_vitl.pth": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/a7ea19fa0ed99244e67b624c72b8580b7e9553043245905be58796a608eb9345",
        "face_parsing/parsing_bisenet.pth": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/468e13ca13a9b43cc0881a9f99083a430e9c0a38abd935431d1c28ee94b26567",
        "grounding-dino/groundingdino_swint_ogc.pth": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/3b3ca2563c77c69f651d7bd133e97139c186df06231157a64c507099c52bc799",
        "interpolation/gimm-vfi/gimmvfi_r_arb_lpips_fp32.safetensors": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/897b892e7ee481f2e5c09e59661b645abbd6c9aba9c0c01346bbe31aa569e277",
        "interpolation/gimm-vfi/raft-things_fp32.safetensors": "https://cnb.cool/fuliai/comfyui_pro/-/lfs/ba7cb7781f9f67030e2f6acc4151ac8701b633d93d39e8d61991f2b472a0e45a"
    },
    "Wan2.2-Lightning": {
        "Wan2.2-T2V-A14B-4steps-lora-250928_low-lightx2v.safetensors": "https://cnb.cool/ai-models/lightx2v/Wan2.2-Lightning/-/lfs/09b26832d05c2a2fdfa344da126dd90ed4ff6663c30511e735e915df3c8646af",
        "Wan2.2-T2V-A14B-4steps-lora-250928_high-lightx2v.safetensors": "https://cnb.cool/ai-models/lightx2v/Wan2.2-Lightning/-/lfs/905950365a2e663d57463cd08ddfd51e2db29a49208317fdc7d97d17e61be8d3"
    }
}

def deep_merge(source, destination):
    """
    递归合并字典。
    - 将 source 中的键值对合并到 destination 中。
    - 如果键在两者中都存在且值为字典，则递归合并。
    - 否则，source 中的值会覆盖 destination 中的值（在此场景下为新增）。
    """
    for key, value in source.items():
        if isinstance(value, dict) and key in destination and isinstance(destination[key], dict):
            deep_merge(value, destination[key])
        else:
            destination[key] = value
    return destination

def apply_patch(target_file='source.json'):
    """
    主函数，用于应用补丁。
    """
    # 1. 检查文件是否存在
    if not os.path.exists(target_file):
        print(f"错误: 目标文件 '{target_file}' 不存在。请将脚本与该文件放在同一目录下。")
        return

    # 2. 创建备份
    backup_file = target_file + '.bak'
    try:
        shutil.copy2(target_file, backup_file)
        print(f"成功创建备份文件: '{backup_file}'")
    except Exception as e:
        print(f"错误: 创建备份文件失败。错误信息: {e}")
        return

    # 3. 读取原始JSON文件
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            source_data = json.load(f)
        print(f"成功读取 '{target_file}'。")
    except json.JSONDecodeError:
        print(f"错误: '{target_file}' 不是一个有效的JSON文件。请检查文件内容。")
        return
    except Exception as e:
        print(f"错误: 读取文件时发生未知错误。错误信息: {e}")
        return

    # 4. 深度合并数据
    print("正在合并新增内容...")
    updated_data = deep_merge(patch_data, source_data)
    print("合并完成。")

    # 5. 将更新后的数据写回文件
    try:
        with open(target_file, 'w', encoding='utf-8') as f:
            # 使用 indent=4 保持格式美观，ensure_ascii=False 以正确显示中文
            json.dump(updated_data, f, indent=4, ensure_ascii=False)
        print(f"成功将更新内容写入 '{target_file}'。")
    except Exception as e:
        print(f"错误: 写入更新文件时失败。错误信息: {e}")
        return
        
    print("\n补丁成功应用！")

if __name__ == '__main__':
    apply_patch()