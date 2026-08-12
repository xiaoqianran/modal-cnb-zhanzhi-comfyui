# -*- coding: utf-8 -*-
import os
import re
import shutil
import sys
import json
try:
    from flask import Flask, request, jsonify, render_template_string
except ImportError:
    print("❌ 错误：请先安装 flask (pip install flask)")
    sys.exit(1)

app = Flask(__name__)

# ================= 配置区 =================
TARGET_DIR = "/workspace"
FILENAME = "初始化下载"
FALLBACK_FILE = "初始化下载.txt"

if os.path.exists(TARGET_DIR):
    FILE_PATH = os.path.join(TARGET_DIR, FILENAME)
else:
    FILE_PATH = os.path.join(os.getcwd(), FALLBACK_FILE)

PORT = 5000

# ================= HTML 模板 (智能解析版) =================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>下载配置编辑器 (智能版)</title>
    <style>
        /* === 全局样式 === */
        * { box-sizing: border-box; }
        body { 
            background-color: #f0f2f5; 
            font-family: Consolas, "Microsoft YaHei", sans-serif; /* 默认使用等宽字体，看起来更像编辑器 */
            padding-top: 80px; 
            padding-bottom: 50px;
            margin: 0;
        }

        /* === 顶部导航 === */
        .navbar-fixed {
            position: fixed; top: 0; left: 0; right: 0;
            height: 70px;
            background: #ffffff;
            border-bottom: 1px solid #e0e0e0;
            box-shadow: 0 4px 12px rgba(0,0,0,0.03);
            z-index: 1000;
            display: flex; align-items: center; justify-content: space-between;
            padding: 0 20px;
        }

        /* === 搜索框 === */
        .search-container {
            flex: 1; max-width: 500px; margin: 0 20px; position: relative;
        }
        .search-input {
            width: 100%; padding: 10px 15px 10px 40px; border-radius: 8px;
            border: 1px solid #ddd; background: #f8f9fa; font-size: 14px;
        }
        .search-input:focus { background: #fff; border-color: #4f46e5; outline: none; }
        .search-icon {
            position: absolute; left: 12px; top: 50%; transform: translateY(-50%);
            width: 16px; height: 16px; fill: #999; pointer-events: none;
        }

        /* === 列表容器 === */
        .container-fluid { padding: 0 20px; max-width: 99%; margin: 0 auto; }
        
        .grid-header {
            display: flex; padding: 10px 0; font-weight: 600; color: #666;
            border-bottom: 2px solid #ddd; margin-bottom: 10px; font-size: 0.9rem; font-family: sans-serif;
        }

        .row-item {
            display: flex; align-items: center; background: #fff;
            border: 1px solid #ddd; border-left: 5px solid #ccc;
            margin-bottom: 8px; padding: 8px 0; border-radius: 6px;
        }
        .row-item:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.05); }

        /* === 列布局 (宽屏优化) === */
        .col-drag { width: 40px; display: flex; justify-content: center; cursor: move; color: #ccc; }
        
        /* 目录和文件名限制宽度，把空间留给 URL */
        .col-path, .col-name { width: 15%; min-width: 120px; max-width: 300px; padding: 0 5px; }
        .col-url { flex: 1; padding: 0 5px; min-width: 200px; }
        .col-del { width: 60px; display: flex; justify-content: center; }

        /* === 输入框 (强制填满) === */
        .form-control {
            width: 100% !important; 
            border: 1px solid #ddd; border-radius: 4px; padding: 8px 10px;
            font-size: 14px; background: #fdfdfd; color: #333;
        }
        .form-control:focus { background: #fff; border-color: #4f46e5; outline: none; }

        /* 任务行特定样式 */
        .type-task { border-left-color: #0d6efd; }
        .type-task .col-url input { color: #0d6efd; } /* URL蓝色高亮 */

        /* 注释行样式 */
        .type-comment { border-left-color: #ffc107; background: #fffbf0; }
        .input-comment { 
            width: 100%; border: none; background: transparent; 
            color: #856404; font-weight: bold; border-bottom: 1px dashed #e0c070; padding: 5px;
        }
        .input-comment:focus { outline: none; border-bottom: 2px solid #ffc107; }

        /* 原始行样式 */
        .type-raw { border-left-color: #adb5bd; background: #f8f9fa; }
        .input-raw { width: 100%; border: none; color: #aaa; background: transparent; }

        /* === 按钮 === */
        .btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-weight: 500; display: inline-flex; align-items: center; gap: 5px; font-size: 14px; }
        .btn-primary { background: #0d6efd; color: white; }
        .btn-primary:hover { background: #0b5ed7; }
        .btn-outline { background: white; border: 1px solid #ddd; color: #333; }
        .btn-outline:hover { background: #f5f5f5; }
        
        .btn-del {
            width: 36px; height: 36px; border-radius: 6px; background: #fff; border: 1px solid #eee; color: #dc3545; display: flex; align-items: center; justify-content: center; cursor: pointer;
        }
        .btn-del:hover { background: #dc3545; color: white; border-color: #dc3545; }

        .svg-icon { width: 18px; height: 18px; fill: currentColor; }
        .d-none { display: none !important; }
    </style>
</head>
<body>

<svg style="display: none;">
    <symbol id="icon-search" viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></symbol>
    <symbol id="icon-plus" viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></symbol>
    <symbol id="icon-save" viewBox="0 0 24 24"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></symbol>
    <symbol id="icon-trash" viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></symbol>
    <symbol id="icon-drag" viewBox="0 0 24 24"><path d="M11 18c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2zm-2-8c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0-6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm6 4c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></symbol>
</svg>

<div class="navbar-fixed">
    <div style="display:flex; align-items:center;">
        <h3 style="margin:0; font-size:18px; font-weight:700; color:#333; font-family:sans-serif;">配置编辑器</h3>
        <span style="background:#eee; padding:2px 8px; border-radius:4px; margin-left:10px; font-size:12px; color:#555;">{{ file_path }}</span>
    </div>
    <div class="search-container">
        <svg class="search-icon"><use href="#icon-search"></use></svg>
        <input type="text" class="search-input" id="searchInput" placeholder="搜索 URL、文件名..." onkeyup="filterList()">
    </div>
    <div>
        <button class="btn btn-outline" onclick="addItem('comment')"><span style="color:#f59e0b; font-weight:bold;">#</span> 添加注释</button>
        <button class="btn btn-outline" onclick="addItem('task')" style="margin-left:5px;"><svg class="svg-icon" style="fill:#0d6efd"><use href="#icon-plus"></use></svg> 添加任务</button>
        <button class="btn btn-primary" onclick="saveFile()" id="btn-save" style="margin-left:5px;"><svg class="svg-icon" style="fill:#fff"><use href="#icon-save"></use></svg> 保存</button>
    </div>
</div>

<div class="container-fluid">
    <div class="grid-header">
        <div class="col-drag"></div>
        <div class="col-path">存储目录 (-d)</div>
        <div class="col-name">文件名 (-o)</div>
        <div class="col-url">下载链接 (URL) - 自动去除 ?name=</div>
        <div class="col-del">删</div>
    </div>
    <div id="list-container"></div>
    <div id="loading" style="text-align:center; padding:50px; color:#999;">Loading...</div>
</div>

<script src="https://lib.baomitu.com/Sortable/1.15.0/Sortable.min.js"></script>

<script>
    let lines = {{ lines | tojson }};
    const container = document.getElementById('list-container');
    const loading = document.getElementById('loading');

    function render() {
        container.innerHTML = '';
        loading.style.display = 'none';

        if(lines.length === 0) {
            loading.style.display = 'block';
            loading.innerText = "暂无数据";
            return;
        }

        lines.forEach((item, index) => {
            const row = document.createElement('div');
            let typeClass = item.type === 'task' ? 'type-task' : (item.type === 'comment' ? 'type-comment' : 'type-raw');
            row.className = `row-item ${typeClass}`;
            
            const dragHtml = `<div class="col-drag drag-handle"><svg class="svg-icon"><use href="#icon-drag"></use></svg></div>`;
            const delHtml = `<div class="col-del"><button class="btn-del" onclick="del(${index})" title="删除"><svg class="svg-icon"><use href="#icon-trash"></use></svg></button></div>`;

            let innerHtml = '';

            if (item.type === 'task') {
                // 注意：这里将 oninput 改为传递 'this' (DOM元素)，以便在JS中操作兄弟元素
                innerHtml = `
                    <div class="col-path">
                        <input type="text" class="form-control" value="${escapeHtml(item.dir)}" placeholder="/dir" oninput="update(${index}, 'dir', this)">
                    </div>
                    <div class="col-name">
                        <input type="text" class="form-control" value="${escapeHtml(item.filename)}" placeholder="filename" oninput="update(${index}, 'filename', this)">
                    </div>
                    <div class="col-url">
                        <input type="text" class="form-control" value="${escapeHtml(item.url)}" placeholder="https://..." oninput="update(${index}, 'url', this)">
                    </div>
                `;
            } else if (item.type === 'comment') {
                innerHtml = `
                    <div style="flex:1; padding:0 10px; display:flex;">
                        <span style="color:#f59e0b; font-weight:bold; margin-right:10px;">#</span>
                        <input type="text" class="input-comment" value="${escapeHtml(item.content)}" oninput="update(${index}, 'content', this)">
                    </div>
                `;
            } else {
                innerHtml = `
                    <div style="flex:1; padding:0 10px;">
                        <input type="text" class="input-raw" value="${escapeHtml(item.content)}" disabled>
                    </div>
                `;
            }

            row.innerHTML = dragHtml + innerHtml + delHtml;
            container.appendChild(row);
        });
        filterList();
    }

    // === 核心逻辑：数据更新 & 自动提取文件名 ===
    window.update = function(idx, key, el) {
        let val = el.value;

        // 【新功能】自动解析 URL 中的 ?name=
        if (key === 'url' && val.includes('?name=')) {
            try {
                // 分割 URL
                const parts = val.split('?name=');
                const cleanUrl = parts[0];
                let extractedName = parts[1];
                
                // 防止提取到后续其他参数（虽然 ?name= 通常在最后，但为了保险）
                if (extractedName.includes('&')) {
                    extractedName = extractedName.split('&')[0];
                }
                
                // URL 解码 (例如将 %20 转为空格)
                extractedName = decodeURIComponent(extractedName);

                // 1. 更新数据模型
                lines[idx]['url'] = cleanUrl;
                lines[idx]['filename'] = extractedName;

                // 2. 更新 DOM 视觉显示
                // 更新当前的 URL 框
                el.value = cleanUrl; 
                val = cleanUrl; // 确保存入 model 的也是干净的 URL

                // 更新同行的文件名框
                const row = el.closest('.row-item');
                const nameInput = row.querySelector('.col-name input');
                if (nameInput) {
                    nameInput.value = extractedName;
                    // 给个黄色闪烁效果提示用户已自动填充
                    nameInput.style.backgroundColor = "#fff9c4";
                    setTimeout(() => nameInput.style.backgroundColor = "#fdfdfd", 500);
                }

            } catch (e) {
                console.error("Auto parse failed:", e);
            }
        }

        // 正常更新数据
        lines[idx][key] = val;
    };

    window.filterList = function() {
        const term = document.getElementById('searchInput').value.toLowerCase();
        document.querySelectorAll('.row-item').forEach(row => {
            let text = "";
            row.querySelectorAll('input').forEach(i => text += i.value.toLowerCase() + " ");
            if(text.includes(term)) row.classList.remove('d-none');
            else row.classList.add('d-none');
        });
    }

    window.del = function(idx) {
        if(confirm("确定删除？")) {
            lines.splice(idx, 1);
            render();
        }
    }

    window.addItem = function(type) {
        document.getElementById('searchInput').value = '';
        if(type === 'task') lines.push({ type: 'task', dir: '/models/checkpoints', filename: '', url: '' });
        else lines.push({ type: 'comment', content: ' 新注释' });
        render();
        window.scrollTo(0, document.body.scrollHeight);
    }

    window.saveFile = function() {
        const btn = document.getElementById('btn-save');
        const old = btn.innerHTML;
        btn.innerHTML = 'Saving...';
        btn.disabled = true;

        fetch('/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ lines: lines })
        })
        .then(res => res.json())
        .then(data => {
            if(data.status === 'success') alert('✅ 保存成功');
            else alert('失败: ' + data.msg);
        })
        .catch(e => alert('网络错误'))
        .finally(() => {
            btn.innerHTML = old;
            btn.disabled = false;
        });
    }

    function escapeHtml(text) { return text ? text.replace(/"/g, "&quot;") : ""; }

    try {
        new Sortable(container, {
            handle: '.drag-handle',
            animation: 150,
            onEnd: function (evt) {
                const item = lines.splice(evt.oldIndex, 1)[0];
                lines.splice(evt.newIndex, 0, item);
            }
        });
    } catch(e) {}

    render();
</script>
</body>
</html>
"""

# ================= 后端逻辑 (不变) =================
ARIA_PATTERN = re.compile(r'aria2c .*?-d\s+"([^"]+)"\s+-o\s+"([^"]+)"\s+"([^"]+)"')

@app.route('/')
def index():
    if not os.path.exists(FILE_PATH):
        try:
            with open(FILE_PATH, 'w', encoding='utf-8') as f: f.write('#!/bin/bash\n')
        except: pass

    parsed = []
    try:
        with open(FILE_PATH, 'r', encoding='utf-8') as f:
            for idx, line in enumerate(f):
                c = line.strip()
                match = ARIA_PATTERN.search(c)
                if match and not c.startswith('#'):
                    parsed.append({'type': 'task', 'dir': match.group(1), 'filename': match.group(2), 'url': match.group(3)})
                elif c.startswith('#') and '!/bin/bash' not in c:
                    parsed.append({'type': 'comment', 'content': c.lstrip('#').strip()})
                else:
                    parsed.append({'type': 'raw', 'content': c})
    except Exception as e: return f"Error: {e}"
    return render_template_string(HTML_TEMPLATE, lines=parsed, file_path=FILE_PATH)

@app.route('/save', methods=['POST'])
def save():
    try:
        lines = request.json.get('lines', [])
        content_list = []
        if os.path.exists(FILE_PATH):
            try: shutil.copy(FILE_PATH, f"{FILE_PATH}.bak")
            except: pass
        for item in lines:
            if item['type'] == 'task':
                content_list.append(f'aria2c -x 4 -s 4 -c -d "{item["dir"]}" -o "{item["filename"]}" "{item["url"]}"')
            elif item['type'] == 'comment':
                if item['content'].strip(): content_list.append(f"# {item['content']}")
            else:
                content_list.append(item['content'])
        with open(FILE_PATH, 'w', encoding='utf-8') as f: f.write('\n'.join(content_list) + '\n')
        return jsonify({'status': 'success'})
    except Exception as e: return jsonify({'status': 'error', 'msg': str(e)})

if __name__ == '__main__':
    print(f"✅ 智能编辑器已启动: http://0.0.0.0:{PORT}")
    app.run(host='0.0.0.0', port=PORT)