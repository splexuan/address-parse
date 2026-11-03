"""parser.py 回归测试

运行：
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parser
from parser import address_parse, clean_address, sort_address

STANDARD = '浙江省杭州市西湖区文三路138号 张三 13800138000'


class TestRegionParse(unittest.TestCase):
    """省市区解析"""

    def test_standard_address_both_modes(self):
        for parse_type in (0, 1):
            with self.subTest(parse_type=parse_type):
                r = address_parse(STANDARD, {'type': parse_type})
                self.assertEqual(r['province'], '浙江省')
                self.assertEqual(r['city'], '杭州市')
                self.assertEqual(r['area'], '西湖区')
                self.assertEqual(r['provinceCode'], '330000')
                self.assertEqual(r['cityCode'], '330100')
                self.assertEqual(r['areaCode'], '330106')
                self.assertEqual(r['detail'], '文三路138号')
                self.assertEqual(r['name'], '张三')
                self.assertEqual(r['phone'], '13800138000')

    def test_abbreviated_province_and_city(self):
        r = address_parse('浙江杭州西湖区文三路138号 赵六')
        self.assertEqual((r['province'], r['city'], r['area']),
                         ('浙江省', '杭州市', '西湖区'))

    def test_municipality(self):
        r = address_parse('上海市浦东新区陆家嘴世纪大道100号 孙七')
        self.assertEqual(r['province'], '上海市')
        self.assertEqual(r['area'], '浦东新区')

    def test_province_direct_county_goes_to_area(self):
        """省直辖县级单位应归入 area，city 置空"""
        r = address_parse('湖北省神农架林区松柏镇 张三')
        self.assertEqual(r['province'], '湖北省')
        self.assertEqual(r['city'], '')
        self.assertEqual(r['area'], '神农架林区')
        self.assertEqual(r['areaCode'], '429021')


class TestLegacyDistrictRename(unittest.TestCase):
    """历史区划改名：延庆县 → 延庆区、蓟县 → 蓟州区"""

    def test_legacy_county_suffix_removed_from_detail(self):
        for parse_type in (0, 1):
            with self.subTest(parse_type=parse_type):
                r = address_parse('北京市延庆县八达岭镇 李四', {'type': parse_type})
                self.assertEqual(r['area'], '延庆区')
                self.assertEqual(r['detail'], '八达岭镇')
                self.assertEqual(r['name'], '李四')

    def test_legacy_county_handled_by_fallback(self):
        for parse_type in (0, 1):
            with self.subTest(parse_type=parse_type):
                r = address_parse('天津市蓟县渔阳镇 张三', {'type': parse_type})
                self.assertEqual(r['area'], '蓟州区')
                self.assertEqual(r['detail'], '渔阳镇')

    def test_street_name_starting_with_shi_is_kept(self):
        """东区 + 东市街：街道名首字不能被当成残留后缀删掉"""
        r = address_parse('四川省攀枝花市东区东市街1号 张三')
        self.assertEqual(r['area'], '东区')
        self.assertEqual(r['detail'], '东市街1号')


class TestDetailAssembly(unittest.TestCase):
    """详细地址拼接"""

    def test_recognized_region_names_are_all_stripped(self):
        """重复写省市区时，三者都要被剔除（逐次替换会互相覆盖）"""
        r = address_parse('浙江省杭州市西湖区浙江省杭州市西湖区文三路138号 张三')
        self.assertEqual(r['province'], '浙江省')
        self.assertEqual(r['area'], '西湖区')
        for name in ('浙江省', '杭州市', '西湖区'):
            self.assertNotIn(name, r['detail'])
        self.assertIn('文三路138号', r['detail'])

    def test_detail_order_follows_input(self):
        """详细地址顺序必须稳定（用 set 去重会随哈希种子乱序）"""
        r = address_parse('浙江省杭州市西湖区文三路138号 A座 3单元 5号楼 张三')
        self.assertEqual(r['detail'], '文三路138号A座3单元5号楼')

    def test_detail_order_is_repeatable(self):
        text = '浙江省杭州市西湖区文三路138号 A座 3单元 5号楼 张三'
        results = {address_parse(text)['detail'] for _ in range(20)}
        self.assertEqual(len(results), 1, f'同一输入出现多种输出: {results}')


class TestExtraGovData(unittest.TestCase):
    """extraGovData 必须是请求级，不能污染进程状态"""

    EXTRA = {
        'province': [{'code': '990000', 'name': '测试省'}],
        'city': [{'code': '990100', 'name': '测试市', 'provinceCode': '990000'}],
        'area': [{'code': '990101', 'name': '测试区', 'cityCode': '990100',
                  'provinceCode': '990000'}],
    }
    ADDRESS = '测试省测试市测试区某路1号 张三'

    def test_extra_data_is_applied(self):
        r = address_parse(self.ADDRESS, {'extraGovData': self.EXTRA})
        self.assertEqual(r['province'], '测试省')
        self.assertEqual(r['city'], '测试市')
        self.assertEqual(r['area'], '测试区')
        self.assertEqual(r['areaCode'], '990101')

    def test_extra_data_does_not_leak_to_next_call(self):
        before = parser._BASE_GOV_DATA
        address_parse(self.ADDRESS, {'extraGovData': self.EXTRA})

        self.assertIs(parser._BASE_GOV_DATA, before)
        self.assertEqual(parser._BASE_GOV_DATA.provinces, before.provinces)

        r = address_parse(self.ADDRESS)
        self.assertEqual(r['province'], '')

    def test_extra_data_does_not_leak_in_tree_mode(self):
        address_parse(self.ADDRESS, {'type': 1, 'extraGovData': self.EXTRA})
        r = address_parse(self.ADDRESS, {'type': 1})
        self.assertEqual(r['province'], '')


class TestPhoneAndPostalCode(unittest.TestCase):
    """手机号与邮编"""

    def test_postal_code_recognized(self):
        r = address_parse('广东省深圳市南山区科技园南区粤海街道 王五 518057')
        self.assertEqual(r['postalCode'], '518057')
        self.assertEqual(r['name'], '王五')

    def test_six_digit_door_number_is_not_postal_code(self):
        """6 位门牌号不能被当成邮编摘走"""
        r = address_parse('浙江省杭州市西湖区文三路123456号 张三')
        self.assertEqual(r['postalCode'], '')
        self.assertEqual(r['detail'], '文三路123456号')

    def test_phone_formatted_with_dashes(self):
        r = address_parse('浙江省杭州市西湖区文三路138号 张三 138-0013-8000')
        self.assertEqual(r['phone'], '13800138000')

    def test_landline_like_number_not_matched_as_mobile(self):
        r = address_parse('浙江省杭州市西湖区文三路138号 张三 057188889999')
        self.assertEqual(r['phone'], '')


class TestCleanAddress(unittest.TestCase):
    """地址清洗"""

    def test_words_containing_shou_are_preserved(self):
        for text in (
            '北京市朝阳区回收路5号 张三',
            '广东省深圳市南山区收货点A 李四',
            '浙江省杭州市西湖区代收点 3号楼',
        ):
            with self.subTest(text=text):
                self.assertEqual(clean_address(text), text)

    def test_field_label_is_stripped(self):
        self.assertEqual(clean_address('收：张三'), '张三')
        self.assertEqual(clean_address('收件人：张三'), '张三')
        self.assertEqual(clean_address('寄: 张三'), '张三')

    def test_newline_and_special_chars(self):
        self.assertEqual(clean_address('浙江省杭州市\r\n文三路138号'), '浙江省杭州市 文三路138号')
        self.assertNotIn('#', clean_address('浙江省杭州市西湖区文三路138号#'))

    def test_custom_text_filter(self):
        self.assertEqual(clean_address('浙江省杭州市西湖区文三路138号 备注', ['备注']),
                         '浙江省杭州市西湖区文三路138号')


class TestNameDetection(unittest.TestCase):
    """姓名识别"""

    def test_normal_name_detected(self):
        self.assertEqual(address_parse('浙江省杭州市西湖区文三路138号 李四')['name'], '李四')

    def test_single_char_is_not_name(self):
        self.assertEqual(address_parse('张')['name'], '')

    def test_status_word_is_not_name(self):
        r = address_parse('浙江省杭州市西湖区文三路138号 已签收')
        self.assertEqual(r['name'], '')
        self.assertIn('已签收', r['detail'])

    def test_community_name_is_not_person_name(self):
        r = address_parse('北京市朝阳区幸福小区 3号楼')
        self.assertEqual(r['name'], '')
        self.assertIn('幸福小区', r['detail'])

    def test_school_name_is_not_person_name(self):
        r = address_parse('浙江省杭州市西湖区文一西路 学军小学')
        self.assertEqual(r['name'], '')

    def test_name_with_courtesy_title(self):
        r = address_parse('北京市朝阳区建国路88号 李四先生 13912345678')
        self.assertEqual(r['name'], '李四先生')

    def test_minority_name_is_detected(self):
        """姓氏表兜底不能误杀少数民族姓名"""
        r = address_parse('新疆维吾尔自治区乌鲁木齐市天山区解放南路1号 阿依古丽')
        self.assertEqual(r['name'], '阿依古丽')
        self.assertEqual(r['detail'], '解放南路1号')

    def test_urgent_status_word_is_not_name(self):
        r = address_parse('浙江省杭州市西湖区文三路138号 尽快送达')
        self.assertEqual(r['name'], '')


class TestSameNameDistrict(unittest.TestCase):
    """同名区县不能串到外省（徐州鼓楼区 vs 南京鼓楼区）"""

    def test_tree_mode_uses_city_scope(self):
        for parse_type in (0, 1):
            with self.subTest(parse_type=parse_type):
                r = address_parse('徐州市鼓楼区中山北路1号 张三',
                                  {'type': parse_type})
                self.assertEqual((r['city'], r['area'], r['areaCode']),
                                 ('徐州市', '鼓楼区', '320302'))

    def test_explicit_city_still_wins(self):
        r = address_parse('江苏省南京市鼓楼区中山北路1号 张三', {'type': 1})
        self.assertEqual(r['areaCode'], '320106')


class TestNameFalsePositives(unittest.TestCase):
    """小区 / 机构 / 状态词不能被当成姓名"""

    def test_place_or_community_name_is_not_name(self):
        for fragment in ('东方时代7幢1701', '妈妈驿站', '谢谢', '开发区',
                         '幸福家园'):
            with self.subTest(fragment=fragment):
                r = address_parse(f'浙江省杭州市西湖区文三路138号 {fragment}')
                self.assertEqual(r['name'], '')
                self.assertIn(fragment, r['detail'])

    def test_region_name_is_not_name(self):
        """与区县同名的片段（朝阳）不应被当成姓名"""
        r = address_parse('北京市朝阳区建国路88号 朝阳')
        self.assertEqual(r['name'], '')


class TestAdminNoise(unittest.TestCase):
    """层级之间残留的 州/地区/省/县 不能挡住下一级匹配"""

    def test_abbreviated_autonomous_prefecture(self):
        for parse_type in (0, 1):
            with self.subTest(parse_type=parse_type):
                r = address_parse('云南省文山州富宁县新华镇 张三',
                                  {'type': parse_type})
                self.assertEqual((r['city'], r['area'], r['areaCode']),
                                 ('文山壮族苗族自治州', '富宁县', '532628'))
                self.assertEqual(r['detail'], '新华镇')

    def test_prefecture_noise(self):
        for parse_type in (0, 1):
            with self.subTest(parse_type=parse_type):
                r = address_parse('贵州省毕节地区织金县 张三',
                                  {'type': parse_type})
                self.assertEqual((r['city'], r['area']), ('毕节市', '织金县'))

    def test_province_suffix_noise(self):
        for parse_type in (0, 1):
            with self.subTest(parse_type=parse_type):
                r = address_parse('广西省南宁市青秀区 张三',
                                  {'type': parse_type})
                self.assertEqual((r['province'], r['city'], r['area']),
                                 ('广西壮族自治区', '南宁市', '青秀区'))


class TestUnicodeWhitespace(unittest.TestCase):
    """全角空格不能把姓名 / 手机号粘在正文里"""

    def test_full_width_space_separated_fields(self):
        r = address_parse('北京市朝阳区建国路88号　李四　13912345678')
        self.assertEqual(r['phone'], '13912345678')
        self.assertEqual(r['name'], '李四')
        self.assertEqual(r['detail'], '建国路88号')


class TestStrictNameMode(unittest.TestCase):
    """严格姓名模式（opt-in）：没有可信信号时不输出姓名"""

    def test_name_next_to_phone(self):
        r = address_parse('浙江省杭州市西湖区文三路138号 张三 13800138000',
                          {'nameMode': 'strict'})
        self.assertEqual(r['name'], '张三')

    def test_name_with_marker(self):
        r = address_parse('收货人：张三 浙江省杭州市西湖区文三路138号',
                          {'nameMode': 'strict'})
        self.assertEqual(r['name'], '张三')

    def test_name_with_title(self):
        r = address_parse('浙江省杭州市西湖区文三路138号 李四先生',
                          {'nameMode': 'strict'})
        self.assertEqual(r['name'], '李四先生')

    def test_bare_name_without_signal_is_skipped(self):
        """已知取舍：空格分隔的裸姓名在严格模式下不输出"""
        r = address_parse('浙江省杭州市西湖区文三路138号 张三',
                          {'nameMode': 'strict'})
        self.assertEqual(r['name'], '')
        self.assertIn('张三', r['detail'])

    def test_snake_case_option(self):
        r = address_parse('浙江省杭州市西湖区文三路138号 张三 13800138000',
                          {'name_mode': 'strict'})
        self.assertEqual(r['name'], '张三')

    def test_invalid_mode_falls_back_to_loose(self):
        r = address_parse('浙江省杭州市西湖区文三路138号 张三',
                          {'nameMode': 'unknown'})
        self.assertEqual(r['name'], '张三')


class TestSortAddress(unittest.TestCase):
    """片段排序"""

    def test_all_matching_fragments_are_moved_up(self):
        self.assertEqual(
            sort_address(['文三路138号', '浙江省', '南京市', '玄武区', '杭州市']),
            ['浙江省', '南京市', '杭州市', '玄武区', '文三路138号'],
        )

    def test_order_within_group_is_preserved(self):
        self.assertEqual(sort_address(['杭州市', '南京市']), ['杭州市', '南京市'])


class TestParamNormalization(unittest.TestCase):
    """参数归一化（Python 直接调用时也可能传字符串）"""

    def test_string_params_do_not_raise(self):
        r = address_parse(STANDARD, {'type': '1', 'nameMaxLength': '4', 'textFilter': '电话'})
        self.assertEqual(r['area'], '西湖区')
        self.assertEqual(r['phone'], '13800138000')

    def test_tree_mode_used_when_type_is_string_one(self):
        r = address_parse('天津市蓟县渔阳镇 张三', {'type': '1'})
        self.assertEqual(r['detail'], '渔阳镇')

    def test_invalid_type_falls_back_to_regex_mode(self):
        r = address_parse(STANDARD, {'type': 'abc'})
        self.assertEqual(r['detail'], '文三路138号')

    def test_invalid_name_max_length_falls_back_to_default(self):
        r = address_parse('浙江省杭州市西湖区文三路138号 李四', {'nameMaxLength': '四'})
        self.assertEqual(r['name'], '李四')


class TestBoundary(unittest.TestCase):
    """边界输入"""

    def test_empty_address(self):
        r = address_parse('')
        self.assertEqual(r['detail'], '')
        self.assertEqual(r['province'], '')
        self.assertEqual(r['name'], '')

    def test_none_like_blank_address(self):
        r = address_parse('   ')
        self.assertEqual(r['detail'], '')

    def test_phone_only_address(self):
        r = address_parse('13800138000')
        self.assertEqual(r['phone'], '13800138000')
        self.assertEqual(r['detail'], '')

    def test_result_keys_are_stable(self):
        expected = {'phone', 'postalCode', 'province', 'city', 'area', 'detail',
                    'name', 'provinceCode', 'cityCode', 'areaCode'}
        self.assertEqual(set(address_parse(STANDARD)), expected)


if __name__ == '__main__':
    unittest.main()
