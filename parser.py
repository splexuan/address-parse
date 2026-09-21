"""
地址解析核心模块
基于 zh-address-parse (https://github.com/ldwonday/zh-address-parse) 的 Python 移植版
支持两种解析模式：正则匹配 (type=0) 和树查找 (type=1)
"""
import json
import re
import os
from typing import TypedDict, List, Optional, Dict

# ============================================================
# 数据加载
# ============================================================

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

with open(os.path.join(DATA_DIR, 'provinceList.json'), 'r', encoding='utf-8') as f:
    _address_json = json.load(f)

with open(os.path.join(DATA_DIR, 'names.json'), 'r', encoding='utf-8') as f:
    _zh_cn_names: List[str] = json.load(f)


class GovData(TypedDict):
    code: str
    name: str
    provinceCode: Optional[str]
    cityCode: Optional[str]


class ParseResult(TypedDict):
    phone: str
    postalCode: str
    province: str
    city: str
    area: str
    detail: str
    name: str
    provinceCode: str
    cityCode: str
    areaCode: str


class ParseOptions(TypedDict, total=False):
    type: int           # 0: 正则, 1: 树查找
    textFilter: List[str]
    nameMaxLength: int
    extraGovData: Dict[str, List[GovData]]


# 过滤特殊行政区划（名称包含"行政区划"的城市扁平化，子节点提升）
_filter_city = ['行政区划']
for item in _address_json:
    if item.get('children'):
        children_to_add = []
        indices_to_remove = []
        for city_index, city in enumerate(item['children']):
            for f in _filter_city:
                if f in city['name']:
                    if city.get('children'):
                        children_to_add.extend(city['children'])
                    indices_to_remove.append(city_index)
        for i in sorted(indices_to_remove, reverse=True):
            item['children'].pop(i)
        item['children'].extend(children_to_add)

# 构建扁平化的省/市/区列表
_provinces: List[GovData] = []
for cur in _address_json:
    item = {k: v for k, v in cur.items() if k != 'children'}
    _provinces.append(item)

_cities: List[GovData] = []
for cur in _address_json:
    if cur.get('children'):
        for city in cur['children']:
            item = {k: v for k, v in city.items() if k != 'children'}
            item['provinceCode'] = cur['code']
            _cities.append(item)

_areas: List[GovData] = []
for cur in _address_json:
    province_code = cur['code']
    if cur.get('children'):
        for city in cur['children']:
            city_code = city['code']
            if city.get('children'):
                for area in city['children']:
                    item = {k: v for k, v in area.items() if k != 'children'}
                    item['cityCode'] = city_code
                    item['provinceCode'] = province_code
                    _areas.append(item)

# 序列化为 JSON 字符串（用于正则匹配）
def _compact_json(obj):
    """紧凑JSON序列化（无空格，匹配JS的JSON.stringify格式）"""
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))

_province_string = _compact_json(_provinces)
_city_string = _compact_json(_cities)
_area_string = _compact_json(_areas)


def set_extra_gov_data(extra_gov_data: Dict[str, List[GovData]]):
    """设置额外的国家地理信息数据"""
    global _provinces, _province_string, _cities, _city_string, _areas, _area_string

    if extra_gov_data.get('province'):
        _provinces.extend(extra_gov_data['province'])
        _province_string = _compact_json(_provinces)

    if extra_gov_data.get('city'):
        _cities.extend(extra_gov_data['city'])
        _city_string = _compact_json(_cities)

    if extra_gov_data.get('area'):
        _areas.extend(extra_gov_data['area'])
        _area_string = _compact_json(_areas)


# ============================================================
# 地址清洗
# ============================================================

_CLEAN_KEYWORDS = [
    '详细地址', '收货地址', '收件地址', '地址', '所在地区',
    '姓名', '收货人', '收件人', '联系人', '收',
    '邮编', '联系电话', '电话', '联系人手机号码',
    '手机号码', '手机号',
    '自治区直辖县级行政区划', '省直辖县级行政区划', '市辖区',
]

_SPECIAL_CHAR_PATTERN = re.compile(
    r"[`~!@#$^&*()=|{}':;',\[\]\.<>/?~！@#￥……&*（）——|{}【】'；：""'。，、？]"
)

# 非数字之间的 - 替换为空格（保留 1-1-2406 这类房号格式）
_DASH_SEP_PATTERN = re.compile(r'(?<!\d)-(?!\d)')

_MUNICIPALITY = ['北京', '上海', '天津', '重庆']


def clean_address(address: str, text_filter: List[str] = None) -> str:
    """清洗地址文本"""
    # 去换行和制表符
    address = address.replace('\r\n', ' ').replace('\n', ' ').replace('\t', ' ')

    # 去除预定义关键字和自定义过滤词
    all_filters = _CLEAN_KEYWORDS + (text_filter or [])
    for keyword in all_filters:
        address = address.replace(keyword, ' ')

    # 非数字间的 - 替换为空格（保留 1-1-2406 之类房号）
    address = _DASH_SEP_PATTERN.sub(' ', address)

    # 去除特殊符号
    address = _SPECIAL_CHAR_PATTERN.sub(' ', address)

    # 合并多个空格
    address = re.sub(r' {2,}', ' ', address)

    # 修正直辖市重复名称（如 "北京北京" → "北京"）
    for m in _MUNICIPALITY:
        address = address.replace(m + m, m)

    return address.strip()


# ============================================================
# 手机号和邮编提取
# ============================================================

_MOBILE_REG = re.compile(r'(?:0|\+?86-?|17951)?1[3456789]\d{9}(?:-\d{4})?')
_POSTAL_CODE_REG = re.compile(r'[1-9]\d{5}(?!\d)')


def filter_phone(address: str) -> tuple:
    """提取手机号"""
    phone = ''
    # 整理电话格式
    address = re.sub(r'(\d{3})-(\d{4})-(\d{4})', r'\1\2\3', address)
    address = re.sub(r'(\d{3}) (\d{4}) (\d{4})', r'\1\2\3', address)

    match = _MOBILE_REG.search(address)
    if match:
        phone = match.group(0)
        address = address.replace(match.group(0), ' ')

    # 去除国际区号前缀
    phone = re.sub(r'^\+?86-?', '', phone)
    return address, phone


def filter_postal_code(address: str) -> tuple:
    """提取邮编"""
    postal_code = ''
    match = _POSTAL_CODE_REG.search(address)
    if match:
        postal_code = match.group(0)
        address = address.replace(match.group(0), ' ')
    return address, postal_code


# ============================================================
# 地址片段排序
# ============================================================

def sort_address(split_address: List[str]) -> List[str]:
    """按省市区县镇排序，包含这些关键词的片段排前面"""
    result = []
    for keyword in ['省', '市', '区', '县', '镇']:
        for i, item in enumerate(split_address):
            if keyword in item:
                result.append(split_address.pop(i))
                break
    return result + split_address


# ============================================================
# 姓名识别
# ============================================================

_NAME_CALLS = ['先生', '小姐', '同志', '哥哥', '姐姐', '妹妹', '弟弟',
               '妈妈', '爸爸', '爷爷', '奶奶', '姑姑', '舅舅']
_ADDR_FILTERS = ['街道', '乡镇', '镇', '乡', '路', '巷', '弄', '号', '楼',
                   '栋', '单元', '室', '座', '层', '门', '队', '组', '村']


def judge_fragment_is_name(fragment: str, name_max_length: int) -> bool:
    """判断片段是否为人名"""
    if not fragment or not re.search(r'[\u4E00-\u9FA5]', fragment):
        return False

    # 包含称呼词 → 是人名
    for call in _NAME_CALLS:
        if call in fragment:
            return True

    # 包含地址关键词 → 不是人名
    for f in _ADDR_FILTERS:
        if f in fragment:
            return False

    # 首字在百家姓中，且长度在 2 ~ nameMaxLength 之间
    name_first = fragment[0]
    if 1 < len(fragment) <= name_max_length and name_first in _zh_cn_names:
        return True

    # 检查复姓
    if len(fragment) > 2 and fragment[:2] in _zh_cn_names:
        return True

    return False


# ============================================================
# 正则匹配解析 (type=0)
# ============================================================

def parse_region_with_regexp(fragment: str, has_parse_result: dict) -> dict:
    """利用正则表达式在序列化的 JSON 中匹配省市区"""
    province = list(has_parse_result.get('province', []))
    city = list(has_parse_result.get('city', []))
    area = list(has_parse_result.get('area', []))
    detail = []

    match_str = ''

    # 匹配省级
    if len(province) == 0:
        for i in range(1, len(fragment)):
            s = fragment[:i + 1]
            regex_province = re.compile(
                r'\{"code":"[0-9]{1,6}","name":"' + re.escape(s) + r'[\u4E00-\u9FA5]*?"\}'
            )
            matches = regex_province.findall(_province_string)
            if matches:
                obj = json.loads(matches[0])
                if len(matches) == 1:
                    province = [obj]
                    match_str = s
            else:
                break

        if province and province[0]:
            fragment = fragment.replace(match_str, '', 1) if match_str else fragment

    # 匹配市级
    if len(city) == 0:
        province_code = province[0]['code'] if province and province[0] else r'[0-9]{1,6}'
        for i in range(1, len(fragment)):
            s = fragment[:i + 1]
            regex_city = re.compile(
                r'\{"code":"[0-9]{1,6}","name":"' + re.escape(s) +
                r'[\u4E00-\u9FA5]*?","provinceCode":"' + province_code + r'"}'
            )
            matches = regex_city.findall(_city_string)
            if matches:
                obj = json.loads(matches[0])
                if len(matches) == 1:
                    city = [obj]
                    match_str = s
            else:
                break

        if city and city[0]:
            fragment = fragment.replace(match_str, '', 1) if match_str else fragment
            # 如果没匹配到省，通过市的 provinceCode 反推
            if len(province) == 0:
                pc = city[0]['provinceCode']
                regex_p = re.compile(r'\{"code":"' + pc + r'","name":"[\u4E00-\u9FA5]+?"\}')
                pm = regex_p.findall(_province_string)
                if pm:
                    province = [json.loads(pm[0])]

    # 匹配区级
    if len(area) == 0:
        province_code = province[0]['code'] if province and province[0] else r'[0-9]{1,6}'
        city_code = city[0]['code'] if city and city[0] else r'[0-9]{1,6}'
        for i in range(1, len(fragment)):
            s = fragment[:i + 1]
            regex_area = re.compile(
                r'\{"code":"[0-9]{1,9}","name":"' + re.escape(s) +
                r'[\u4E00-\u9FA5]*?","cityCode":"' + city_code +
                r'","provinceCode":"' + province_code + r'"}'
            )
            matches = regex_area.findall(_area_string)
            if matches:
                obj = json.loads(matches[0])
                if len(matches) == 1:
                    area = [obj]
                    match_str = s
            else:
                break

        if area and area[0]:
            fragment = fragment.replace(match_str, '', 1) if match_str else fragment
            # 反推市和省
            if len(city) == 0:
                cc = area[0]['cityCode']
                regex_c = re.compile(
                    r'\{"code":"' + cc + r'","name":"[\u4E00-\u9FA5]+?","provinceCode":"' +
                    area[0]['provinceCode'] + r'"}'
                )
                cm = regex_c.findall(_city_string)
                if cm:
                    city = [json.loads(cm[0])]
            if len(province) == 0:
                pc = area[0]['provinceCode']
                regex_p = re.compile(r'\{"code":"' + pc + r'","name":"[\u4E00-\u9FA5]+?"\}')
                pm = regex_p.findall(_province_string)
                if pm:
                    province = [json.loads(pm[0])]

        # 容错：县→区（如蓟县→蓟州区、延庆县→延庆区）
        if len(area) == 0 and ('县' in fragment or '市' in fragment):
            for old_suffix, new_suffix in [('县', '区'), ('市', '区')]:
                idx = fragment.find(old_suffix, 1)
                if idx == -1:
                    continue
                prefix = fragment[:idx]
                for i in range(len(prefix), 0, -1):
                    s = prefix[:i]
                    regex_area = re.compile(
                        r'\{"code":"[0-9]{1,9}","name":"' + re.escape(s) +
                        r'[\u4E00-\u9FA5]*?' + new_suffix +
                        r'","cityCode":"' + city_code +
                        r'","provinceCode":"' + province_code + r'"}'
                    )
                    matches = regex_area.findall(_area_string)
                    if matches and len(matches) == 1:
                        area = [json.loads(matches[0])]
                        fragment = area[0]['name'] + fragment[idx + 1:]
                        break
                    elif matches and len(matches) > 1:
                        continue
                if area:
                    break

    if len(fragment.strip()) > 0:
        detail.append(fragment.strip())

    return {'province': province, 'city': city, 'area': area, 'detail': detail}


# ============================================================
# 树查找解析 (type=1)
# ============================================================

def parse_region(fragment: str, has_parse_result: dict) -> dict:
    """利用树向下查找解析省市区"""
    province = list(has_parse_result.get('province', []))
    city = list(has_parse_result.get('city', []))
    area = list(has_parse_result.get('area', []))
    detail = []

    # 从省开始查找
    if not province or not province[0]:
        for temp_province in _provinces:
            name = temp_province['name']
            replace_name = ''
            for i in range(len(name), 1, -1):
                temp = name[:i]
                if fragment.startswith(temp):
                    replace_name = temp
                    break
            if replace_name:
                province = [temp_province]
                fragment = fragment.replace(replace_name, '', 1)
                break

    # 从市开始查找
    if not city or not city[0]:
        current_province = province[0] if province and province[0] else None
        for temp_city in _cities:
            name = temp_city['name']
            pc = temp_city.get('provinceCode', '')

            if current_province:
                if current_province['code'] != pc:
                    continue
                replace_name = ''
                for i in range(len(name), 1, -1):
                    temp = name[:i]
                    if fragment.startswith(temp):
                        replace_name = temp
                        break
                if replace_name:
                    city = [temp_city]
                    fragment = fragment.replace(replace_name, '', 1)
                    break
            else:
                replace_name = ''
                for i in range(len(name), 1, -1):
                    temp = name[:i]
                    if fragment.startswith(temp):
                        replace_name = temp
                        break
                if replace_name:
                    city = [temp_city]
                    # 反推省
                    for p in _provinces:
                        if p['code'] == pc:
                            province = [p]
                            break
                    fragment = fragment.replace(replace_name, '', 1)
                    break

    # 从区开始查找
    current_province = province[0] if province and province[0] else None
    current_city = city[0] if city and city[0] else None

    for temp_area in _areas:
        name = temp_area['name']
        pc = temp_area.get('provinceCode', '')
        cc = temp_area.get('cityCode', '')

        if current_province or current_city:
            match_province = current_province and current_province['code'] == pc
            match_city = current_city and current_city['code'] == cc

            if match_province or match_city:
                replace_name = ''
                for i in range(len(name), 1, -1):
                    temp = name[:i]
                    if fragment.startswith(temp):
                        replace_name = temp
                        break
                if replace_name:
                    area = [temp_area]
                    if not current_city:
                        for c in _cities:
                            if c['code'] == cc:
                                city = [c]
                                break
                    if not current_province:
                        for p in _provinces:
                            if p['code'] == pc:
                                province = [p]
                                break
                    fragment = fragment.replace(replace_name, '', 1)
                    break
        else:
            replace_name = ''
            for i in range(len(name), 1, -1):
                temp = name[:i]
                if fragment.startswith(temp):
                    replace_name = temp
                    break
            if replace_name:
                area = [temp_area]
                for c in _cities:
                    if c['code'] == cc:
                        city = [c]
                        break
                for p in _provinces:
                    if p['code'] == pc:
                        province = [p]
                        break
                fragment = fragment.replace(replace_name, '', 1)
                break

    # 容错：县→区（如蓟县→蓟州区、延庆县→延庆区）
    if len(area) == 0 and ('县' in fragment or '市' in fragment):
        cc = current_city['code'] if current_city else ''
        pc = current_province['code'] if current_province else ''
        for old_suffix, new_suffix in [('县', '区'), ('市', '区')]:
            idx = fragment.find(old_suffix, 1)
            if idx == -1:
                continue
            prefix = fragment[:idx]
            for i in range(len(prefix), 0, -1):
                s = prefix[:i]
                for temp_area in _areas:
                    name = temp_area['name']
                    if name.startswith(s) and name.endswith(new_suffix):
                        if (not pc or temp_area.get('provinceCode') == pc) and \
                           (not cc or temp_area.get('cityCode') == cc):
                            area = [temp_area]
                            fragment = name + fragment[idx + 1:]
                            break
                if area:
                    break
            if area:
                break

    if fragment.strip():
        detail.append(fragment.strip())

    return {'province': province, 'city': city, 'area': area, 'detail': detail}


# ============================================================
# 主解析函数
# ============================================================

def address_parse(address: str, options: ParseOptions = None) -> ParseResult:
    """
    解析中国收货地址

    Args:
        address: 需要解析的地址字符串
        options: 可选配置
            - type: 0 正则匹配（默认），1 树查找
            - textFilter: 预清洗的字段列表
            - nameMaxLength: 中文名最大长度，默认 4
            - extraGovData: 额外的行政区划数据

    Returns:
        ParseResult: 包含 province, city, area, detail, name, phone, postalCode,
                     provinceCode, cityCode, areaCode 的字典
    """
    if options is None:
        options = {}

    parse_type = options.get('type', 0)
    extra_gov_data = options.get('extraGovData', {})
    text_filter = options.get('textFilter', [])
    name_max_length = options.get('nameMaxLength', 4)

    if not address:
        return {
            'phone': '', 'postalCode': '', 'province': '', 'city': '',
            'area': '', 'detail': '', 'name': '',
            'provinceCode': '', 'cityCode': '', 'areaCode': ''
        }

    # 设置额外行政区划数据
    if extra_gov_data:
        set_extra_gov_data(extra_gov_data)

    parse_result = {
        'phone': '',
        'province': [],
        'city': [],
        'area': [],
        'detail': [],
        'name': '',
    }

    # 清洗地址
    address = clean_address(address, text_filter)

    # 提取手机号
    address, phone = filter_phone(address)
    parse_result['phone'] = phone

    # 提取邮编
    address, postal_code = filter_postal_code(address)
    parse_result['postalCode'] = postal_code

    # 地址分割并排序
    split_addr = address.split(' ')
    split_addr = [item.strip() for item in split_addr
                  if item.strip() and not re.match(r'^\d+$', item.strip())]
    split_addr = sort_address(split_addr)

    # 逐片段解析省市区
    for item in split_addr:
        if (not parse_result['province'] or not parse_result['province'][0] or
                not parse_result['city'] or not parse_result['city'][0] or
                not parse_result['area'] or not parse_result['area'][0]):
            if parse_type == 1:
                parsed = parse_region(item, parse_result)
            else:
                parsed = parse_region_with_regexp(item, parse_result)

            parse_result['province'] = parsed.get('province', []) or parse_result['province']
            parse_result['area'] = parsed.get('area', []) or parse_result['area']
            parse_result['city'] = parsed.get('city', []) or parse_result['city']
            parse_result['detail'].extend(parsed.get('detail', []))
            parse_result['areaCode'] = (parse_result['area'][0]['code']
                                        if parse_result['area'] else '')
            parse_result['provinceCode'] = (parse_result['province'][0]['code']
                                            if parse_result['province'] else '')
            parse_result['cityCode'] = (parse_result['city'][0]['code']
                                        if parse_result['city'] else '')
        else:
            parse_result['detail'].append(item)

    province_obj = parse_result['province'][0] if parse_result['province'] else None
    city_obj = parse_result['city'][0] if parse_result['city'] else None
    area_obj = parse_result['area'][0] if parse_result['area'] else None
    detail_list = parse_result['detail']

    # 从详细地址中去掉已识别的省市区名称
    for i, item in enumerate(detail_list):
        for obj in [province_obj, city_obj, area_obj]:
            if obj and obj['name'] in item:
                detail_list[i] = item.replace(obj['name'], '')

    # 去重
    detail_list = list({d for d in detail_list if d.strip()})

    # 从详细地址中识别姓名
    if detail_list:
        copy_detail = sorted(
            [d for d in detail_list if d.strip()],
            key=lambda x: len(x)
        )
        name = ''
        for d in copy_detail:
            if judge_fragment_is_name(d, name_max_length):
                name = d
                break

        if not name and copy_detail:
            first = copy_detail[0]
            # 即使 judge_fragment_is_name 返回了 False，也要检查是否包含地址关键词
            has_addr_keyword = any(kw in first for kw in _ADDR_FILTERS)
            if (len(first) <= name_max_length and
                    re.search(r'[\u4E00-\u9FA5]', first) and
                    not has_addr_keyword):
                name = first

        if name:
            parse_result['name'] = name
            try:
                detail_list.remove(name)
            except ValueError:
                pass

    # 处理城市名称（直辖市的"市辖区"等特殊名称用省份名替代）
    province_name = province_obj['name'] if province_obj else ''
    city_name = city_obj['name'] if city_obj else ''
    if city_name in ['市辖区', '区', '县', '镇']:
        city_name = province_name

    # 县级单位判定：city 匹配后 area 为空
    # 省直辖县级（code 含90）：移到 area，city 置空
    # 地级市直管（东莞/中山/嘉峪关等）：保留在 city
    if city_obj and not area_obj:
        for a in _areas:
            if a.get('code') == city_obj['code'] and a.get('name') == city_obj['name']:
                if city_obj['code'][2:4] == '90':
                    # 省直辖县级（如神农架 429021、仙桃 429004）
                    area_obj = a
                    city_obj = None
                    city_name = ''
                    parse_result['areaCode'] = parse_result.get('cityCode', '')
                    parse_result['cityCode'] = ''
                break

    # 地级市直管：area 和 city 同名且同 code → 清除 area
    if city_obj and area_obj and area_obj.get('code') == city_obj['code']:
        if city_obj['code'][2:4] != '90':
            area_obj = None
            parse_result['areaCode'] = ''

    return {
        'phone': parse_result.get('phone', ''),
        'postalCode': parse_result.get('postalCode', ''),
        'province': province_name,
        'city': city_name,
        'area': area_obj['name'] if area_obj else '',
        'detail': ''.join(detail_list) if detail_list else '',
        'name': parse_result.get('name', ''),
        'provinceCode': parse_result.get('provinceCode', ''),
        'cityCode': parse_result.get('cityCode', ''),
        'areaCode': parse_result.get('areaCode', ''),
    }
