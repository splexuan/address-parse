"""
地址解析 HTTP API 服务（Flask 版）
基于 zh-address-parse 的中国大陆收货地址智能解析
行政区划数据：2025年12月版（国家地名信息库）

启动方式:
    python app.py
    或: flask run --host 0.0.0.0 --port 8000

访问:
    - 演示页面: http://localhost:8000/
    - API 说明: http://localhost:8000/docs
    - GET 解析: /api/parse?address=地址
    - POST 解析: /api/parse (JSON body)
"""
from flask import Flask, request, jsonify, render_template_string
from parser import address_parse

app = Flask(__name__)

# address 长度上限，避免超长文本占用解析资源
MAX_ADDRESS_LENGTH = 2000


# ============================================================
# 工具函数
# ============================================================

class ParamError(ValueError):
    """请求参数非法（对应 HTTP 400）"""


def _parse(address, parse_type=0, name_max_length=4, text_filter=None):
    """统一的解析调用"""
    options = {
        'type': parse_type,
        'textFilter': text_filter or [],
        'nameMaxLength': name_max_length,
    }
    return address_parse(address, options)


def _to_int(raw, field, default, min_value=None, max_value=None):
    """把请求参数转成 int，非法时抛 ParamError

    此前直接透传字符串，会在解析器内部抛 TypeError 返回 500，
    或（type 字段）静默落回默认模式导致与调用方预期不符。
    """
    if raw is None or raw == '':
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ParamError(f'{field} 必须是整数')
    if min_value is not None and value < min_value:
        raise ParamError(f'{field} 不能小于 {min_value}')
    if max_value is not None and value > max_value:
        raise ParamError(f'{field} 不能大于 {max_value}')
    return value


def _to_text_filter(raw):
    """text_filter 必须是字符串数组"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ParamError('text_filter 必须是字符串数组')
    return [str(item) for item in raw]


# ============================================================
# API 接口
# ============================================================

@app.route("/api/parse", methods=["GET", "POST"])
def api_parse():
    """
    地址解析接口，支持 GET 和 POST
    GET:  /api/parse?address=地址&type=0&name_max_length=4
    POST: {"address": "地址", "type": 0, "name_max_length": 4}
    """
    try:
        if request.method == "POST":
            data = request.get_json(force=True, silent=True) or {}
            if not isinstance(data, dict):
                raise ParamError("请求体必须是 JSON 对象")
            address = data.get("address", "")
            parse_type = _to_int(data.get("type"), "type", 0, 0, 1)
            name_max_length = _to_int(data.get("name_max_length"), "name_max_length", 4, 1, 20)
            text_filter = _to_text_filter(data.get("text_filter"))
        else:
            address = request.args.get("address", "")
            parse_type = _to_int(request.args.get("type"), "type", 0, 0, 1)
            name_max_length = _to_int(request.args.get("name_max_length"), "name_max_length", 4, 1, 20)
            text_filter = _to_text_filter(request.args.getlist("text_filter") or None)

        if not isinstance(address, str) or not address.strip():
            return jsonify({"success": False, "data": {}, "message": "缺少 address 参数"}), 400

        if len(address) > MAX_ADDRESS_LENGTH:
            return jsonify({
                "success": False,
                "data": {},
                "message": f"address 长度不能超过 {MAX_ADDRESS_LENGTH} 个字符",
            }), 400

        result = _parse(address, parse_type, name_max_length, text_filter)
        return jsonify({"success": True, "data": result, "message": "解析成功"})
    except ParamError as e:
        return jsonify({"success": False, "data": {}, "message": str(e)}), 400
    except Exception:
        # 详细信息只写日志，不回显给调用方
        app.logger.exception("解析地址失败")
        return jsonify({"success": False, "data": {}, "message": "解析失败，请稍后重试"}), 500


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "service": "地址解析 API"})


# ============================================================
# API 文档页
# ============================================================

DOCS_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API 文档 - 地址解析</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f7fa; padding: 40px 20px; }
        .container { max-width: 860px; margin: 0 auto; }
        h1 { font-size: 24px; color: #1a1a2e; margin-bottom: 8px; }
        .subtitle { color: #666; font-size: 14px; margin-bottom: 30px; }
        .section { background: #fff; border-radius: 10px; padding: 24px 28px; margin-bottom: 20px; box-shadow: 0 1px 6px rgba(0,0,0,0.05); }
        .section h2 { font-size: 18px; margin-bottom: 12px; color: #333; }
        .endpoint { background: #f0f4f8; border-radius: 6px; padding: 12px 16px; margin: 12px 0; }
        .method { display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 12px; font-weight: 700; margin-right: 8px; color: #fff; }
        .method.get { background: #22c55e; }
        .method.post { background: #3b82f6; }
        .endpoint .path { font-family: monospace; font-size: 14px; color: #1a1a2e; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 14px; }
        th { color: #666; font-weight: 600; background: #fafbfc; }
        td code { background: #f0f4f8; padding: 2px 6px; border-radius: 3px; font-size: 13px; }
        pre { background: #1a1a2e; color: #e2e8f0; padding: 16px; border-radius: 8px; overflow-x: auto; font-size: 13px; line-height: 1.6; margin: 10px 0; }
        .back { font-size: 14px; color: #4a90d9; text-decoration: none; }
        .back:hover { text-decoration: underline; }
    </style>
</head>
<body>
<div class="container">
    <a href="/" class="back">← 返回演示页</a>
    <h1 style="margin-top:12px;">地址解析 API 文档</h1>
    <p class="subtitle">中国大陆收货地址智能解析 · 基于国家地名信息库 2025年12月数据</p>

    <div class="section">
        <h2>GET /api/parse</h2>
        <p>通过 URL 参数传入地址，适合简单调用。</p>
        <div class="endpoint">
            <span class="method get">GET</span>
            <a class="path" href="{{ base_url }}/api/parse?address=%E6%B5%99%E6%B1%9F%E7%9C%81%E6%9D%AD%E5%B7%9E%E5%B8%82%E8%A5%BF%E6%B9%96%E5%8C%BA%E6%96%87%E4%B8%89%E8%B7%AF138%E5%8F%B7%20%E5%BC%A0%E4%B8%89%2013800138000&type=0&name_max_length=4" target="_blank" style="font-family:monospace;font-size:14px;color:#1a1a2e;text-decoration:none;">{{ base_url }}/api/parse?address=地址&type=0&name_max_length=4</a>
        </div>
        <table>
            <tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>
            <tr><td><code>address</code></td><td>string</td><td>✅</td><td>待解析的地址字符串（需 URL 编码），最长 2000 字符</td></tr>
            <tr><td><code>type</code></td><td>int</td><td>否</td><td>0=正则匹配（默认），1=树查找，取值 0~1</td></tr>
            <tr><td><code>name_max_length</code></td><td>int</td><td>否</td><td>姓名最大长度，默认 4，取值 1~20</td></tr>
            <tr><td><code>text_filter</code></td><td>string[]</td><td>否</td><td>预清洗词列表，可重复传参，如 <code>text_filter=电话</code></td></tr>
        </table>
        <p><strong>示例（点击可测试）：</strong></p>
        <pre><a href="{{ base_url }}/api/parse?address=%E6%B5%99%E6%B1%9F%E7%9C%81%E6%9D%AD%E5%B7%9E%E5%B8%82%E8%A5%BF%E6%B9%96%E5%8C%BA%E6%96%87%E4%B8%89%E8%B7%AF138%E5%8F%B7%20%E5%BC%A0%E4%B8%89%2013800138000&type=0&name_max_length=4" target="_blank" style="color:#66b3ff;">{{ base_url }}/api/parse?address=%E6%B5%99%E6%B1%9F%E7%9C%81%E6%9D%AD%E5%B7%9E%E5%B8%82%E8%A5%BF%E6%B9%96%E5%8C%BA%E6%96%87%E4%B8%89%E8%B7%AF138%E5%8F%B7%20%E5%BC%A0%E4%B8%89%2013800138000&type=0&name_max_length=4</a></pre>
    </div>

    <div class="section">
        <h2>POST /api/parse</h2>
        <p>通过 JSON Body 传入地址和可选参数。</p>
        <div class="endpoint">
            <span class="method post">POST</span>
            <span class="path">/api/parse</span>
        </div>
        <pre>{
  "address": "浙江省杭州市西湖区文三路138号 张三 13800138000",
  "type": 0,
  "name_max_length": 4,
  "text_filter": ["电话", "联系人"]
}</pre>
    </div>

    <div class="section">
        <h2>响应格式</h2>
        <pre>{
  "success": true,
  "message": "解析成功",
  "data": {
    "province": "浙江省",
    "provinceCode": "330000",
    "city": "杭州市",
    "cityCode": "330100",
    "area": "西湖区",
    "areaCode": "330106",
    "detail": "文三路138号",
    "name": "张三",
    "phone": "13800138000",
    "postalCode": ""
  }
}</pre>
    </div>

    <div class="section">
        <h2>health</h2>
        <div class="endpoint">
            <span class="method get">GET</span>
            <a class="path" href="{{ base_url }}/api/health" target="_blank" style="font-family:monospace;font-size:14px;color:#1a1a2e;text-decoration:none;">{{ base_url }}/api/health</a>
        </div>
        <p>健康检查接口。<a href="{{ base_url }}/api/health" target="_blank" style="color:#4a90d9;">点击测试 →</a></p>
    </div>
</div>
</body>
</html>
"""


@app.route("/docs")
def docs_page():
    base_url = request.url_root.rstrip("/")
    return render_template_string(DOCS_HTML, base_url=base_url)


# ============================================================
# 演示页面
# ============================================================

DEMO_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>地址解析 Demo</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
            background: #f5f7fa;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            padding: 40px 20px;
        }
        .container { width: 100%; max-width: 800px; }
        .header-row { display: flex; align-items: center; justify-content: center; gap: 16px; margin-bottom: 4px; }
        .header-row h1 { margin-bottom: 0; color: #1a1a2e; font-size: 28px; }
        .header-row a {
            display: inline-block; padding: 6px 16px; background: #4a90d9; color: #fff;
            border-radius: 6px; text-decoration: none; font-size: 13px; font-weight: 500;
        }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; font-size: 14px; }
        .card { background: #fff; border-radius: 12px; padding: 30px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); margin-bottom: 20px; }
        .card-title { font-size: 16px; font-weight: 600; color: #333; margin-bottom: 16px; }
        textarea {
            width: 100%; height: 120px; padding: 14px; border: 1.5px solid #e0e0e0;
            border-radius: 8px; font-size: 15px; resize: vertical; transition: border-color .2s; line-height: 1.6;
        }
        textarea:focus { outline: none; border-color: #4a90d9; }
        .options-row { display: flex; gap: 20px; margin-top: 16px; flex-wrap: wrap; align-items: center; }
        .option-group { display: flex; align-items: center; gap: 8px; }
        .option-group label { font-size: 14px; color: #555; white-space: nowrap; }
        .option-group select, .option-group input { padding: 6px 10px; border: 1.5px solid #e0e0e0; border-radius: 6px; font-size: 14px; }
        .option-group select:focus, .option-group input:focus { outline: none; border-color: #4a90d9; }
        #nameMaxLength { width: 70px; }
        button {
            padding: 10px 32px; background: #4a90d9; color: #fff; border: none;
            border-radius: 8px; font-size: 15px; cursor: pointer; transition: background .2s; font-weight: 500;
        }
        button:hover { background: #357abd; }
        .result-card { display: none; }
        .result-card.show { display: block; }
        .result-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
        .result-item { background: #f8f9fc; border-radius: 8px; padding: 14px; border: 1px solid #eee; }
        .result-item .label { font-size: 12px; color: #999; margin-bottom: 4px; }
        .result-item .value { font-size: 15px; color: #1a1a2e; word-break: break-all; }
        .result-item .value.empty { color: #ccc; font-style: italic; }
        .example-item {
            padding: 10px 14px; background: #f8f9fc; border-radius: 6px;
            margin-bottom: 8px; cursor: pointer; font-size: 14px; color: #444;
            border: 1px solid #eee; transition: all .15s;
        }
        .example-item:hover { background: #eef3ff; border-color: #4a90d9; }
        .api-link { text-align: center; font-size: 13px; color: #999; margin-top: 20px; }
        .api-link a { color: #4a90d9; }
        .api-link code { background: #f0f4f8; padding: 1px 5px; border-radius: 3px; }
    </style>
</head>
<body>
<div class="container">
    <div class="header-row">
        <h1>地址解析</h1>
        <a href="/docs" target="_blank">API 文档</a>
    </div>
    <p class="subtitle">基于 zh-address-parse · 中国大陆收货地址智能解析</p>

    <div class="card">
        <div class="card-title">输入地址</div>
        <textarea id="addressInput" placeholder="请输入需要解析的收货地址...
例如：浙江省杭州市西湖区文三路138号 张三 13800138000"></textarea>
        <div class="options-row">
            <div class="option-group">
                <label for="parseType">解析模式</label>
                <select id="parseType">
                    <option value="0">正则匹配</option>
                    <option value="1">树查找</option>
                </select>
            </div>
            <div class="option-group">
                <label for="nameMaxLength">姓名最大长度</label>
                <input type="number" id="nameMaxLength" value="4" min="2" max="10">
            </div>
            <button onclick="doParse()">开始解析</button>
        </div>
    </div>

    <div class="card result-card" id="resultCard">
        <div class="card-title">解析结果</div>
        <div class="result-grid" id="resultGrid"></div>
    </div>

    <div class="card">
        <div class="card-title">示例地址（点击填充）</div>
        <div class="example-item" onclick="fillExample(this)">浙江省杭州市西湖区文三路138号 张三 13800138000</div>
        <div class="example-item" onclick="fillExample(this)">北京市朝阳区建国路88号SOHO现代城A座 李四先生 13912345678</div>
        <div class="example-item" onclick="fillExample(this)">广东省深圳市南山区科技园南区粤海街道 王五 518057</div>
        <div class="example-item" onclick="fillExample(this)">上海市浦东新区陆家嘴金融贸易区世纪大道100号 赵六</div>
        <div class="example-item" onclick="fillExample(this)">四川省成都市武侯区天府大道中段500号 孙七 18600001111</div>
    </div>

    <p class="api-link">
        <a href="/docs" target="_blank">API 文档</a> ·
        GET: <code>/api/parse?address=地址</code> ·
        POST: <code>/api/parse</code> (JSON)
    </p>
</div>

<script>
    async function doParse() {
        const address = document.getElementById('addressInput').value.trim();
        if (!address) return alert('请先输入地址');

        const type = parseInt(document.getElementById('parseType').value);
        const nameMaxLength = parseInt(document.getElementById('nameMaxLength').value) || 4;

        try {
            const resp = await fetch('/api/parse', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ address, type, name_max_length: nameMaxLength })
            });
            const json = await resp.json();
            const data = json.data || {};

            const fields = [
                { key: 'name', label: '姓名' },
                { key: 'phone', label: '手机号' },
                { key: 'province', label: '省', sub: 'provinceCode' },
                { key: 'city', label: '市', sub: 'cityCode' },
                { key: 'area', label: '区/县', sub: 'areaCode' },
                { key: 'detail', label: '详细地址' },
                { key: 'postalCode', label: '邮编' },
            ];

            const grid = document.getElementById('resultGrid');
            grid.innerHTML = fields.map(f => {
                const v = data[f.key] || '';
                const cls = v ? '' : 'empty';
                const subInfo = f.sub && data[f.sub] ? '<br><span style="font-size:11px;color:#aaa;">代码: ' + data[f.sub] + '</span>' : '';
                return '<div class="result-item"><div class="label">' + f.label + '</div><div class="value ' + cls + '">' + (v || '(未识别)') + subInfo + '</div></div>';
            }).join('');

            document.getElementById('resultCard').classList.add('show');
        } catch (e) {
            alert('请求失败: ' + e.message);
        }
    }

    function fillExample(el) {
        document.getElementById('addressInput').value = el.innerText;
        doParse();
    }
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(DEMO_HTML)


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(host=host, port=port, debug=False)
