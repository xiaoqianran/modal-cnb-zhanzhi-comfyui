# venv生成方法

```
# 生成venv
python3 -m venv venv

# 激活venv
source venv/bin/activate

# 安装pytorch（注意cuda版本）
pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128

# pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu129

# 安装dev版本的pytorch（注意cuda版本）
pip install -U torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu129

# 安装xformers（注意cuda版本，低版本pytorch需要手工指定xformers版本）
pip install xformers --index-url https://download.pytorch.org/whl/cu128

# pytorch版本 xformers版本对照表（仅供参考）
# torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 xformers==0.0.32.post2
# torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 xformers==0.0.31.post1
# torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 xformers==0.0.30
# torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 xformers==0.0.29.post2
# torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 xformers==0.0.28.post3
# torch==2.5.0 torchvision==0.20.0 torchaudio==2.5.0 xformers==0.0.28.post2
# torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1 xformers==0.0.28.post1
# torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 xformers==0.0.27.post2
# torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 xformers==0.0.27
# torch==2.3.0 torchvision==0.18.0 torchaudio==2.3.0 xformers==0.0.26.post1
# torch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2 xformers==0.0.26
# torch==2.2.1 torchvision==0.17.1 torchaudio==2.2.1 xformers==0.0.25
# torch==2.2.0 torchvision==0.17.0 torchaudio==2.2.0 xformers==0.0.24
# torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 xformers==0.0.23.post1
# torch==2.1.1 torchvision==0.16.1 torchaudio==2.1.1 xformers==0.0.23
# torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 xformers==0.0.22.post7
# torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 无xformers
# torch==2.0.0 torchvision==0.15.1 torchaudio==2.0.1 无xformers

# 从源码安装xformers（pip安装的版本有问题时可尝试，低版本torch需要自己找低版本xformers源码）
git clone https://github.com/facebookresearch/xformers.git
cd xformers
git submodule update --init --recursive
python setup.py install
cd ..

# 安装flash-attn（具体版本得看插件要求）
pip install flash-attn==2.8.0.post2

# 安装SageAttention
git clone https://github.com/thu-ml/SageAttention.git
cd SageAttention 
export EXT_PARALLEL=4 NVCC_APPEND_FLAGS="--threads 8" MAX_JOBS=32 # parallel compiling (Optional)
python setup.py install
cd ..
```