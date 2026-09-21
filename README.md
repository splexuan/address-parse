# address-parse

中国大陆收货地址智能解析服务（Python / Flask）。

基于 [zh-address-parse](https://github.com/ldwonday/zh-address-parse) 的 Python 移植实现，行政区划数据来自国家地名信息库（2025 年 12 月版）。

支持从一段混杂的文本中自动拆解出 **省 / 市 / 区 / 详细地址 / 姓名 / 手机号 / 邮编**，并提供 HTTP API 与在线演示页面。

## 特性

- 双解析引擎：正则匹配（`type=0`，默认）与行政区划树查找（`type=1`）
- 自动提取手机号、邮政编码并做格式化清洗
- 基于百家姓 + 称呼词 + 地址关键词的收货人姓名识别
- 简称与后缀缺省补全：`浙江杭州西湖区` → `浙江省 / 杭州市 / 西湖区`
- 历史区划纠错：`蓟县` → `蓟州区`、`延庆县` → `延庆区`
- 直辖市与省直辖县级市特殊处理（`市辖区` 归一、`神农架 / 仙桃` 归入区县）
- 支持自定义过滤词与补充行政区划数据

## 快速开始

```bash
pip install -r requirements.txt
python app.py
```

启动后访问：

| 地址 | 说明 |
| --- | --- |
| http://localhost:8000/ | 演示页面 |
| http://localhost:8000/docs | API 文档 |
| http://localhost:8000/api/parse | 解析接口 |
| http://localhost:8000/api/health | 健康检查 |

可通过环境变量覆盖监听地址：`HOST`（默认 `0.0.0.0`）、`PORT`（默认 `8000`）。

## API

### GET /api/parse

```
/api/parse?address=浙江省杭州市西湖区文三路138号 张三 13800138000&type=0&name_max_length=4
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `address` | string | 是 | 待解析地址（需 URL 编码） |
| `type` | int | 否 | `0` 正则匹配（默认），`1` 树查找 |
| `name_max_length` | int | 否 | 姓名最大长度，默认 `4` |

### POST /api/parse

```bash
curl -X POST http://localhost:8000/api/parse \
  -H 'Content-Type: application/json' \
  -d '{
    "address": "浙江省杭州市西湖区文三路138号 张三 13800138000",
    "type": 0,
    "name_max_length": 4,
    "text_filter": ["电话", "联系人"]
  }'
```

### 响应

```json
{
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
}
```

## Python 调用

```python
from parser import address_parse

result = address_parse('浙江省杭州市西湖区文三路138号 张三 13800138000', {
    'type': 0,            # 0 正则匹配，1 树查找
    'textFilter': [],     # 预清洗的字段列表
    'nameMaxLength': 4,   # 中文姓名最大长度
})
print(result)
```

## 项目结构

```
address_parse/
├── app.py                    # Flask 服务：API、演示页、接口文档
├── parser.py                 # 解析核心：清洗、提取、省市区匹配、姓名识别
├── data/
│   ├── provinceList.json     # 省 / 市 / 区行政区划树
│   └── names.json            # 百家姓表
├── requirements.txt
├── gunicorn_conf.py          # Gunicorn 部署配置（可选）
└── uwsgi.ini                 # uWSGI 部署配置（可选）
```

## 部署

### Gunicorn

```bash
pip install gunicorn
gunicorn -c gunicorn_conf.py app:app
```

### uWSGI

```bash
uwsgi --ini uwsgi.ini
```

两个配置默认监听 `0.0.0.0:6653`，请按需修改 `bind` / `http` 与日志路径。

## 数据说明

行政区划数据为三级树形结构（省 / 市 / 区），节点包含 `code`、`name` 字段，可直接替换 `data/provinceList.json` 以更新区划。也可在运行时通过 `extraGovData` 选项补充：

```python
address_parse(text, {
    'extraGovData': {
        'province': [{'code': '990000', 'name': '某某省'}],
        'city': [{'code': '990100', 'name': '某某市', 'provinceCode': '990000'}],
        'area': [{'code': '990101', 'name': '某某区', 'cityCode': '990100', 'provinceCode': '990000'}],
    }
})
```

## 致谢

- 解析算法参考 [zh-address-parse](https://github.com/ldwonday/zh-address-parse)
- 行政区划数据来源：国家地名信息库

## License

MIT
