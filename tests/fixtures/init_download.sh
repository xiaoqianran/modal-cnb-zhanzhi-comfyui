aria2c -x 4 -s 4 -c -d "/models/sams" -o "SeC-4B-fp8.safetensors" "https://cnb.cool/zhan_zhi/Ai-Models/-/lfs/aaa111"
# commented
aria2c -x 4 -s 4 -c -d "/models/vae" -o "wan_2.1_vae.safetensors" "https://cnb.cool/ai-models/example/-/lfs/bbb222"
aria2c -x 4 -s 4 -c -d "/workspace/models/loras" -o "lightning.safetensors" "https://huggingface.co/example/resolve/main/lightning.safetensors"
# aria2c -x 4 -s 4 -c -d "/models/skip" -o "nope.pt" "https://example.invalid/nope.pt"
