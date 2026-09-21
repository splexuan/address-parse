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
- 支持自定义过滤词与请求级补充行政区划数据（`extraGovData` 不会污染其他请求）

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

> `python app.py` 使用的是 Flask 自带服务器，仅适合开发调试，生产环境请用下面的部署方式。

## API

### GET /api/parse

```
/api/parse?address=浙江省杭州市西湖区文三路138号 张三 13800138000&type=0&name_max_length=4
```

请求参数（GET 与 POST 通用）：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `address` | string | 是 | 待解析地址（需 URL 编码），最长 2000 字符 |
| `type` | int | 否 | `0` 正则匹配（默认），`1` 树查找，取值 `0~1` |
| `name_max_length` | int | 否 | 姓名最大长度，默认 `4`，取值 `1~20` |
| `text_filter` | string[] | 否 | 预清洗词列表；GET 可重复传参，如 `text_filter=电话&text_filter=备注` |

参数非法（类型错误、超出范围、缺失 `address`）统一返回 **HTTP 400**。

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

失败时返回 `success: false` 与 `message`，`data` 为空对象：

```json
{ "success": false, "message": "缺少 address 参数", "data": {} }
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

`address_parse` 对参数做了归一化：`type` / `nameMaxLength` 传字符串会被转换，非法值回落到默认（分别为 `0` 和 `4`），`textFilter` 非列表时按空列表处理，函数不会因参数类型抛异常。

### 补充行政区划数据

`extraGovData` 是**请求级**的，只在本次调用的副本上合并，不会影响后续请求：

```python
address_parse('测试省测试市测试区某路1号 张三', {
    'extraGovData': {
        'province': [{'code': '990000', 'name': '测试省'}],
        'city': [{'code': '990100', 'name': '测试市', 'provinceCode': '990000'}],
        'area': [{'code': '990101', 'name': '测试区', 'cityCode': '990100',
                  'provinceCode': '990000'}],
    }
})
```

如果需要长期生效，可显式调用 `parser.set_extra_gov_data(...)` 修改进程级数据（多进程部署下各 worker 需各自设置）。

## 项目结构

```
address_parse/
├── app.py                    # Flask 服务：API、演示页、接口文档、参数校验
├── parser.py                 # 解析核心：清洗、提取、省市区匹配、姓名识别
├── data/
│   ├── provinceList.json     # 省 / 市 / 区行政区划树
│   └── names.json            # 百家姓表
├── tests/
│   ├── test_parser.py        # 解析核心回归测试
│   └── test_api.py           # HTTP 接口与参数校验测试
├── requirements.txt
├── gunicorn_conf.py          # Gunicorn 部署配置（可移植，环境变量驱动）
└── LICENSE
```

含本机绝对路径的服务器本地配置（`uwsgi.ini`、`.htaccess`、`*.pid`、`gunicorn_conf.local.py` 等）已列入 `.gitignore`，不会进入版本库。

## 测试

```bash
python -m unittest discover -s tests -t . -v
```

仅依赖标准库的 `unittest`，无需额外安装测试框架。当前 60 项用例覆盖两种解析模式、简称补全、省直辖县级单位、历史区划改名、邮编与手机号提取、姓名识别、参数归一化与接口参数校验。

## 部署

### Gunicorn（推荐，配置可移植）

配置项均可用环境变量覆盖，默认值与具体服务器无关：

```bash
pip install -r requirements.txt
gunicorn -c gunicorn_conf.py app:app
```

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `GUNICORN_BIND` | `0.0.0.0:8000` | 监听地址 |
| `GUNICORN_WORKERS` | `4` | 进程数 |
| `GUNICORN_THREADS` | `2` | 每进程线程数 |
| `GUNICORN_LOG_LEVEL` | `info` | 日志级别 |
| `GUNICORN_ACCESS_LOG` / `GUNICORN_ERROR_LOG` | `-` | 日志路径，默认输出到标准输出/错误 |
| `GUNICORN_PIDFILE` | `<项目目录>/gunicorn.pid` | 进程文件 |

需要以低权限用户运行时，请在命令行追加参数（不要写死在配置里，否则非 root 用户加载配置会失败）：

```bash
gunicorn -c gunicorn_conf.py --user www --group www app:app
```

### uWSGI

`uwsgi.ini` 含本机绝对路径与端口，属于服务器本地配置，不入版本库。需要时在项目根目录自行创建：

```ini
[uwsgi]
chdir=/path/to/address_parse
wsgi-file=/path/to/address_parse/app.py
callable=app
processes=4
threads=2
http=0.0.0.0:6653
master=true
uid=www
gid=www
pidfile=/path/to/address_parse/uwsgi.pid
daemonize=/path/to/address_parse/uwsgi.log
```

```bash
pip install uwsgi
uwsgi --ini uwsgi.ini
```

`chdir` 必须写成绝对路径：uWSGI 会先应用 `chdir` 再解析其余相对配置，且它不提供"环境变量缺省值"机制，写成 `%(ENV_XXX)` 时环境变量缺失会导致启动直接失败。

## 数据说明

行政区划数据为三级树形结构（省 / 市 / 区），节点包含 `code`、`name` 字段，可直接替换 `data/provinceList.json` 以更新区划。`parser.py` 在导入时加载数据，修改后需重启服务。

## 已知取舍

- 手机号仅识别 11 位手机号（可带 `+86`、`17951` 前缀或 `-` 分隔），不识别固定电话
- 姓名识别为启发式规则（姓氏表 + 称呼词 + 地址关键词黑名单），无法覆盖所有复姓与少数民族姓名
- 邮编识别要求 6 位数字前后不紧邻其他数字，且不能紧跟 `号 / 室 / 楼` 等门牌号后缀

## 致谢

- 解析算法参考 [zh-address-parse](https://github.com/ldwonday/zh-address-parse)（MIT）
- 行政区划数据来源：国家地名信息库

## License

[MIT](LICENSE)
