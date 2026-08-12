from flask import Flask, render_template_string, request, jsonify, send_file
import json
from io import BytesIO
import os
import traceback

app = Flask(__name__)

# 定义要自动加载的文件路径列表
SOURCE_FILE_PATHS = {
    "source.json": "/workspace/assets/source.json",
    "自定义下载链接.json": "/workspace/自定义下载链接.json",
    "source_2.json": "/workspace/assets/source_2.json"
}

# 全局变量 - 确保在多线程环境下的访问安全
current_json = {
    "checkpoints": {
        "多级文件夹示例/multi-level folders/majicmixRealistic_v7.safetensors": "https://cnb.cool/ai-models/digiplay/majicMIX_realistic_v7/-/lfs/7c819b6d13663ed720c2254f4fe18373107dfef2448d337913c8fc545640881e"
    },
    "loras": {
        f"风格{i}Lora.safetensors": f"https://example.com/style{i}.lora" for i in range(1, 15)
    },
    "vae": {
        "常规VAE.safetensors": "https://example.com/regular.vae"
    },
    "clip": {},
    "clip_vision": {},
    "controlnet": {},
    "diffusion_models": {},
    "text_encoders": {},
    "upscale_models": {},
    # 路径管理相关字段（支持两种格式）
    "path_settings": {
        "base_path": "/models",  # 默认基础路径
        "checkpoints": "{base_path}/checkpoints",
        "loras": "{base_path}/loras",
        "vae": "{base_path}/vae"
    },
    "path_dict": {
        "默认分组": {
            "base_path": "/models",
            "checkpoints": "{base_path}/checkpoints"
        }
    }
}
uploaded_filename = "source.json"
current_file_path = None
current_path_group = "默认分组"  # 默认路径分组

def get_paginated_data(data, page=1, per_page=10):
    """获取分页数据"""
    items = list(data.items())
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))  # 确保页码有效
    start = (page - 1) * per_page
    end = start + per_page
    paginated = dict(items[start:end])
    
    # 计算显示的页码范围（最多显示10个页码）
    page_range = []
    if total_pages <= 10:
        page_range = list(range(1, total_pages + 1))
    else:
        page_range.append(1)
        if page > 3:
            page_range.append('...')
        start_page = max(2, page - 2)
        end_page = min(total_pages - 1, page + 2)
        for p in range(start_page, end_page + 1):
            page_range.append(p)
        if page < total_pages - 2:
            page_range.append('...')
        page_range.append(total_pages)
    
    return {
        'data': paginated,
        'current_page': page,
        'total_pages': total_pages,
        'items_per_page': per_page,
        'total_items': total,
        'page_range': page_range
    }

def get_model_nodes(json_data):
    """获取模型节点列表（排除路径设置等非模型节点）"""
    exclude_nodes = ['path_settings', 'path_dict']
    return [key for key in json_data.keys() if key not in exclude_nodes]

def get_non_model_nodes(json_data):
    """获取非模型节点的顶级字段"""
    model_nodes = get_model_nodes(json_data)
    return [key for key in json_data.keys() if key not in model_nodes]

def get_path_structure(json_data):
    """
    获取完整的路径结构信息，兼容两种格式
    返回: {groups: [], current_group: str, paths: dict, is_grouped: bool}
    """
    result = {
        "groups": ["默认"],
        "current_group": "默认",
        "paths": {},
        "is_grouped": False
    }
    
    # 检查是否存在分组路径设置（path_dict）
    if "path_dict" in json_data and isinstance(json_data["path_dict"], dict) and len(json_data["path_dict"]) > 0:
        result["is_grouped"] = True
        result["groups"] = list(json_data["path_dict"].keys())
        # 保持当前分组，如果不存在则用第一个分组
        if current_path_group in result["groups"]:
            result["current_group"] = current_path_group
        else:
            result["current_group"] = result["groups"][0] if result["groups"] else "默认"
        # 获取当前分组的路径设置
        result["paths"] = json_data["path_dict"].get(result["current_group"], {})
    else:
        # 使用扁平路径设置（path_settings）
        result["paths"] = json_data.get("path_settings", {})
        # 确保基础路径存在
        if "base_path" not in result["paths"]:
            result["paths"]["base_path"] = "/models"  # 设置默认基础路径
    
    return result

def resolve_path(path_value, base_path):
    """解析路径中的变量"""
    if not path_value or not base_path:
        return None
    return path_value.replace("{base_path}", base_path)

@app.route('/', methods=['GET'])
def index():
    global current_json, uploaded_filename, current_file_path, current_path_group
    
    # 获取查询参数
    node = request.args.get('node')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    path_group = request.args.get('path_group')
    
    # 更新当前路径分组
    if path_group:
        current_path_group = path_group
    
    # 获取路径结构信息
    path_info = get_path_structure(current_json)
    
    # 获取模型节点列表
    model_nodes = get_model_nodes(current_json)
    non_model_nodes = get_non_model_nodes(current_json)
    
    # 确定当前节点
    current_node = node if node and node in model_nodes else (model_nodes[0] if model_nodes else None)
    
    # 获取当前节点的分页数据
    paginated_data = {
        'data': {},
        'current_page': 1,
        'total_pages': 1,
        'items_per_page': per_page,
        'total_items': 0,
        'page_range': [1]
    }
    
    if current_node and current_node in current_json and isinstance(current_json[current_node], dict):
        paginated_data = get_paginated_data(current_json[current_node], page, per_page)
    
    return render_template_string(HTML_TEMPLATE,
        filename=uploaded_filename,
        current_file_path=current_file_path,
        model_nodes=model_nodes,
        non_model_nodes=non_model_nodes,
        current_node=current_node,
        paginated_models=paginated_data['data'],
        model_current_page=paginated_data['current_page'],
        model_total_pages=paginated_data['total_pages'],
        model_items_per_page=paginated_data['items_per_page'],
        total_model_items=paginated_data['total_items'],
        model_page_range=paginated_data['page_range'],
        source_file_paths=SOURCE_FILE_PATHS,
        path_info=path_info,
        path_groups=path_info["groups"],
        current_path_group=path_info["current_group"],
        path_settings=path_info["paths"],
        is_grouped=path_info["is_grouped"]
    )

@app.route('/upload', methods=['POST'])
def upload_file():
    global current_json, uploaded_filename, current_file_path
    
    try:
        if 'json_file' not in request.files:
            return jsonify({'success': False, 'msg': '没有文件部分'})
        
        file = request.files['json_file']
        if file.filename == '':
            return jsonify({'success': False, 'msg': '未选择文件'})
        
        if file and file.filename.endswith('.json'):
            # 读取并解析JSON
            content = file.read().decode('utf-8')
            current_json = json.loads(content)
            uploaded_filename = file.filename
            current_file_path = None  # 重置文件路径，因为是上传的文件
            return jsonify({'success': True, 'msg': '文件上传成功'})
        
        return jsonify({'success': False, 'msg': '请上传JSON文件'})
    except Exception as e:
        return jsonify({'success': False, 'msg': f'上传失败: {str(e)}'})

@app.route('/download', methods=['GET'])
def download_file():
    global current_json, uploaded_filename
    
    try:
        # 将JSON数据转换为字符串
        json_str = json.dumps(current_json, ensure_ascii=False, indent=2)
        # 创建字节流
        buffer = BytesIO()
        buffer.write(json_str.encode('utf-8'))
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=uploaded_filename,
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({'success': False, 'msg': f'下载失败: {str(e)}'})

@app.route('/add-node', methods=['POST'])
def add_node():
    global current_json
    
    try:
        data = request.get_json()
        node = data.get('node')
        
        if not node:
            return jsonify({'success': False, 'msg': '节点名称不能为空'})
        
        if node in current_json:
            return jsonify({'success': False, 'msg': f'节点 "{node}" 已存在'})
        
        # 添加新节点
        current_json[node] = {}
        return jsonify({'success': True, 'msg': f'节点 "{node}" 添加成功'})
    except Exception as e:
        return jsonify({'success': False, 'msg': f'添加失败: {str(e)}'})

@app.route('/delete-node', methods=['POST'])
def delete_node():
    global current_json
    
    try:
        data = request.get_json()
        node = data.get('node')
        
        if not node:
            return jsonify({'success': False, 'msg': '节点名称不能为空'})
        
        if node not in current_json:
            return jsonify({'success': False, 'msg': f'节点 "{node}" 不存在'})
        
        # 特殊保护：不允许删除路径设置节点
        if node in ['path_settings', 'path_dict']:
            return jsonify({'success': False, 'msg': '不允许删除路径设置节点'})
        
        # 删除节点
        del current_json[node]
        return jsonify({'success': True, 'msg': f'节点 "{node}" 删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'msg': f'删除失败: {str(e)}'})

@app.route('/add-model', methods=['POST'])
def add_model():
    global current_json
    
    try:
        data = request.get_json()
        node = data.get('node')
        filename = data.get('filename')
        url = data.get('url')
        
        if not node or not filename or not url:
            return jsonify({'success': False, 'msg': '节点、文件名和URL不能为空'})
        
        if node not in current_json:
            return jsonify({'success': False, 'msg': f'节点 "{node}" 不存在'})
        
        # 确保节点是字典类型
        if not isinstance(current_json[node], dict):
            current_json[node] = {}
        
        # 检查是否已存在
        if filename in current_json[node]:
            return jsonify({'success': False, 'msg': f'文件名 "{filename}" 已存在'})
        
        # 添加模型
        current_json[node][filename] = url
        return jsonify({'success': True, 'msg': '模型添加成功'})
    except Exception as e:
        return jsonify({'success': False, 'msg': f'添加失败: {str(e)}'})

@app.route('/edit-model', methods=['POST'])
def edit_model():
    global current_json
    
    try:
        data = request.get_json()
        node = data.get('node')
        original_filename = data.get('original_filename')
        new_filename = data.get('new_filename')
        new_url = data.get('new_url')
        
        if not node or not original_filename or not new_filename or not new_url:
            return jsonify({'success': False, 'msg': '参数不完整'})
        
        if node not in current_json:
            return jsonify({'success': False, 'msg': f'节点 "{node}" 不存在'})
        
        # 确保节点是字典类型
        if not isinstance(current_json[node], dict):
            return jsonify({'success': False, 'msg': f'节点 "{node}" 不是有效的字典类型'})
        
        if original_filename not in current_json[node]:
            return jsonify({'success': False, 'msg': f'文件名 "{original_filename}" 不存在'})
        
        # 如果文件名改变，检查新文件名是否已存在
        if original_filename != new_filename and new_filename in current_json[node]:
            return jsonify({'success': False, 'msg': f'新文件名 "{new_filename}" 已存在'})
        
        # 删除原条目
        del current_json[node][original_filename]
        # 添加新条目
        current_json[node][new_filename] = new_url
        
        return jsonify({'success': True, 'msg': '模型编辑成功'})
    except Exception as e:
        return jsonify({'success': False, 'msg': f'编辑失败: {str(e)}'})

@app.route('/delete-model', methods=['POST'])
def delete_model():
    global current_json
    
    try:
        data = request.get_json()
        node = data.get('node')
        filename = data.get('filename')
        
        if not node or not filename:
            return jsonify({'success': False, 'msg': '节点和文件名不能为空'})
        
        if node not in current_json:
            return jsonify({'success': False, 'msg': f'节点 "{node}" 不存在'})
        
        # 确保节点是字典类型
        if not isinstance(current_json[node], dict):
            return jsonify({'success': False, 'msg': f'节点 "{node}" 不是有效的字典类型'})
        
        if filename not in current_json[node]:
            return jsonify({'success': False, 'msg': f'文件名 "{filename}" 不存在'})
        
        # 删除模型
        del current_json[node][filename]
        return jsonify({'success': True, 'msg': '模型删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'msg': f'删除失败: {str(e)}'})

@app.route('/load-file', methods=['POST'])
def load_file():
    global current_json, uploaded_filename, current_file_path, current_path_group
    
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        file_name = data.get('file_name')
        
        if not file_path or not file_name:
            return jsonify({'success': False, 'msg': '文件路径和名称不能为空'})
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'msg': f'文件不存在: {file_path}'})
        
        # 检查文件是否是JSON文件
        if not file_path.endswith('.json'):
            return jsonify({'success': False, 'msg': '只能加载JSON文件'})
        
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            current_json = json.loads(content)
        
        uploaded_filename = file_name
        current_file_path = file_path
        
        # 重置路径分组
        path_info = get_path_structure(current_json)
        current_path_group = path_info["current_group"]
        
        return jsonify({'success': True, 'msg': f'文件 "{file_name}" 加载成功'})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'msg': f'加载失败: {str(e)}'})

@app.route('/save-to-original-path', methods=['POST'])
def save_to_original_path():
    global current_json, current_file_path
    
    try:
        if not current_file_path:
            return jsonify({'success': False, 'msg': '没有可保存的文件路径'})
        
        # 检查文件是否仍然存在
        if not os.path.exists(current_file_path):
            return jsonify({'success': False, 'msg': f'文件不存在: {current_file_path}'})
        
        # 保存文件
        with open(current_file_path, 'w', encoding='utf-8') as f:
            json.dump(current_json, f, ensure_ascii=False, indent=2)
        
        return jsonify({'success': True, 'msg': f'已保存到: {current_file_path}'})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'msg': f'保存失败: {str(e)}'})

@app.route('/get-model-node-data', methods=['POST'])
def get_model_node_data():
    global current_json
    
    try:
        data = request.get_json()
        node = data.get('node')
        
        if not node:
            return jsonify({'success': False, 'msg': '节点名称不能为空'})
        
        if node not in current_json:
            return jsonify({'success': False, 'msg': f'节点 "{node}" 不存在'})
        
        # 确保返回的数据是字典
        node_data = current_json[node]
        if not isinstance(node_data, dict):
            node_data = {}
            
        return jsonify({
            'success': True,
            'data': node_data
        })
    except Exception as e:
        return jsonify({'success': False, 'msg': f'获取数据失败: {str(e)}'})

@app.route('/update-path-settings', methods=['POST'])
def update_path_settings():
    global current_json, current_path_group
    
    try:
        data = request.get_json()
        node = data.get('node')
        path_value = data.get('path_value')
        group = data.get('group', current_path_group)
        
        if not node or path_value is None:
            return jsonify({'success': False, 'msg': '节点和路径值不能为空'})
        
        # 检查路径设置格式并更新
        path_info = get_path_structure(current_json)
        
        if path_info["is_grouped"]:
            # 处理分组路径格式 (path_dict)
            if "path_dict" not in current_json or not isinstance(current_json["path_dict"], dict):
                current_json["path_dict"] = {}
            
            # 确保分组存在
            if group not in current_json["path_dict"]:
                current_json["path_dict"][group] = {}
            
            # 更新路径
            current_json["path_dict"][group][node] = path_value
        else:
            # 处理扁平路径格式 (path_settings)
            if "path_settings" not in current_json or not isinstance(current_json["path_settings"], dict):
                current_json["path_settings"] = {}
            
            # 更新路径
            current_json["path_settings"][node] = path_value
        
        # 特别处理基础路径变更 - 确保始终存在
        if node == "base_path" and not path_value:
            current_json["path_settings"]["base_path"] = "/models"
            return jsonify({'success': True, 'msg': '基础路径不能为空，已设置为默认值'})
        
        return jsonify({
            'success': True,
            'msg': f'节点 "{node}" 的路径设置已更新',
            'base_path': path_info["paths"].get("base_path", "/models")
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'msg': f'更新失败: {str(e)}'})

@app.route('/switch-path-group', methods=['POST'])
def switch_path_group():
    global current_path_group
    
    try:
        data = request.get_json()
        group = data.get('group')
        
        if not group:
            return jsonify({'success': False, 'msg': '分组名称不能为空'})
        
        # 验证分组是否存在
        if "path_dict" in current_json and isinstance(current_json["path_dict"], dict):
            if group not in current_json["path_dict"]:
                return jsonify({'success': False, 'msg': f'分组 "{group}" 不存在'})
        
        current_path_group = group
        return jsonify({
            'success': True,
            'msg': f'已切换到路径分组 "{group}"',
            'paths': get_path_structure(current_json)["paths"]
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'msg': f'切换失败: {str(e)}'})

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>JSON 编辑器</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; }
        .section { margin-bottom: 30px; padding: 20px; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .btn { 
            background: #4285f4; 
            color: white; 
            border: none; 
            padding: 10px 18px; 
            border-radius: 4px; 
            cursor: pointer; 
            font-size: 14px;
            margin-right: 8px;
            margin-bottom: 8px;
        }
        .btn:hover { background: #3367d6; }
        .btn-danger { background: #ea4335; }
        .btn-danger:hover { background: #d33222; }
        .btn-secondary { background: #f5f5f5; color: #333; }
        .btn-secondary:hover { background: #e9e9e9; }
        .btn-auto-load { background: #34a853; }
        .btn-auto-load:hover { background: #2d8643; }
        .btn-save { background: #fbbc05; color: #333; }
        .btn-save:hover { background: #f9aa00; }
        .btn-save:disabled { background: #f2f2f2; color: #999; cursor: not-allowed; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        th { background-color: #f5f5f5; }
        .status { margin: 10px 0; padding: 10px; border-radius: 4px; }
        .success { background-color: #dff0d8; color: #3c763d; }
        .error { background-color: #f2dede; color: #a94442; }
        .debug { margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 5px; font-size: 0.9em; }
        .pagination { margin: 15px 0; padding: 10px; border: 1px solid #eee; border-radius: 4px; }
        .page-btn { 
            padding: 6px 12px; 
            border: 1px solid #ddd; 
            background: #fff; 
            border-radius: 4px; 
            cursor: pointer; 
            margin-right: 5px;
        }
        .page-btn.active { 
            background: #4285f4; 
            color: white; 
            border-color: #4285f4;
        }
        .page-btn:disabled { 
            opacity: 0.5; 
            cursor: not-allowed; 
            background: #f9f9f9;
        }
        .controls { margin: 15px 0; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .select-control { padding: 8px; min-width: 200px; border: 1px solid #ddd; border-radius: 4px; }
        .add-form { margin: 15px 0; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
        .form-input { padding: 8px; flex: 1; min-width: 200px; border: 1px solid #ddd; border-radius: 4px; }
        .folder-prefix-input { flex: 0.5; min-width: 150px; }
        .prefix-hint { font-size: 0.85em; color: #666; margin: 5px 0 0 0; }
        .section-title { margin-top: 0; padding-bottom: 10px; border-bottom: 1px solid #eee; }
        .table-container { max-height: 400px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px; }
        .pagination-info { margin-bottom: 10px; color: #666; }
        .edit-input { width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 3px; }
        .action-buttons { display: flex; gap: 5px; }
        .hint { color: #666; font-size: 0.9em; margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 4px; }
        .checkbox-group { display: flex; align-items: center; gap: 5px; margin: 5px 0; }
        .auto-load-buttons { margin: 10px 0; }
        .search-container { margin: 10px 0; }
        .search-input { 
            width: 100%; 
            padding: 10px; 
            border: 1px solid #ddd; 
            border-radius: 4px; 
            font-size: 14px;
            box-sizing: border-box;
        }
        .search-input::placeholder { color: #999; }
        .search-results { 
            color: #666; 
            font-size: 0.9em; 
            margin: 5px 0; 
            display: flex;
            justify-content: space-between;
        }
        .highlight { background-color: #fff3cd; font-weight: bold; }
        
        .global-search-container {
            margin: 0 0 30px 0;
            padding: 20px;
            background: #f8fafc;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            overflow: hidden;
        }
        .global-search-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            cursor: pointer;
        }
        .global-search-title {
            display: flex;
            align-items: center;
            font-size: 1.2em;
            font-weight: bold;
        }
        .toggle-icon {
            margin-left: 10px;
            transition: transform 0.3s ease;
        }
        .toggle-icon.collapsed {
            transform: rotate(-90deg);
        }
        .global-search-content {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out, opacity 0.3s ease-out, padding 0.3s ease-out;
            opacity: 0;
            padding-top: 0;
            padding-bottom: 0;
        }
        .global-search-content.expanded {
            max-height: 1000px;
            opacity: 1;
            padding-top: 10px;
            padding-bottom: 10px;
        }
        .search-input-container {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        .global-search-input {
            flex: 1;
            padding: 12px 15px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 16px;
        }
        .global-search-results {
            margin-top: 20px;
            max-height: 500px;
            overflow-y: auto;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            display: none;
        }
        .global-search-results.visible {
            display: block;
        }
        .search-section-header {
            background: #f1f5f9;
            padding: 10px 15px;
            font-weight: bold;
            border-bottom: 1px solid #e2e8f0;
        }
        .search-result-item {
            padding: 10px 15px;
            border-bottom: 1px solid #f1f5f9;
        }
        .search-result-item:hover {
            background: #f8fafc;
        }
        .result-type {
            font-size: 0.8em;
            color: #64748b;
            margin-bottom: 5px;
        }
        .result-content {
            margin-bottom: 5px;
        }
        .result-meta {
            font-size: 0.85em;
            color: #64748b;
        }
        .global-search-stats {
            margin: 10px 0;
            padding: 10px;
            background: #f8fafc;
            border-radius: 4px;
            font-size: 0.9em;
            color: #64748b;
        }
        .search-tabs {
            display: flex;
            border-bottom: 1px solid #e2e8f0;
            margin-bottom: 15px;
        }
        .search-tab {
            padding: 8px 15px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
        }
        .search-tab.active {
            border-bottom-color: #4285f4;
            color: #4285f4;
            font-weight: bold;
        }
        .search-result-actions {
            margin-top: 8px;
            display: flex;
            gap: 5px;
        }
        .result-action-btn {
            padding: 3px 8px;
            font-size: 0.8em;
        }
        
        .file-source-info {
            font-size: 0.9em;
            color: #666;
            margin: 5px 0;
            padding: 8px;
            background: #f8f9fa;
            border-radius: 4px;
        }
        
        .folder-path {
            color: #666;
            font-size: 0.85em;
            margin-bottom: 3px;
        }
        .file-name {
            font-weight: 500;
        }
        
        #debug-info {
            margin: 10px 0;
            padding: 10px;
            background: #f0f0f0;
            border-radius: 4px;
            font-size: 0.9em;
            color: #333;
            max-height: 200px;
            overflow-y: auto;
        }
        
        /* 模型路径管理样式 - 增强版 */
        #model-path-management {
            margin: 30px 0;
            padding: 20px;
            border: 1px solid #ddd;
            border-radius: 8px;
            background-color: #f9f9f9;
        }
        .path-management-controls {
            display: flex;
            align-items: center;
            gap: 15px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }
        .path-group-select {
            min-width: 180px;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .path-node-select {
            min-width: 220px;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .path-input-group {
            flex: 1;
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .path-input {
            flex: 1;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .path-preview {
            margin-top: 15px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 4px;
            font-size: 0.9em;
        }
        .path-variable {
            display: inline-block;
            padding: 2px 6px;
            background-color: #e3f2fd;
            border-radius: 3px;
            font-family: monospace;
            margin: 0 2px;
        }
        .path-section-disabled {
            opacity: 0.6;
            pointer-events: none;
        }
        .path-section-disabled-message {
            color: #999;
            font-style: italic;
            padding: 10px;
            text-align: center;
            margin: 20px 0;
        }
        .path-group-info {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 10px;
            padding: 5px;
            background: #f0f7ff;
            border-radius: 4px;
        }
        .required-indicator {
            color: #dc3545;
            font-weight: bold;
        }
        
        /* URL解析辅助提示样式 */
        .url-parsing-hint {
            font-size: 0.85em;
            color: #28a745;
            margin: 5px 0 10px 0;
            padding: 8px;
            background: #f0fff4;
            border-radius: 4px;
            display: none;
        }
        .url-parsing-hint.visible {
            display: block;
        }
        .url-parsing-hint.error {
            color: #dc3545;
            background: #fff5f5;
        }
    </style>
</head>
<body>
    <h1>JSON 编辑器</h1>

    <!-- 调试信息区域 -->
    <div id="debug-info" style="display: none;">
        <strong>调试信息:</strong>
        <div id="debug-content"></div>
    </div>

    <!-- 可折叠的全局搜索区域 -->
    <div class="global-search-container">
        <div class="global-search-header" id="global-search-toggle">
            <div class="global-search-title">
                全局搜索
                <span class="toggle-icon collapsed" id="toggle-icon">▼</span>
            </div>
        </div>
        
        <div class="global-search-content" id="global-search-content">
            <div class="search-input-container">
                <input type="text" id="global-search-input" class="global-search-input" 
                       placeholder="搜索所有模型、链接、路径...">
                <button id="global-search-btn" class="btn">搜索</button>
                <button id="clear-global-search" class="btn btn-secondary">清除</button>
            </div>
            
            <div class="search-tabs">
                <div class="search-tab active" data-tab="all">全部结果</div>
                <div class="search-tab" data-tab="models">模型节点</div>
            </div>
            
            <div class="global-search-stats" id="global-search-stats" style="display: none;">
                找到 <span id="total-results">0</span> 个结果
            </div>
            
            <div class="global-search-results" id="global-search-results">
                <!-- 模型结果区域 -->
                <div class="search-section" id="model-results-section">
                    <div class="search-section-header">模型节点结果</div>
                    <div id="model-results-container"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- 文件操作 -->
    <div class="section">
        <h2 class="section-title">文件操作</h2>
        <form id="upload-form" enctype="multipart/form-data">
            <input type="file" name="json_file" accept=".json">
            <button type="submit" class="btn">上传文件</button>
        </form>
        
        <!-- 自动载入文件按钮组 -->
        <div class="auto-load-buttons">
            <p>自动载入文件:</p>
            {% for name, path in source_file_paths.items() %}
            <button class="btn btn-auto-load load-file-btn" data-path="{{ path }}" data-name="{{ name }}">
                载入 {{ name }}
            </button>
            {% endfor %}
        </div>
        
        <!-- 文件操作按钮组 -->
        <div style="margin-top: 10px;">
            <button id="download-btn" class="btn">下载文件</button>
            <button id="save-btn" class="btn btn-save" {% if not current_file_path %}disabled{% endif %}>
                保持（保存到原文件）
            </button>
            <button id="toggle-debug" class="btn btn-secondary">显示/隐藏调试</button>
        </div>
        
        <div id="upload-status" class="status"></div>
        
        <!-- 文件来源信息 -->
        <div class="file-source-info">
            当前文件: {{ filename }}
            {% if current_file_path %}
                <br>文件来源: {{ current_file_path }}
                <br><small>点击"保持"按钮将保存到原文件路径</small>
            {% else %}
                {% if filename == "source.json" %}
                    <br><small>未通过自动载入功能加载，"保持"按钮不可用</small>
                {% endif %}
            {% endif %}
        </div>
    </div>

    <!-- 模型节点管理 -->
    <div class="section">
        <h2 class="section-title">模型节点管理</h2>
        
        <div class="hint">
            <strong>说明：</strong> 支持多级文件夹结构，使用斜杠 <strong>/</strong> 分隔文件夹层级（例如：<code>文件夹1/文件夹2/文件名.safetensors</code>）。<br>
            系统会自动识别并展示文件夹结构。当输入包含 <code>?name=</code> 参数的URL时，会自动提取文件名并清理链接。
        </div>
        
        <div class="controls">
            <label>选择节点: </label>
            <select id="model-node" class="select-control">
                {% for node in model_nodes %}
                <option value="{{ node }}" {% if node == current_node %}selected{% endif %}>{{ node }}</option>
                {% endfor %}
            </select>
            <button id="add-node" class="btn">新增节点</button>
            <button id="delete-node" class="btn btn-danger">删除当前节点</button>
        </div>
        
        <!-- 添加模型条目 -->
        <div class="add-form">
            <input type="text" id="folder-prefix" class="form-input folder-prefix-input" placeholder="目录前缀 (可选)">
            <input type="text" id="new-filename" class="form-input" placeholder="文件名 (如: model.safetensors)">
            <input type="text" id="new-url" class="form-input" placeholder="下载链接">
            <button id="add-model-item" class="btn">添加模型</button>
        </div>
        
        <!-- URL解析提示 -->
        <div id="url-parsing-hint" class="url-parsing-hint">
            已自动解析URL: 提取文件名并清理链接
        </div>
        
        <p class="prefix-hint">提示：目录前缀和文件名会自动组合为完整路径（例如：前缀"Flux"+文件名"model.safetensors" → "Flux/model.safetensors"）</p>
        
        <!-- 模型节点搜索框 -->
        <div class="search-container">
            <input type="text" id="model-search" class="search-input" placeholder="搜索模型（文件名、文件夹或链接）...">
            <div class="search-results">
                <span id="model-search-count">找到 {{ total_model_items }} 个结果</span>
                <button id="clear-model-search" class="btn btn-secondary btn-sm" style="padding: 3px 8px; font-size: 0.8em;">清除搜索</button>
            </div>
        </div>
        
        <h3>当前节点: {{ current_node }} (共 {{ total_model_items }} 项)</h3>
        <div class="table-container">
            <table id="model-table">
                <thead><tr><th>文件路径</th><th>链接</th><th>操作</th></tr></thead>
                <tbody>
                    {% for file_path, url in paginated_models.items() %}
                    <tr>
                        <td>
                            {% set path_parts = file_path.split('/') %}
                            {% if path_parts|length > 1 %}
                                <div class="folder-path">
                                    {{ '/'.join(path_parts[:-1]) }}/
                                </div>
                            {% endif %}
                            <div class="file-name">
                                {{ path_parts[-1] }}
                            </div>
                        </td>
                        <td style="word-break: break-all;">{{ url }}</td>
                        <td class="action-buttons">
                            <button class="btn btn-secondary edit-model" data-filename="{{ file_path }}">编辑</button>
                            <button class="btn btn-danger delete-model" data-filename="{{ file_path }}">删除</button>
                        </td>
                    </tr>
                    {% else %}
                    <tr><td colspan="3" style="text-align: center;">该节点暂无模型数据</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <!-- 模型分页 -->
        <div class="pagination">
            <div class="pagination-info">
                第 {{ model_current_page }} / {{ model_total_pages }} 页，每页 {{ model_items_per_page }} 条，共 {{ total_model_items }} 条
            </div>
            
            <button class="page-btn" id="model-first" {% if model_current_page == 1 %}disabled{% endif %}>首页</button>
            <button class="page-btn" id="model-prev" {% if model_current_page == 1 %}disabled{% endif %}>上一页</button>
            
            {% for page in model_page_range %}
                <button class="page-btn {% if page == model_current_page %}active{% endif %}" 
                        data-page="{{ page }}">{{ page }}</button>
            {% endfor %}
            
            <button class="page-btn" id="model-next" {% if model_current_page == model_total_pages %}disabled{% endif %}>下一页</button>
            <button class="page-btn" id="model-last" {% if model_current_page == model_total_pages %}disabled{% endif %}>末页</button>
            
            <select id="model-items-per-page" class="select-control" style="margin-left: 10px;">
                <option value="10" {% if model_items_per_page == 10 %}selected{% endif %}>10条/页</option>
                <option value="20" {% if model_items_per_page == 20 %}selected{% endif %}>20条/页</option>
                <option value="50" {% if model_items_per_page == 50 %}selected{% endif %}>50条/页</option>
            </select>
        </div>
    </div>

    <!-- 模型路径管理功能区（支持分组） -->
    <div id="model-path-management" class="section">
        <h2 class="section-title">模型路径管理</h2>
        
        <div class="hint">
            <strong>说明：</strong> 选择模型节点后设置对应的存储路径，支持使用基础路径变量（<span class="path-variable">{base_path}</span>）。<br>
            基础路径（base_path）<span class="required-indicator">*</span> 为所有模型路径的根目录，必须先设置才能解析其他路径。
        </div>
        
        {% if path_info.is_grouped %}
        <div class="path-group-info">
            <strong>路径分组:</strong> 该文件使用分组路径管理，当前分组: {{ current_path_group }}
        </div>
        
        <div class="path-management-controls">
            <label for="path-group-select">选择路径分组:</label>
            <select id="path-group-select" class="path-group-select">
                {% for group in path_groups %}
                <option value="{{ group }}" {% if group == current_path_group %}selected{% endif %}>{{ group }}</option>
                {% endfor %}
            </select>
        </div>
        {% endif %}
        
        <!-- 下拉选择节点 + 路径输入 -->
        <div class="path-management-controls">
            <label for="path-node-select">选择模型节点:</label>
            <select id="path-node-select" class="path-node-select">
                <option value="base_path">基础路径 (base_path) <span class="required-indicator">*</span></option>
                {% for node in model_nodes %}
                <option value="{{ node }}">{{ node }}</option>
                {% endfor %}
            </select>
            
            <div class="path-input-group">
                <input type="text" id="path-value-input" class="path-input" placeholder="输入路径（例如：{base_path}/checkpoints）">
                <button id="save-path-btn" class="btn">保存路径</button>
                <button id="reset-path-btn" class="btn btn-secondary">重置</button>
            </div>
        </div>
        
        <!-- 路径预览 -->
        <div class="path-preview">
            <strong>当前设置:</strong>
            <div id="current-path-display">- 请选择节点查看路径 -</div>
            <br>
            <strong>解析后路径:</strong>
            <div id="resolved-path-display" style="color: #666;">- 请先设置基础路径 -</div>
        </div>
    </div>

    <!-- 调试信息 -->
    <div class="debug">
        <h3>调试信息</h3>
        <div>模型节点: {{ model_nodes|join(', ') or '无' }}</div>
        <div>当前模型节点: {{ current_node }}</div>
        {% if current_file_path %}
        <div>当前文件路径: {{ current_file_path }}</div>
        {% endif %}
        <div>非模型节点的顶级字段: {{ non_model_nodes|join(', ') or '无' }}</div>
        <div>路径设置类型: {% if is_grouped %}分组路径 (path_dict){% else %}扁平路径 (path_settings){% endif %}</div>
        {% if is_grouped %}
        <div>路径分组: {{ path_groups|join(', ') }}</div>
        <div>当前路径分组: {{ current_path_group }}</div>
        {% endif %}
        <div>路径设置内容: {{ path_settings|tojson }}</div>
        <div>基础路径状态: {% if path_settings and path_settings.base_path %}已设置为 "{{ path_settings.base_path }}"{% else %}未设置{% endif %}</div>
    </div>

    <!-- 编辑弹窗模板 -->
    <div id="edit-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); align-items: center; justify-content: center; z-index: 1000;">
        <div style="background: white; padding: 20px; border-radius: 8px; width: 500px; max-width: 90%;">
            <h3 id="modal-title">编辑项目</h3>
            <div id="modal-content" style="margin: 15px 0;">
                <!-- 动态填充 -->
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 10px;">
                <button id="cancel-edit" class="btn btn-secondary">取消</button>
                <button id="save-edit" class="btn">保存</button>
            </div>
        </div>
    </div>

    <script>
        // 当前状态
        const currentNode = "{{ current_node }}";
        const modelCurrentPage = {{ model_current_page }};
        const modelItemsPerPage = {{ model_items_per_page }};
        const modelTotalPages = {{ model_total_pages }};
        const totalModelItems = {{ total_model_items }};
        const currentFilePath = "{{ current_file_path or '' }}";
        const pathInfo = {{ path_info|tojson }};
        const pathGroups = {{ path_groups|tojson }};
        const currentPathGroup = "{{ current_path_group }}";
        const pathSettings = {{ path_settings|tojson }};
        const isGrouped = {{ 'true' if is_grouped else 'false' }};
        const allModelNodes = {{ model_nodes|tojson }};
        const sourceFilePaths = {{ source_file_paths|tojson }};
        
        // 页面加载完成后初始化
        document.addEventListener('DOMContentLoaded', function() {
            loadFolderPrefix();
            
            // 绑定所有事件
            bindModelEvents();
            bindFileEvents();
            bindModalEvents();
            bindUrlParsingEvent();
            bindAutoLoadEvents();
            bindSearchEvents();
            bindGlobalSearchEvents();
            bindSaveButtonEvent();
            bindFolderPrefixEvents();
            bindDebugEvents();
            
            // 记录初始状态
            logToDebug('页面加载完成，功能初始化完成');
            logToDebug('路径设置类型: ' + (isGrouped ? '分组路径 (path_dict)' : '扁平路径 (path_settings)'));
            logToDebug('当前路径分组: ' + currentPathGroup);
            logToDebug('路径设置内容: ' + JSON.stringify(pathSettings));
            logToDebug('基础路径: ' + (pathSettings.base_path || '未设置'));
            logToDebug('模型节点列表: ' + JSON.stringify(allModelNodes));
            
            // 绑定路径管理事件
            bindPathManagementEvents();
        });
        
        // 绑定路径管理事件
        function bindPathManagementEvents() {
            const nodeSelect = document.getElementById('path-node-select');
            const pathInput = document.getElementById('path-value-input');
            const saveBtn = document.getElementById('save-path-btn');
            const resetBtn = document.getElementById('reset-path-btn');
            const currentPathDisplay = document.getElementById('current-path-display');
            const resolvedPathDisplay = document.getElementById('resolved-path-display');
            const groupSelect = document.getElementById('path-group-select');
            
            // 分组切换事件（如果是分组路径）
            if (isGrouped && groupSelect) {
                groupSelect.addEventListener('change', function() {
                    const selectedGroup = this.value;
                    if (selectedGroup !== currentPathGroup) {
                        fetch('/switch-path-group', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({group: selectedGroup})
                        }).then(res => res.json())
                          .then(data => {
                              if (data.success) {
                                  logToDebug(`切换路径分组至: ${selectedGroup}`);
                                  // 重新加载页面以更新路径设置
                                  window.location.href = window.location.pathname + `?path_group=${encodeURIComponent(selectedGroup)}`;
                              } else {
                                  alert('切换分组失败: ' + data.msg);
                              }
                          })
                          .catch(error => {
                              alert('切换分组出错: ' + error.message);
                              logToDebug('切换路径分组错误: ' + error.message);
                          });
                    }
                });
            }
            
            // 初始化：加载选中节点的路径
            nodeSelect.addEventListener('change', function() {
                const selectedNode = this.value;
                const pathValue = pathSettings[selectedNode] || '';
                pathInput.value = pathValue;
                updatePathDisplay(selectedNode, pathValue);
                logToDebug(`切换路径节点至: ${selectedNode}, 路径值: ${pathValue}`);
            });
            
            // 重置按钮：清空输入框
            resetBtn.addEventListener('click', function() {
                pathInput.value = '';
                const selectedNode = nodeSelect.value;
                currentPathDisplay.textContent = `节点: ${selectedNode} | 路径: 未设置`;
                resolvedPathDisplay.textContent = selectedNode === 'base_path' ? '基础路径未设置' : '无法解析（基础路径未设置）';
                resolvedPathDisplay.style.color = '#dc3545';
                logToDebug(`重置路径节点: ${selectedNode}`);
            });
            
            // 保存按钮：提交路径设置
            saveBtn.addEventListener('click', function() {
                const selectedNode = nodeSelect.value;
                const pathValue = pathInput.value.trim();
                
                if (!pathValue) {
                    alert('路径不能为空，请输入有效的路径设置');
                    return;
                }
                
                // 提交到后端
                fetch('/update-path-settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        node: selectedNode,
                        path_value: pathValue,
                        group: currentPathGroup
                    })
                }).then(res => res.json())
                  .then(data => {
                      alert(data.msg);
                      // 更新显示
                      updatePathDisplay(selectedNode, pathValue);
                      // 更新本地缓存
                      pathSettings[selectedNode] = pathValue;
                      // 如果设置的是基础路径，更新所有路径显示
                      if (selectedNode === 'base_path') {
                          nodeSelect.dispatchEvent(new Event('change'));
                      }
                      // 启用保存按钮（如果是自动加载的文件）
                      if (currentFilePath) {
                          document.getElementById('save-btn').disabled = false;
                      }
                  })
                  .catch(error => {
                      alert('保存路径失败: ' + error.message);
                      logToDebug('保存路径错误: ' + error.message);
                  });
            });
            
            // 初始化默认显示（基础路径）
            nodeSelect.value = 'base_path';
            const initPath = pathSettings['base_path'] || '';
            pathInput.value = initPath;
            updatePathDisplay('base_path', initPath);
            logToDebug(`初始化路径管理，基础路径: ${initPath}`);
        }
        
        // 更新路径显示（含变量解析）
        function updatePathDisplay(node, pathValue) {
            const currentPathDisplay = document.getElementById('current-path-display');
            const resolvedPathDisplay = document.getElementById('resolved-path-display');
            const isBasePath = node === 'base_path';
            
            // 显示原始设置
            currentPathDisplay.textContent = `节点: ${node} | 路径: ${pathValue || '未设置'}`;
            
            // 解析变量（如{base_path}）
            let resolvedPath = pathValue;
            if (!isBasePath && pathValue && pathSettings.base_path) {
                resolvedPath = pathValue.replace(/\{base_path\}/g, pathSettings.base_path);
            }
            
            // 显示解析后路径
            if (isBasePath) {
                resolvedPathDisplay.textContent = pathValue || '未设置（请先设置基础路径）';
            } else if (!pathSettings.base_path) {
                resolvedPathDisplay.textContent = '无法解析（基础路径未设置）';
            } else {
                resolvedPathDisplay.textContent = resolvedPath || '未设置路径';
            }
            
            // 设置颜色
            if (!pathValue) {
                resolvedPathDisplay.style.color = '#dc3545'; // 未设置
            } else if (!isBasePath && !pathSettings.base_path) {
                resolvedPathDisplay.style.color = '#fd7e14'; // 警告
            } else {
                resolvedPathDisplay.style.color = '#28a745'; // 正常
            }
            
            logToDebug(`更新路径显示: ${node} = ${pathValue}, 解析后: ${resolvedPath}`);
        }
        
        // 调试相关功能
        function bindDebugEvents() {
            const toggleBtn = document.getElementById('toggle-debug');
            const debugInfo = document.getElementById('debug-info');
            toggleBtn.addEventListener('click', function() {
                debugInfo.style.display = debugInfo.style.display === 'none' ? 'block' : 'none';
            });
        }
        
        function logToDebug(message) {
            const debugContent = document.getElementById('debug-content');
            const timestamp = new Date().toLocaleTimeString();
            const logEntry = document.createElement('div');
            logEntry.innerHTML = `<strong>[${timestamp}]</strong> ${message}`;
            debugContent.appendChild(logEntry);
            debugContent.scrollTop = debugContent.scrollHeight;
        }
        
        // 文件夹前缀相关功能
        function bindFolderPrefixEvents() {
            const folderPrefixInput = document.getElementById('folder-prefix');
            folderPrefixInput.addEventListener('input', function() {
                saveFolderPrefix(this.value);
            });
        }
        
        function saveFolderPrefix(prefix) {
            try {
                localStorage.setItem('folderPrefix', prefix);
            } catch (e) {
                console.error('保存目录前缀失败:', e);
                logToDebug('保存目录前缀失败: ' + e.message);
            }
        }
        
        function loadFolderPrefix() {
            try {
                const savedPrefix = localStorage.getItem('folderPrefix');
                if (savedPrefix !== null) {
                    document.getElementById('folder-prefix').value = savedPrefix;
                }
            } catch (e) {
                console.error('加载目录前缀失败:', e);
                logToDebug('加载目录前缀失败: ' + e.message);
            }
        }
        
        // 保存按钮事件
        function bindSaveButtonEvent() {
            const saveBtn = document.getElementById('save-btn');
            const statusEl = document.getElementById('upload-status');
            saveBtn.addEventListener('click', function() {
                if (!currentFilePath) {
                    statusEl.className = 'status error';
                    statusEl.textContent = '错误: 只有通过自动载入功能加载的文件才能使用"保持"功能';
                    return;
                }
                if (confirm(`确定要保存到原文件路径吗？\n${currentFilePath}\n此操作将覆盖原文件！`)) {
                    fetch('/save-to-original-path', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'}
                    }).then(res => res.json())
                      .then(data => {
                          if (data.success) {
                              statusEl.className = 'status success';
                              statusEl.textContent = '保存成功: ' + data.msg;
                              setTimeout(() => {
                                  statusEl.textContent = '';
                                  statusEl.className = 'status';
                              }, 3000);
                          } else {
                              statusEl.className = 'status error';
                              statusEl.textContent = '保存失败: ' + data.msg;
                          }
                      })
                      .catch(error => {
                          statusEl.className = 'status error';
                          statusEl.textContent = '保存出错: ' + error.message;
                      });
                }
            });
        }
        
        // 全局搜索功能
        function bindGlobalSearchEvents() {
            const globalSearchToggle = document.getElementById('global-search-toggle');
            const globalSearchContent = document.getElementById('global-search-content');
            const toggleIcon = document.getElementById('toggle-icon');
            const globalSearchInput = document.getElementById('global-search-input');
            const globalSearchBtn = document.getElementById('global-search-btn');
            const clearGlobalSearchBtn = document.getElementById('clear-global-search');
            const searchTabs = document.querySelectorAll('.search-tab');
            
            globalSearchToggle.addEventListener('click', function() {
                globalSearchContent.classList.toggle('expanded');
                toggleIcon.classList.toggle('collapsed');
            });
            
            globalSearchBtn.addEventListener('click', function() {
                if (!globalSearchContent.classList.contains('expanded')) {
                    globalSearchContent.classList.add('expanded');
                    toggleIcon.classList.remove('collapsed');
                }
                performGlobalSearch(globalSearchInput.value);
            });
            
            globalSearchInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    if (!globalSearchContent.classList.contains('expanded')) {
                        globalSearchContent.classList.add('expanded');
                        toggleIcon.classList.remove('collapsed');
                    }
                    performGlobalSearch(globalSearchInput.value);
                }
            });
            
            clearGlobalSearchBtn.addEventListener('click', function() {
                globalSearchInput.value = '';
                document.getElementById('global-search-results').classList.remove('visible');
                document.getElementById('global-search-stats').style.display = 'none';
            });
            
            searchTabs.forEach(tab => {
                tab.addEventListener('click', function() {
                    searchTabs.forEach(t => t.classList.remove('active'));
                    this.classList.add('active');
                    const tabType = this.getAttribute('data-tab');
                    filterGlobalResults(tabType);
                });
            });
        }
        
        function performGlobalSearch(keyword) {
            keyword = keyword.toLowerCase().trim();
            if (!keyword) {
                alert('请输入搜索关键词');
                return;
            }
            document.getElementById('model-results-container').innerHTML = '';
            let totalResultsCount = 0;
            
            allModelNodes.forEach(node => {
                fetch('/get-model-node-data', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({node: node})
                }).then(res => res.json())
                  .then(data => {
                      if (data.success && data.data) {
                          const items = data.data;
                          Object.keys(items).forEach(filePath => {
                              const url = items[filePath];
                              const lowerFilePath = filePath.toLowerCase();
                              const lowerUrl = url.toLowerCase();
                              
                              if (lowerFilePath.includes(keyword) || lowerUrl.includes(keyword)) {
                                  totalResultsCount++;
                                  const resultItem = document.createElement('div');
                                  resultItem.className = 'search-result-item';
                                  resultItem.setAttribute('data-node', node);
                                  resultItem.setAttribute('data-type', 'model');
                                  
                                  // 高亮匹配的关键词
                                  let highlightedPath = filePath;
                                  if (lowerFilePath.includes(keyword)) {
                                      const index = lowerFilePath.indexOf(keyword);
                                      highlightedPath = filePath.substring(0, index) + 
                                                       '<span class="highlight">' + 
                                                       filePath.substring(index, index + keyword.length) + 
                                                       '</span>' + 
                                                       filePath.substring(index + keyword.length);
                                  }
                                  
                                  let highlightedUrl = url;
                                  if (lowerUrl.includes(keyword)) {
                                      const index = lowerUrl.indexOf(keyword);
                                      highlightedUrl = url.substring(0, index) + 
                                                       '<span class="highlight">' + 
                                                       url.substring(index, index + keyword.length) + 
                                                       '</span>' + 
                                                       url.substring(index + keyword.length);
                                  }
                                  
                                  resultItem.innerHTML = `
                                      <div class="result-type">模型节点: ${node}</div>
                                      <div class="result-content">${highlightedPath}</div>
                                      <div class="result-meta">${highlightedUrl}</div>
                                      <div class="search-result-actions">
                                          <button class="btn btn-secondary result-action-btn view-in-node" 
                                                  data-node="${node}" data-filepath="${filePath}">
                                              在节点中查看
                                          </button>
                                          <button class="btn btn-secondary result-action-btn edit-result" 
                                                  data-node="${node}" data-filepath="${filePath}">
                                              编辑
                                          </button>
                                      </div>
                                  `;
                                  document.getElementById('model-results-container').appendChild(resultItem);
                              }
                          });
                          
                          // 绑定结果项的操作按钮事件
                          document.querySelectorAll('.view-in-node').forEach(btn => {
                              btn.addEventListener('click', function() {
                                  const node = this.getAttribute('data-node');
                                  const filePath = this.getAttribute('data-filepath');
                                  viewInNode(node, filePath);
                              });
                          });
                          
                          document.querySelectorAll('.edit-result').forEach(btn => {
                              btn.addEventListener('click', function() {
                                  const node = this.getAttribute('data-node');
                                  const filePath = this.getAttribute('data-filepath');
                                  editResult(node, filePath);
                              });
                          });
                          
                          // 更新统计信息
                          document.getElementById('total-results').textContent = totalResultsCount;
                          document.getElementById('global-search-stats').style.display = 'block';
                          document.getElementById('global-search-results').classList.add('visible');
                      }
                  })
                  .catch(error => {
                      console.error('搜索出错:', error);
                      logToDebug('全局搜索错误: ' + error.message);
                  });
            });
        }
        
        function filterGlobalResults(tabType) {
            const results = document.querySelectorAll('.search-result-item');
            results.forEach(result => {
                if (tabType === 'all' || result.getAttribute('data-type') === tabType) {
                    result.style.display = 'block';
                } else {
                    result.style.display = 'none';
                }
            });
        }
        
        function viewInNode(node, filePath) {
            // 切换到指定节点
            const nodeSelect = document.getElementById('model-node');
            nodeSelect.value = node;
            nodeSelect.dispatchEvent(new Event('change'));
            
            // 滚动到指定文件行
            setTimeout(() => {
                const rows = document.querySelectorAll('#model-table tr');
                rows.forEach(row => {
                    const firstCell = row.querySelector('td:first-child');
                    if (firstCell) {
                        const fileNameEl = firstCell.querySelector('.file-name');
                        const folderPathEl = firstCell.querySelector('.folder-path');
                        let fullPath = '';
                        
                        if (folderPathEl && fileNameEl) {
                            fullPath = folderPathEl.textContent.trim() + fileNameEl.textContent.trim();
                        } else if (fileNameEl) {
                            fullPath = fileNameEl.textContent.trim();
                        }
                        
                        if (fullPath === filePath) {
                            row.scrollIntoView({behavior: 'smooth', block: 'center'});
                            row.style.backgroundColor = '#e3f2fd';
                            setTimeout(() => {
                                row.style.backgroundColor = '';
                            }, 2000);
                        }
                    }
                });
            }, 500);
        }
        
        function editResult(node, filePath) {
            // 先切换到对应的节点
            const nodeSelect = document.getElementById('model-node');
            nodeSelect.value = node;
            nodeSelect.dispatchEvent(new Event('change'));
            
            // 然后触发编辑操作
            setTimeout(() => {
                const editButtons = document.querySelectorAll('.edit-model');
                editButtons.forEach(btn => {
                    if (btn.getAttribute('data-filename') === filePath) {
                        btn.click();
                    }
                });
            }, 500);
        }
        
        // 模型搜索功能
        function bindSearchEvents() {
            const searchInput = document.getElementById('model-search');
            const clearBtn = document.getElementById('clear-model-search');
            const countEl = document.getElementById('model-search-count');
            
            searchInput.addEventListener('input', function() {
                const searchTerm = this.value.toLowerCase();
                filterModels(searchTerm);
            });
            
            clearBtn.addEventListener('click', function() {
                searchInput.value = '';
                filterModels('');
            });
        }
        
        function filterModels(searchTerm) {
            const rows = document.querySelectorAll('#model-table tbody tr');
            let count = 0;
            
            rows.forEach(row => {
                const filePath = row.querySelector('td:first-child').textContent.toLowerCase();
                const url = row.querySelector('td:nth-child(2)').textContent.toLowerCase();
                
                if (searchTerm === '' || filePath.includes(searchTerm) || url.includes(searchTerm)) {
                    row.style.display = '';
                    count++;
                    
                    // 高亮搜索词
                    highlightSearchTerm(row, searchTerm);
                } else {
                    row.style.display = 'none';
                }
            });
            
            document.getElementById('model-search-count').textContent = `找到 ${count} 个结果`;
        }
        
        function highlightSearchTerm(row, searchTerm) {
            if (!searchTerm) {
                // 清除所有高亮
                row.querySelectorAll('.highlight').forEach(el => {
                    const parent = el.parentNode;
                    parent.replaceChild(document.createTextNode(el.textContent), el);
                    parent.normalize();
                });
                return;
            }
            
            // 处理文件路径
            const filePathCell = row.querySelector('td:first-child');
            const folderPathEl = filePathCell.querySelector('.folder-path');
            const fileNameEl = filePathCell.querySelector('.file-name');
            
            if (folderPathEl) {
                highlightTextInElement(folderPathEl, searchTerm);
            }
            if (fileNameEl) {
                highlightTextInElement(fileNameEl, searchTerm);
            }
            
            // 处理URL
            const urlCell = row.querySelector('td:nth-child(2)');
            highlightTextInElement(urlCell, searchTerm);
        }
        
        function highlightTextInElement(element, searchTerm) {
            const text = element.textContent;
            const lowerText = text.toLowerCase();
            const index = lowerText.indexOf(searchTerm);
            
            if (index === -1) {
                // 清除现有高亮
                while (element.querySelector('.highlight')) {
                    const highlight = element.querySelector('.highlight');
                    const parent = highlight.parentNode;
                    parent.replaceChild(document.createTextNode(highlight.textContent), highlight);
                    parent.normalize();
                }
                return;
            }
            
            // 清除现有高亮
            element.textContent = text;
            
            // 创建文本节点和高亮节点
            const beforeText = document.createTextNode(text.substring(0, index));
            const highlightText = document.createElement('span');
            highlightText.className = 'highlight';
            highlightText.textContent = text.substring(index, index + searchTerm.length);
            const afterText = document.createTextNode(text.substring(index + searchTerm.length));
            
            // 清空并重新添加节点
            element.textContent = '';
            element.appendChild(beforeText);
            element.appendChild(highlightText);
            element.appendChild(afterText);
        }
        
        // 自动加载文件功能
        function bindAutoLoadEvents() {
            const loadButtons = document.querySelectorAll('.load-file-btn');
            const statusEl = document.getElementById('upload-status');
            
            loadButtons.forEach(button => {
                button.addEventListener('click', function() {
                    const filePath = this.getAttribute('data-path');
                    const fileName = this.getAttribute('data-name');
                    
                    fetch('/load-file', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({file_path: filePath, file_name: fileName})
                    }).then(res => res.json())
                      .then(data => {
                          if (data.success) {
                              statusEl.className = 'status success';
                              statusEl.textContent = `成功加载文件: ${fileName}`;
                              // 重新加载页面以显示新内容
                              window.location.reload();
                          } else {
                              statusEl.className = 'status error';
                              statusEl.textContent = `加载失败: ${data.msg}`;
                          }
                      })
                      .catch(error => {
                          statusEl.className = 'status error';
                          statusEl.textContent = `加载出错: ${error.message}`;
                      });
                });
            });
        }
        
        // URL解析功能 - 增强版，支持从URL参数提取文件名并清理链接
        function bindUrlParsingEvent() {
            const urlInput = document.getElementById('new-url');
            const filenameInput = document.getElementById('new-filename');
            const parsingHint = document.getElementById('url-parsing-hint');
            
            urlInput.addEventListener('blur', function() {
                const url = this.value.trim();
                if (url) {
                    try {
                        // 解析URL
                        const urlObj = new URL(url);
                        let cleanUrl = url;
                        let extractedFilename = '';
                        
                        // 检查是否有name参数
                        if (urlObj.searchParams.has('name')) {
                            // 提取并解码name参数值
                            extractedFilename = decodeURIComponent(urlObj.searchParams.get('name'));
                            
                            // 创建清理后的URL（移除name参数）
                            urlObj.searchParams.delete('name');
                            cleanUrl = urlObj.toString();
                            
                            // 如果文件名输入框为空，则填充提取的文件名
                            if (!filenameInput.value) {
                                filenameInput.value = extractedFilename;
                            }
                            
                            // 更新URL输入框为清理后的URL
                            this.value = cleanUrl;
                            
                            // 显示解析成功提示
                            parsingHint.textContent = `已自动解析URL: 提取文件名 "${extractedFilename}" 并清理链接`;
                            parsingHint.className = 'url-parsing-hint visible';
                            
                            logToDebug(`URL解析成功: 提取文件名 "${extractedFilename}", 清理后URL: ${cleanUrl}`);
                        } else {
                            // 没有name参数，尝试从路径中提取文件名
                            const pathname = urlObj.pathname;
                            const filename = pathname.split('/').pop();
                            
                            // 如果文件名有意义且当前文件名输入为空，则自动填充
                            if (filename && filename.length > 3 && !filenameInput.value) {
                                filenameInput.value = filename;
                                parsingHint.textContent = `已自动提取文件名: "${filename}"`;
                                parsingHint.className = 'url-parsing-hint visible';
                                logToDebug(`从URL路径提取文件名: "${filename}"`);
                            } else {
                                // 隐藏提示
                                parsingHint.className = 'url-parsing-hint';
                            }
                        }
                    } catch (e) {
                        // 不是有效的URL，显示错误提示
                        parsingHint.textContent = `URL解析失败: 不是有效的URL格式 (${e.message})`;
                        parsingHint.className = 'url-parsing-hint visible error';
                        logToDebug('URL解析错误: ' + e.message);
                    }
                } else {
                    // 清空URL时隐藏提示
                    parsingHint.className = 'url-parsing-hint';
                }
            });
            
            // 输入URL时隐藏提示，直到失去焦点
            urlInput.addEventListener('focus', function() {
                parsingHint.className = 'url-parsing-hint';
            });
        }
        
        // 编辑弹窗功能
        function bindModalEvents() {
            const modal = document.getElementById('edit-modal');
            const cancelBtn = document.getElementById('cancel-edit');
            const saveBtn = document.getElementById('save-edit');
            
            cancelBtn.addEventListener('click', function() {
                modal.style.display = 'none';
            });
            
            // 点击模态框外部关闭
            window.addEventListener('click', function(event) {
                if (event.target === modal) {
                    modal.style.display = 'none';
                }
            });
            
            saveBtn.addEventListener('click', function() {
                const currentNode = document.getElementById('model-node').value;
                const originalFilename = document.getElementById('edit-original-filename').value;
                const newFilename = document.getElementById('edit-filename').value.trim();
                const newUrl = document.getElementById('edit-url').value.trim();
                
                if (!newFilename || !newUrl) {
                    alert('文件名和URL不能为空');
                    return;
                }
                
                fetch('/edit-model', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        node: currentNode,
                        original_filename: originalFilename,
                        new_filename: newFilename,
                        new_url: newUrl
                    })
                }).then(res => res.json())
                  .then(data => {
                      if (data.success) {
                          modal.style.display = 'none';
                          // 刷新当前节点数据
                          refreshCurrentNodeData();
                          // 启用保存按钮（如果是自动加载的文件）
                          if (currentFilePath) {
                              document.getElementById('save-btn').disabled = false;
                          }
                      } else {
                          alert('编辑失败: ' + data.msg);
                      }
                  })
                  .catch(error => {
                      alert('编辑出错: ' + error.message);
                  });
            });
        }
        
        // 文件操作功能
        function bindFileEvents() {
            const uploadForm = document.getElementById('upload-form');
            const downloadBtn = document.getElementById('download-btn');
            const statusEl = document.getElementById('upload-status');
            
            uploadForm.addEventListener('submit', function(e) {
                e.preventDefault();
                const formData = new FormData(this);
                
                fetch('/upload', {
                    method: 'POST',
                    body: formData
                }).then(res => res.json())
                  .then(data => {
                      if (data.success) {
                          statusEl.className = 'status success';
                          statusEl.textContent = '文件上传成功';
                          // 重新加载页面以显示新内容
                          window.location.reload();
                      } else {
                          statusEl.className = 'status error';
                          statusEl.textContent = '上传失败: ' + data.msg;
                      }
                  })
                  .catch(error => {
                      statusEl.className = 'status error';
                      statusEl.textContent = '上传出错: ' + error.message;
                  });
            });
            
            downloadBtn.addEventListener('click', function() {
                window.location.href = '/download';
            });
        }
        
        // 模型节点管理功能
        function bindModelEvents() {
            const nodeSelect = document.getElementById('model-node');
            const addNodeBtn = document.getElementById('add-node');
            const deleteNodeBtn = document.getElementById('delete-node');
            const addModelBtn = document.getElementById('add-model-item');
            const modelTable = document.getElementById('model-table');
            const firstPageBtn = document.getElementById('model-first');
            const prevPageBtn = document.getElementById('model-prev');
            const nextPageBtn = document.getElementById('model-next');
            const lastPageBtn = document.getElementById('model-last');
            const itemsPerPageSelect = document.getElementById('model-items-per-page');
            const pageButtons = document.querySelectorAll('.page-btn[data-page]');
            
            // 切换模型节点
            nodeSelect.addEventListener('change', function() {
                const node = this.value;
                window.location.href = `/?node=${encodeURIComponent(node)}&path_group=${encodeURIComponent(currentPathGroup)}`;
            });
            
            // 添加新节点
            addNodeBtn.addEventListener('click', function() {
                const newNode = prompt('请输入新节点名称:');
                if (newNode && newNode.trim()) {
                    const nodeName = newNode.trim();
                    fetch('/add-node', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({node: nodeName})
                    }).then(res => res.json())
                      .then(data => {
                          if (data.success) {
                              alert('节点添加成功');
                              window.location.href = `/?node=${encodeURIComponent(nodeName)}&path_group=${encodeURIComponent(currentPathGroup)}`;
                          } else {
                              alert('添加失败: ' + data.msg);
                          }
                      })
                      .catch(error => {
                          alert('添加出错: ' + error.message);
                      });
                }
            });
            
            // 删除当前节点
            deleteNodeBtn.addEventListener('click', function() {
                const currentNode = nodeSelect.value;
                if (confirm(`确定要删除节点 "${currentNode}" 吗？此操作不可恢复！`)) {
                    fetch('/delete-node', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({node: currentNode})
                    }).then(res => res.json())
                      .then(data => {
                          if (data.success) {
                              alert('节点删除成功');
                              window.location.href = `/?path_group=${encodeURIComponent(currentPathGroup)}`;
                          } else {
                              alert('删除失败: ' + data.msg);
                          }
                      })
                      .catch(error => {
                          alert('删除出错: ' + error.message);
                      });
                }
            });
            
            // 添加模型
            addModelBtn.addEventListener('click', function() {
                const folderPrefix = document.getElementById('folder-prefix').value.trim();
                const filename = document.getElementById('new-filename').value.trim();
                const url = document.getElementById('new-url').value.trim();
                const node = nodeSelect.value;
                
                // 组合文件夹前缀和文件名
                let fullPath = filename;
                if (folderPrefix) {
                    // 处理斜杠，确保格式正确
                    const normalizedPrefix = folderPrefix.endsWith('/') ? folderPrefix : folderPrefix + '/';
                    fullPath = normalizedPrefix + filename;
                }
                
                if (!filename || !url) {
                    alert('文件名和URL不能为空');
                    return;
                }
                
                fetch('/add-model', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        node: node,
                        filename: fullPath,
                        url: url
                    })
                }).then(res => res.json())
                  .then(data => {
                      if (data.success) {
                          // 清空输入框
                          document.getElementById('new-filename').value = '';
                          document.getElementById('new-url').value = '';
                          // 刷新当前节点数据
                          refreshCurrentNodeData();
                          // 启用保存按钮（如果是自动加载的文件）
                          if (currentFilePath) {
                              document.getElementById('save-btn').disabled = false;
                          }
                      } else {
                          alert('添加失败: ' + data.msg);
                      }
                  })
                  .catch(error => {
                      alert('添加出错: ' + error.message);
                  });
            });
            
            // 编辑模型
            modelTable.addEventListener('click', function(e) {
                if (e.target.classList.contains('edit-model')) {
                    const filename = e.target.getAttribute('data-filename');
                    const row = e.target.closest('tr');
                    const url = row.querySelector('td:nth-child(2)').textContent;
                    
                    // 填充模态框
                    document.getElementById('modal-title').textContent = `编辑 ${filename}`;
                    document.getElementById('modal-content').innerHTML = `
                        <input type="hidden" id="edit-original-filename" value="${filename}">
                        <div style="margin-bottom: 15px;">
                            <label style="display: block; margin-bottom: 5px;">文件路径:</label>
                            <input type="text" id="edit-filename" class="edit-input" value="${filename}">
                        </div>
                        <div>
                            <label style="display: block; margin-bottom: 5px;">下载链接:</label>
                            <input type="text" id="edit-url" class="edit-input" value="${url}">
                        </div>
                    `;
                    
                    // 显示模态框
                    document.getElementById('edit-modal').style.display = 'flex';
                }
            });
            
            // 删除模型
            modelTable.addEventListener('click', function(e) {
                if (e.target.classList.contains('delete-model')) {
                    const filename = e.target.getAttribute('data-filename');
                    const node = nodeSelect.value;
                    
                    if (confirm(`确定要删除 "${filename}" 吗？`)) {
                        fetch('/delete-model', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({
                                node: node,
                                filename: filename
                            })
                        }).then(res => res.json())
                          .then(data => {
                              if (data.success) {
                                  refreshCurrentNodeData();
                                  // 启用保存按钮（如果是自动加载的文件）
                                  if (currentFilePath) {
                                      document.getElementById('save-btn').disabled = false;
                                  }
                              } else {
                                  alert('删除失败: ' + data.msg);
                              }
                          })
                          .catch(error => {
                              alert('删除出错: ' + error.message);
                          });
                    }
                }
            });
            
            // 分页控制
            firstPageBtn.addEventListener('click', function() {
                navigateToPage(1);
            });
            
            prevPageBtn.addEventListener('click', function() {
                const currentPage = parseInt(document.querySelector('.page-btn.active').getAttribute('data-page'));
                if (currentPage > 1) {
                    navigateToPage(currentPage - 1);
                }
            });
            
            nextPageBtn.addEventListener('click', function() {
                const currentPage = parseInt(document.querySelector('.page-btn.active').getAttribute('data-page'));
                if (currentPage < modelTotalPages) {
                    navigateToPage(currentPage + 1);
                }
            });
            
            lastPageBtn.addEventListener('click', function() {
                navigateToPage(modelTotalPages);
            });
            
            itemsPerPageSelect.addEventListener('change', function() {
                const itemsPerPage = parseInt(this.value);
                updateItemsPerPage(itemsPerPage);
            });
            
            pageButtons.forEach(button => {
                button.addEventListener('click', function() {
                    const page = parseInt(this.getAttribute('data-page'));
                    navigateToPage(page);
                });
            });
        }
        
        function navigateToPage(page) {
            const currentNode = document.getElementById('model-node').value;
            const itemsPerPage = document.getElementById('model-items-per-page').value;
            window.location.href = `/?node=${encodeURIComponent(currentNode)}&page=${page}&per_page=${itemsPerPage}&path_group=${encodeURIComponent(currentPathGroup)}`;
        }
        
        function updateItemsPerPage(itemsPerPage) {
            const currentNode = document.getElementById('model-node').value;
            window.location.href = `/?node=${encodeURIComponent(currentNode)}&page=1&per_page=${itemsPerPage}&path_group=${encodeURIComponent(currentPathGroup)}`;
        }
        
        function refreshCurrentNodeData() {
            const currentNode = document.getElementById('model-node').value;
            const itemsPerPage = document.getElementById('model-items-per-page').value;
            window.location.href = `/?node=${encodeURIComponent(currentNode)}&per_page=${itemsPerPage}&path_group=${encodeURIComponent(currentPathGroup)}`;
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
    