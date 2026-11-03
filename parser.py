"""
地址解析核心模块
基于 zh-address-parse (https://github.com/ldwonday/zh-address-parse) 的 Python 移植版
支持两种解析模式：正则匹配 (type=0) 和树查找 (type=1)
"""
import json
import re
import os
from typing import TypedDict, NamedTuple, List, Optional, Dict

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


# 区划名去后缀后仍保留至少 2 个字才登记简称（"江阴市"→"江阴"，"东区"不拆）
_REGION_SUFFIXES = [
    '特别行政区', '自治区', '自治州', '自治县', '自治旗', '地区', '新区',
    '省', '市', '区', '县', '旗', '盟', '州', '镇', '乡',
]
_PROVINCE_SUFFIXES = ['特别行政区', '自治区', '省', '市']
_PROVINCE_ETHNIC = ['维吾尔', '壮', '回']


def _add_region_name(names: set, name: str):
    """登记区划名及其去后缀简称（用于排除"江阴""朝阳"这类地名被当姓名）"""
    if not name:
        return
    names.add(name)
    for suffix in _REGION_SUFFIXES:
        if len(name) > len(suffix) + 1 and name.endswith(suffix):
            names.add(name[:-len(suffix)])
            break


def _build_region_names(provinces: List[GovData], cities: List[GovData],
                        areas: List[GovData]) -> frozenset:
    names = set()
    for region in provinces:
        _add_region_name(names, region.get('name', ''))
    for region in cities:
        _add_region_name(names, region.get('name', ''))
    for region in areas:
        _add_region_name(names, region.get('name', ''))

    # 省级简称：广西壮族自治区→广西、新疆维吾尔自治区→新疆、宁夏回族自治区→宁夏
    for province in provinces:
        name = province.get('name', '')
        for suffix in _PROVINCE_SUFFIXES:
            if name.endswith(suffix) and len(name) > len(suffix):
                name = name[:-len(suffix)]
                break
        for ethnic in _PROVINCE_ETHNIC:
            if name.endswith(ethnic + '族'):
                name = name[:-len(ethnic + '族')]
                break
        if name and name != province.get('name'):
            names.add(name)

    return frozenset(names)


class GovDataSet(NamedTuple):
    """一次解析所使用的行政区划数据集（基础数据 + 请求级补充数据）"""
    provinces: List[GovData]
    cities: List[GovData]
    areas: List[GovData]
    province_string: str
    city_string: str
    area_string: str
    region_names: frozenset


def _build_gov_data_set(provinces: List[GovData], cities: List[GovData],
                        areas: List[GovData]) -> GovDataSet:
    return GovDataSet(
        provinces=provinces,
        cities=cities,
        areas=areas,
        province_string=_compact_json(provinces),
        city_string=_compact_json(cities),
        area_string=_compact_json(areas),
        region_names=_build_region_names(provinces, cities, areas),
    )


# 进程级基础数据（不含任何请求级补充数据）
_BASE_GOV_DATA = _build_gov_data_set(_provinces, _cities, _areas)


def set_extra_gov_data(extra_gov_data: Dict[str, List[GovData]]):
    """向进程级基础数据中追加行政区划

    注意：这会改变本进程后续所有请求的解析结果，多进程部署时各进程也可能不一致。
    单次调用如需临时补充区划，请改用 address_parse 的 extraGovData 选项。
    """
    global _BASE_GOV_DATA

    _provinces.extend(extra_gov_data.get('province') or [])
    _cities.extend(extra_gov_data.get('city') or [])
    _areas.extend(extra_gov_data.get('area') or [])
    _BASE_GOV_DATA = _build_gov_data_set(_provinces, _cities, _areas)


def _resolve_gov_data(extra_gov_data: Dict[str, List[GovData]] = None) -> GovDataSet:
    """返回本次解析使用的数据集

    带 extraGovData 时在基础数据的副本上合并，不修改全局状态。
    """
    if not isinstance(extra_gov_data, dict):
        return _BASE_GOV_DATA

    extra_province = list(extra_gov_data.get('province') or [])
    extra_city = list(extra_gov_data.get('city') or [])
    extra_area = list(extra_gov_data.get('area') or [])
    if not (extra_province or extra_city or extra_area):
        return _BASE_GOV_DATA

    return _build_gov_data_set(
        _provinces + extra_province,
        _cities + extra_city,
        _areas + extra_area,
    )


# ============================================================
# 地址清洗
# ============================================================

_CLEAN_KEYWORDS = [
    '详细地址', '收货地址', '收件地址', '地址', '所在地区',
    '姓名', '收货人', '收件人', '联系人',
    '邮编', '联系电话', '电话', '联系人手机号码',
    '手机号码', '手机号',
    '自治区直辖县级行政区划', '省直辖县级行政区划', '直辖县级行政区划',
    '自治区直辖县', '省直辖县', '市辖区',
]

# 全角空格 / 不换行空格 / 其他 Unicode 空白 → 半角空格
# （粘贴来的地址常见「丰　县」「李四　139…」，不归一会导致字段粘连）
_UNICODE_SPACE_PATTERN = re.compile(
    '[\u3000\u00a0\u1680\u2000-\u200b\u202f\u205f\ufeff]'
)

# 字段标签（如"收：张三"）只在紧跟冒号时才剔除；
# 不能用单字"收"做关键词，否则"回收路""代收点"会被破坏
_CLEAN_LABEL_PATTERN = re.compile(r'(?:^|\s)[收寄发]\s*[:：]\s*')

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

    # 全角空格 / 不换行空格 / 其他 Unicode 空白 → 半角空格
    address = _UNICODE_SPACE_PATTERN.sub(' ', address)

    # 去除预定义关键字和自定义过滤词
    all_filters = _CLEAN_KEYWORDS + (text_filter or [])
    for keyword in all_filters:
        address = address.replace(keyword, ' ')

    # 去除"收：""寄："这类字段标签（保留 回收 / 代收 等正常用字）
    address = _CLEAN_LABEL_PATTERN.sub(' ', address)

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
# 邮编必须是"独立"的 6 位数字：前后都不能紧邻其它数字，避免从长数字串中截取
_POSTAL_CODE_REG = re.compile(r'(?<!\d)[1-9]\d{5}(?!\d)')
# 紧跟在这些字符后面的 6 位数字属于门牌号/房间号，不是邮编
_POSTAL_SUFFIX_CHARS = '号室栋楼层幢弄座组队村巷排期'


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
    """提取邮编

    仅当 6 位数字处于"非门牌号"上下文时才认定为邮编，
    否则"文三路123456号"这类门牌号会被误当成邮编摘走并破坏详细地址。
    """
    postal_code = ''
    for match in _POSTAL_CODE_REG.finditer(address):
        end = match.end()
        if end < len(address) and address[end] in _POSTAL_SUFFIX_CHARS:
            # 形如 123456号 / 100022室 → 门牌号、房间号
            continue
        if match.start() > 0 and address[match.start() - 1] in _POSTAL_SUFFIX_CHARS:
            continue
        postal_code = match.group(0)
        address = address[:match.start()] + ' ' + address[end:]
        break
    return address, postal_code


# ============================================================
# 地址片段排序
# ============================================================

_ORDER_KEYWORDS = ['省', '市', '区', '县', '镇']


def sort_address(split_address: List[str]) -> List[str]:
    """把包含 省/市/区/县/镇 的片段整体前移（按关键词分组，组内保持原顺序）

    原实现每个关键词只前移一个片段，同级的第二个市/区会被留在末尾。
    """
    result: List[str] = []
    for keyword in _ORDER_KEYWORDS:
        i = 0
        while i < len(split_address):
            if keyword in split_address[i]:
                result.append(split_address.pop(i))
            else:
                i += 1
    return result + split_address


# ============================================================
# 姓名识别
# ============================================================

_NAME_CALLS = ['先生', '小姐', '女士', '男士', '同志', '老师', '师傅',
               '哥哥', '姐姐', '妹妹', '弟弟',
               '妈妈', '爸爸', '爷爷', '奶奶', '姑姑', '舅舅']
_ADDR_FILTERS = ['街道', '乡镇', '镇', '乡', '路', '巷', '弄', '号', '楼',
                 '栋', '单元', '室', '座', '层', '门', '队', '组', '村',
                 # 常见非人名词尾，避免"幸福小区""学军小学"被当成姓名
                 '小区', '大厦', '大楼', '公寓', '花园', '广场', '中心',
                 '学校', '小学', '中学', '大学', '学院', '医院', '公司',
                 '工厂', '酒店', '宾馆', '超市', '驿站', '物业', '快递',
                 '代收', '门卫',
                 # 园区 / 小区 / 商业体名称，避免"烯望家园""开发区""科技城"被当成姓名
                 '家园', '园区', '公园', '开发区', '工业区', '城区', '新区',
                 '新城', '科技城', '产业园', '工业园', '物流园', '时代',
                 '花苑', '新苑', '雅苑', '地区', '中国', '生活区',
                 # 单字机构 / 地名后缀，中文姓名里几乎不会出现
                 '馆', '桥', '苑', '店', '铺', '场', '局', '所', '院', '校',
                 '站', '港', '岛', '湾', '塔', '寺', '庙', '堂', '厂', '矿',
                 '营', '屯', '庄', '坊', '里', '塘', '坝', '堤', '岸', '滩',
                 '区', '府', '头', '面']

# 兜底判定专用的地名特征字：只在片段首字不是百家姓时生效，
# 用来挡住"新馨园""于大桑树"这类小区名 / 村名。
# 江/山/海 故意不列：维吾尔族常见名"买买提江""艾山""艾海提"含这些字
_FALLBACK_ADDR_CHARS = [
    '园', '苑', '城', '府', '湾', '里', '庄', '屯', '营', '坊',
    '桥', '站', '场', '馆', '店', '铺', '院', '校', '所', '局',
    '部', '厂', '矿', '塔', '寺', '庙', '堂', '岸', '滩', '洲',
    '岛', '港', '湖', '河', '头', '面', '树',
    '沟', '塘', '坝', '堤', '坡', '岭', '泉', '溪', '井', '台',
    '集', '街', '道', '巷', '弄', '路', '村', '镇', '乡', '区',
    '县', '市', '州', '旗', '楼', '栋', '幢', '室', '座', '层',
    '门', '号', '组', '队',
]

# 长度同样在 2~4 之间、但显然不是姓名的状态/动作词
_NON_NAME_WORDS = ['签收', '已收', '待收', '拒收', '退回', '派送', '派件',
                   '送达', '发货', '收货', '谢谢', '麻烦', '尽快', '务必',
                   '备注', '急用', '联系', '到了', '请在', '放门口', '打电话',
                   '暂无', '无地址', '暂无地址', '没有']


def _contains_any(text: str, words) -> bool:
    return any(word in text for word in words)


def _is_name_shape(fragment: str, region_names=None) -> bool:
    """片段是否具备"可能是姓名"的基本形态

    三条硬性否决：不含中文、含数字（门牌号）、等于某个省/市/区县名。
    """
    if not fragment or not re.search(r'[一-龥]', fragment):
        return False
    if re.search(r'\d', fragment):
        return False
    if region_names and fragment in region_names:
        return False
    return True


def judge_fragment_is_name(fragment: str, name_max_length: int,
                           region_names=None) -> bool:
    """判断片段是否为人名"""
    if not _is_name_shape(fragment, region_names):
        return False

    # 地址关键词 / 状态词优先否决，否则"妈妈驿站"会被称呼词捞走
    if _contains_any(fragment, _ADDR_FILTERS):
        return False
    if _contains_any(fragment, _NON_NAME_WORDS):
        return False

    length = len(fragment)

    # 两字叠词（谢谢/慢慢/多多）不是姓名
    if length == 2 and fragment[0] == fragment[1]:
        return False

    # 包含称呼词 → 是人名；长度上限防止整句被当成姓名
    if _contains_any(fragment, _NAME_CALLS) and length <= name_max_length + 2:
        return True

    # 首字在百家姓中，且长度在 2 ~ nameMaxLength 之间
    if 1 < length <= name_max_length and fragment[0] in _zh_cn_names:
        return True

    # 检查复姓（同样受 nameMaxLength 约束，
    # 否则"东方时代7幢1701"这类长串会因以"东方"开头被当成复姓名）
    if 2 < length <= name_max_length and fragment[:2] in _zh_cn_names:
        return True

    return False


def _is_fallback_name(fragment: str, name_max_length: int,
                      region_names=None) -> bool:
    """兜底判定：至少 2 个字、含中文、不含地址关键词，也不是状态词

    注意不能要求首字是常见姓氏：少数民族姓名（如"阿依古丽"）会被误杀。
    """
    length = len(fragment)
    if length < 2 or length > name_max_length:
        return False
    if not _is_name_shape(fragment, region_names):
        return False
    if _contains_any(fragment, _ADDR_FILTERS):
        return False
    if _contains_any(fragment, _NON_NAME_WORDS):
        return False

    # 首字不是百家姓的片段，只要含地名/机构特征字就不当姓名
    if fragment[0] not in _zh_cn_names:
        if _contains_any(fragment, _FALLBACK_ADDR_CHARS):
            return False

    return True


def _has_name_title(fragment: str) -> bool:
    """是否含称呼词（先生/小姐/女士/老师/师傅…）——强人名信号"""
    return _contains_any(fragment, _NAME_CALLS)


def _name_has_signal(name: str, raw_original: str, raw_clean: str,
                     phone: str) -> bool:
    """严格模式：姓名是否带可信信号

    1) 收货人 / 收件人 / 联系人 / 姓名 标记（用清洗前的原文，清洗会删掉这些词）
    2) 姓名紧邻手机号（含"手机号：""电话："等）
    3) 结尾独立姓名（整串即姓名，或姓名前是标点）
    """
    if not name:
        return False
    escaped = re.escape(name)

    if raw_original and re.search(
            r'(收货人|收件人|联系人|联系人姓名|收货姓名|姓名)'
            r'\s*[:：]?\s*' + escaped, raw_original):
        return True

    if phone and raw_clean:
        escaped_phone = re.escape(phone)
        if re.search(escaped + r'\s*(?:手机号码|手机号|手机|电话|联系方式|'
                                 r'微信|联系)?\s*[:：]?\s*' + escaped_phone,
                     raw_clean):
            return True
        if re.search(escaped_phone + r'\s*[:：]?\s*' + escaped, raw_clean):
            return True

        idx = raw_clean.find(phone)
        if idx != -1:
            start = max(0, idx - len(name) - 4)
            window = raw_clean[start:idx + len(phone) + 2 * (len(name) + 4)]
            if name in window:
                return True

    # 结尾独立姓名：空格分隔不认——clean() 会把「，（）」折成空格，
    # 若放行空格，会把「…某小区 高岭坑」这类地名/机构名误收成姓名
    tail = raw_clean.strip()
    while tail and tail[-1] in '，,。.；;）)】]》> 　':
        tail = tail[:-1]
    if tail.endswith(name):
        before = tail[-len(name) - 1] if len(tail) > len(name) else ''
        if before == '' or before in '，,（(、/；;:：':
            return True

    return False


def _detect_name(details: List[str], name_max_length: int, region_names,
                 mode: str = 'loose', raw_original: str = '',
                 raw_clean: str = '', phone: str = '') -> str:
    """在详细地址片段中挑出姓名（优先取最短的候选片段）"""
    if not details:
        return ''

    sorted_details = sorted(details, key=len)

    for fragment in sorted_details:
        if not judge_fragment_is_name(fragment, name_max_length, region_names):
            continue
        if mode == 'strict':
            # 严格模式：只有拿到可信信号才认定为人名
            if _name_has_signal(fragment, raw_original, raw_clean, phone) \
                    or _has_name_title(fragment):
                return fragment
        else:
            return fragment

    if mode == 'strict':
        return ''

    first = sorted_details[0]
    if _is_fallback_name(first, name_max_length, region_names):
        return first
    return ''


# ============================================================
# 正则匹配解析 (type=0)
# ============================================================

# 出现在"残留后缀"之后时，说明该字其实是道路名的一部分（如"东市街"的"市"）
_STREET_FOLLOW_CHARS = '街路巷弄道'


def _strip_legacy_district_suffix(fragment: str, matched_prefix: str,
                                  area_name: str) -> str:
    """用户写的是旧区划名（延庆县）而官方名已改为 xx区 时，去掉残留的 县/市

    仅在"官方名 == 已识别前缀 + 区"时生效；再用 _STREET_FOLLOW_CHARS 排除
    "东区东市街"这类把街道名首字误当成残留后缀的情况。
    """
    if (matched_prefix and area_name == matched_prefix + '区'
            and fragment[:1] in ('县', '市')
            and fragment[1:2] not in _STREET_FOLLOW_CHARS):
        return fragment[1:]
    return fragment


def _match_name_prefix(fragment: str, name: str) -> str:
    """用名称的最长前缀去匹配片段开头（至少 2 个字）

    返回命中的前缀，未命中返回空串。
    """
    for i in range(len(name), 1, -1):
        candidate = name[:i]
        if fragment.startswith(candidate):
            return candidate
    return ''


# 匹配完上级后残留在片段开头的行政字（州/盟/省/县/旗），
# 用户常用缩写："文山州富宁县""毕节地区织金县""广西省南宁市"
_ADMIN_NOISE_MULTI = [
    '自治区直辖县级行政区划', '省直辖县级行政区划', '直辖县级行政区划',
    '自治区直辖县', '省直辖县', '地区',
]
# 故意不含 市/区：会误伤"市中区""城区"这类真实区名
_ADMIN_NOISE_FIRST = '州盟省县旗'


def _strip_leading_admin_noise(fragment: str) -> str:
    """去掉片段开头残留的行政后缀/噪声（不影响正文）

    只剥离不会作为行政区名首字的字符；后面紧跟街道类字符时视为正文
    （如「州前街」），不剥离。
    """
    for token in _ADMIN_NOISE_MULTI:
        if fragment.startswith(token):
            return fragment[len(token):]

    if fragment[:1] in _ADMIN_NOISE_FIRST:
        if fragment[1:2] not in _STREET_FOLLOW_CHARS:
            return fragment[1:]

    return fragment


def parse_region_with_regexp(fragment: str, has_parse_result: dict,
                            gov_data: GovDataSet = None) -> dict:
    """利用正则表达式在序列化的 JSON 中匹配省市区"""
    if gov_data is None:
        gov_data = _BASE_GOV_DATA
    province_string = gov_data.province_string
    city_string = gov_data.city_string
    area_string = gov_data.area_string

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
            matches = regex_province.findall(province_string)
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
        fragment_before_city = fragment
        fragment = _strip_leading_admin_noise(fragment)
        province_code = province[0]['code'] if province and province[0] else r'[0-9]{1,6}'
        for i in range(1, len(fragment)):
            s = fragment[:i + 1]
            regex_city = re.compile(
                r'\{"code":"[0-9]{1,6}","name":"' + re.escape(s) +
                r'[\u4E00-\u9FA5]*?","provinceCode":"' + province_code + r'"}'
            )
            matches = regex_city.findall(city_string)
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
                pm = regex_p.findall(province_string)
                if pm:
                    province = [json.loads(pm[0])]
        else:
            # 剥离噪声后仍没匹配到市，恢复原片段（避免吞掉正文）
            fragment = fragment_before_city

    # 匹配区级
    if len(area) == 0:
        fragment_before_area = fragment
        fragment = _strip_leading_admin_noise(fragment)
        province_code = province[0]['code'] if province and province[0] else r'[0-9]{1,6}'
        city_code = city[0]['code'] if city and city[0] else r'[0-9]{1,6}'
        for i in range(1, len(fragment)):
            s = fragment[:i + 1]
            regex_area = re.compile(
                r'\{"code":"[0-9]{1,9}","name":"' + re.escape(s) +
                r'[\u4E00-\u9FA5]*?","cityCode":"' + city_code +
                r'","provinceCode":"' + province_code + r'"}'
            )
            matches = regex_area.findall(area_string)
            if matches:
                obj = json.loads(matches[0])
                if len(matches) == 1:
                    area = [obj]
                    match_str = s
            else:
                break

        if area and area[0]:
            fragment = fragment.replace(match_str, '', 1) if match_str else fragment
            # 旧名→新名：延庆县 → 延庆区，去掉残留的"县"
            fragment = _strip_legacy_district_suffix(
                fragment, match_str, area[0]['name'])
            # 反推市和省
            if len(city) == 0:
                cc = area[0]['cityCode']
                regex_c = re.compile(
                    r'\{"code":"' + cc + r'","name":"[\u4E00-\u9FA5]+?","provinceCode":"' +
                    area[0]['provinceCode'] + r'"}'
                )
                cm = regex_c.findall(city_string)
                if cm:
                    city = [json.loads(cm[0])]
            if len(province) == 0:
                pc = area[0]['provinceCode']
                regex_p = re.compile(r'\{"code":"' + pc + r'","name":"[\u4E00-\u9FA5]+?"\}')
                pm = regex_p.findall(province_string)
                if pm:
                    province = [json.loads(pm[0])]

        # 容错：县→区（如蓟县→蓟州区、延庆县→延庆区）
        # 仅在已知省/市时启用：否则片段可能是未识别正文，
        # 全局匹配会串到外省同名区
        has_region_context = bool((province and province[0]) or (city and city[0]))
        if (len(area) == 0 and has_region_context
                and ('县' in fragment or '市' in fragment)):
            for old_suffix, new_suffix in [('县', '区'), ('市', '区')]:
                idx = fragment.find(old_suffix, 1)
                if idx == -1:
                    continue
                prefix = fragment[:idx]
                for i in range(len(prefix), 0, -1):
                    # 区名干必须紧贴 县/市 后缀；前缀多于一个字时，
                    # 不接受单字候选（避免"中国…"→中山区）
                    if i == 1 and len(prefix) > 1:
                        continue
                    s = prefix[len(prefix) - i:]
                    regex_area = re.compile(
                        r'\{"code":"[0-9]{1,9}","name":"' + re.escape(s) +
                        r'[\u4E00-\u9FA5]*?' + new_suffix +
                        r'","cityCode":"' + city_code +
                        r'","provinceCode":"' + province_code + r'"}'
                    )
                    matches = regex_area.findall(area_string)
                    if matches and len(matches) == 1:
                        area = [json.loads(matches[0])]
                        fragment = area[0]['name'] + fragment[idx + 1:]
                        break
                    elif matches and len(matches) > 1:
                        continue
                if area:
                    break

        if not area:
            # 剥离噪声后仍没匹配到区，恢复原片段（保留完整正文）
            fragment = fragment_before_area

    if len(fragment.strip()) > 0:
        detail.append(fragment.strip())

    return {'province': province, 'city': city, 'area': area, 'detail': detail}


# ============================================================
# 树查找解析 (type=1)
# ============================================================

def parse_region(fragment: str, has_parse_result: dict,
                 gov_data: GovDataSet = None) -> dict:
    """利用树向下查找解析省市区"""
    if gov_data is None:
        gov_data = _BASE_GOV_DATA
    provinces = gov_data.provinces
    cities = gov_data.cities
    areas = gov_data.areas

    province = list(has_parse_result.get('province', []))
    city = list(has_parse_result.get('city', []))
    area = list(has_parse_result.get('area', []))
    detail = []

    # 从省开始查找
    if not province or not province[0]:
        for temp_province in provinces:
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
        fragment_before_city = fragment
        fragment = _strip_leading_admin_noise(fragment)
        current_province = province[0] if province and province[0] else None

        for temp_city in cities:
            name = temp_city['name']
            pc = temp_city.get('provinceCode', '')

            if current_province and current_province['code'] != pc:
                continue

            replace_name = _match_name_prefix(fragment, name)
            if not replace_name:
                continue

            city = [temp_city]
            # 反推省
            if not current_province:
                for p in provinces:
                    if p['code'] == pc:
                        province = [p]
                        break
            fragment = fragment.replace(replace_name, '', 1)
            break

        if not city or not city[0]:
            # 剥离噪声后仍没匹配到市，恢复原片段（避免吞掉正文）
            fragment = fragment_before_city

    # 从区开始查找
    #
    # 分两轮：先按"市"精确匹配（徐州鼓楼区 vs 南京鼓楼区 只能靠市区分），
    # 第一轮没结果再退回按"省"匹配（省直辖县级市如仙桃、神农架）。
    current_province = province[0] if province and province[0] else None
    current_city = city[0] if city and city[0] else None

    fragment_before_area = fragment
    fragment = _strip_leading_admin_noise(fragment)

    if current_city is not None:
        scopes = ['city']
    elif current_province is not None:
        scopes = ['province']
    else:
        scopes = ['any']

    matched_area = None
    matched_prefix = ''
    for scope in scopes:
        # 同一 scope 内取"匹配前缀最长"的区县，避免共享前缀串名
        best_area = None
        best_prefix = ''
        best_len = 0

        for temp_area in areas:
            pc = temp_area.get('provinceCode', '')
            cc = temp_area.get('cityCode', '')

            if scope == 'city' and cc != current_city['code']:
                continue
            if scope == 'province' and pc != current_province['code']:
                continue

            replace_name = _match_name_prefix(fragment, temp_area['name'])
            if not replace_name:
                continue

            if len(replace_name) > best_len:
                best_len = len(replace_name)
                best_area = temp_area
                best_prefix = replace_name

        if best_area is not None:
            matched_area = best_area
            matched_prefix = best_prefix
            break

    if matched_area is not None:
        area = [matched_area]
        cc = matched_area.get('cityCode', '')
        pc = matched_area.get('provinceCode', '')

        if not current_city:
            for c in cities:
                if c['code'] == cc:
                    city = [c]
                    break
        if not current_province:
            for p in provinces:
                if p['code'] == pc:
                    province = [p]
                    break

        fragment = _strip_legacy_district_suffix(
            fragment.replace(matched_prefix, '', 1),
            matched_prefix, matched_area['name'])
    else:
        # 剥离噪声后仍没匹配到区，恢复原片段（保留完整正文）
        fragment = fragment_before_area

    # 容错：县→区（如蓟县→蓟州区、延庆县→延庆区）
    # 仅在已知省/市时启用，避免未识别正文串到外省同名区
    if (len(area) == 0
            and (current_province is not None or current_city is not None)
            and ('县' in fragment or '市' in fragment)):
        cc = current_city['code'] if current_city else ''
        pc = current_province['code'] if current_province else ''
        for old_suffix, new_suffix in [('县', '区'), ('市', '区')]:
            idx = fragment.find(old_suffix, 1)
            if idx == -1:
                continue
            prefix = fragment[:idx]
            for i in range(len(prefix), 0, -1):
                # 区名干必须紧贴 县/市 后缀；前缀多于一个字时，
                # 不接受单字候选（避免"中国…"→中山区）
                if i == 1 and len(prefix) > 1:
                    continue
                s = prefix[len(prefix) - i:]
                for temp_area in areas:
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
            - nameMode: loose（默认，宽松）/ strict（严格，需可信信号才输出姓名）
            - extraGovData: 额外的行政区划数据

    Returns:
        ParseResult: 包含 province, city, area, detail, name, phone, postalCode,
                     provinceCode, cityCode, areaCode 的字典
    """
    if options is None:
        options = {}

    extra_gov_data = options.get('extraGovData', options.get('extra_gov_data', {}))
    text_filter = options.get('textFilter', options.get('text_filter', []))
    name_max_length = options.get('nameMaxLength',
                                  options.get('name_max_length', 4))
    name_mode = options.get('nameMode', options.get('name_mode', 'loose'))
    if not isinstance(name_mode, str) or name_mode.lower() not in ('loose', 'strict'):
        name_mode = 'loose'
    else:
        name_mode = name_mode.lower()

    # 参数归一化：直接以 Python 调用本模块时也可能传入字符串
    try:
        parse_type = int(options.get('type', 0))
    except (TypeError, ValueError):
        parse_type = 0
    try:
        name_max_length = int(name_max_length)
    except (TypeError, ValueError):
        name_max_length = 4
    if not isinstance(text_filter, (list, tuple)):
        text_filter = []
    text_filter = [str(k) for k in text_filter]

    if not address:
        return {
            'phone': '', 'postalCode': '', 'province': '', 'city': '',
            'area': '', 'detail': '', 'name': '',
            'provinceCode': '', 'cityCode': '', 'areaCode': ''
        }

    # 本次请求使用的行政区划数据集（extraGovData 只在副本上合并，不污染全局）
    gov_data = _resolve_gov_data(extra_gov_data)

    parse_result = {
        'phone': '',
        'province': [],
        'city': [],
        'area': [],
        'detail': [],
        'name': '',
    }

    # 保留清洗前原文，供严格模式识别"收货人/联系人"等标记
    raw_original = address

    # 清洗地址
    address = clean_address(address, text_filter)

    # 保留"清洗后、去手机号前"的文本，供严格模式判断姓名是否紧邻手机号
    raw_clean = address

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
                parsed = parse_region(item, parse_result, gov_data)
            else:
                parsed = parse_region_with_regexp(item, parse_result, gov_data)

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
    # 必须在同一片段上累积替换：原实现用原始 item 逐个替换，后一次会覆盖前一次
    recognized_names = [obj['name'] for obj in (province_obj, city_obj, area_obj)
                        if obj and obj.get('name')]
    for i, item in enumerate(detail_list):
        for name in recognized_names:
            item = item.replace(name, '')
        detail_list[i] = item

    # 保序去重（set 的顺序受哈希随机化影响，会导致详细地址拼接顺序不稳定）
    detail_list = list(dict.fromkeys(d.strip() for d in detail_list if d.strip()))

    # 从详细地址中识别姓名
    if detail_list:
        name = _detect_name(detail_list, name_max_length, gov_data.region_names,
                            mode=name_mode, raw_original=raw_original,
                            raw_clean=raw_clean, phone=phone)
        if name:
            parse_result['name'] = name
            detail_list = [d for d in detail_list if d != name]

    # 处理城市名称（直辖市的"市辖区"等特殊名称用省份名替代）
    province_name = province_obj['name'] if province_obj else ''
    city_name = city_obj['name'] if city_obj else ''
    if city_name in ['市辖区', '区', '县', '镇']:
        city_name = province_name

    # 县级单位判定：city 匹配后 area 为空
    # 省直辖县级（code 含90）：移到 area，city 置空
    # 地级市直管（东莞/中山/嘉峪关等）：保留在 city
    if city_obj and not area_obj:
        for a in gov_data.areas:
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
