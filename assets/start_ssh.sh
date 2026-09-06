#!/bin/bash
set -e

# 1. 设置SSH账号与密码，可自行修改这里
SSH_USER="sshuser"
SSH_PASS="Abc@123456"

# 2. 修改sshd配置，允许密码登录、允许root/普通用户登录
sed -i 's/^#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/^PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/^PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config

# 3. 创建ssh用户，如果已存在就重置密码
if id -u "${SSH_USER}" >/dev/null 2>&1; then
    echo "${SSH_USER} 用户已存在，重置密码"
else
    useradd -m -s /bin/bash "${SSH_USER}"
fi
echo "${SSH_USER}:${SSH_PASS}" | chpasswd

# 可选：如果你也想开放root直接ssh登录，取消下面注释
# echo "root:${SSH_PASS}" | chpasswd

# 4. 生成ssh主机密钥（容器镜像可能缺失密钥，sshd启动会报错）
if [ ! -f /etc/ssh/ssh_host_rsa_key ]; then
    ssh-keygen -A
fi

# 5. 停止旧sshd（如果残留），前台启动sshd
pkill sshd || true
/usr/sbin/sshd -D &

echo "====================================="
echo "SSH服务已启动"
echo "SSH端口: 22"
echo "SSH用户名: ${SSH_USER}"
echo "SSH密码: ${SSH_PASS}"
echo "====================================="
echo "提示：容器外部访问记得docker run -p 宿主机端口:22 映射端口！"
echo "查看sshd进程: ps aux | grep sshd"
