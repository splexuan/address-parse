"""app.py HTTP 接口测试

运行：
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module

ADDRESS = '浙江省杭州市西湖区文三路138号 张三 13800138000'


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        app_module.app.config['TESTING'] = True
        # 500 分支会写日志，测试时静音
        app_module.app.logger.disabled = True
        self.client = app_module.app.test_client()


class TestParseEndpoint(ApiTestCase):
    def test_get_parse(self):
        resp = self.client.get('/api/parse', query_string={'address': ADDRESS})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data']['province'], '浙江省')
        self.assertEqual(payload['data']['area'], '西湖区')
        self.assertEqual(payload['data']['phone'], '13800138000')

    def test_post_parse(self):
        resp = self.client.post('/api/parse', json={'address': ADDRESS})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['data']['name'], '张三')

    def test_post_parse_with_text_filter(self):
        resp = self.client.post('/api/parse', json={
            'address': ADDRESS,
            'text_filter': ['电话'],
        })
        self.assertEqual(resp.status_code, 200)

    def test_get_parse_with_text_filter(self):
        resp = self.client.get('/api/parse', query_string={
            'address': ADDRESS,
            'text_filter': '电话',
        })
        self.assertEqual(resp.status_code, 200)

    def test_tree_mode_via_type_param(self):
        resp = self.client.post('/api/parse', json={'address': ADDRESS, 'type': 1})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['data']['city'], '杭州市')


class TestParameterValidation(ApiTestCase):
    """非法参数必须返回 400 而不是 500，也不能静默降级"""

    def test_missing_address(self):
        self.assertEqual(self.client.get('/api/parse').status_code, 400)
        self.assertEqual(self.client.post('/api/parse', json={}).status_code, 400)

    def test_non_string_address(self):
        resp = self.client.post('/api/parse', json={'address': 12345})
        self.assertEqual(resp.status_code, 400)

    def test_non_object_body(self):
        resp = self.client.post('/api/parse', json=[1, 2, 3])
        self.assertEqual(resp.status_code, 400)

    def test_invalid_type_is_rejected(self):
        resp = self.client.get('/api/parse', query_string={'address': ADDRESS, 'type': 'abc'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('type', resp.get_json()['message'])

    def test_out_of_range_type_is_rejected(self):
        resp = self.client.post('/api/parse', json={'address': ADDRESS, 'type': 5})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_name_max_length_is_rejected(self):
        resp = self.client.post('/api/parse', json={'address': ADDRESS, 'name_max_length': '四'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('name_max_length', resp.get_json()['message'])

    def test_out_of_range_name_max_length_is_rejected(self):
        resp = self.client.post('/api/parse', json={'address': ADDRESS, 'name_max_length': 0})
        self.assertEqual(resp.status_code, 400)

    def test_text_filter_must_be_list(self):
        resp = self.client.post('/api/parse', json={'address': ADDRESS, 'text_filter': '电话'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('text_filter', resp.get_json()['message'])

    def test_address_too_long_is_rejected(self):
        resp = self.client.post('/api/parse', json={
            'address': '浙' * (app_module.MAX_ADDRESS_LENGTH + 1),
        })
        self.assertEqual(resp.status_code, 400)

    def test_empty_string_params_use_defaults(self):
        resp = self.client.get('/api/parse', query_string={'address': ADDRESS, 'type': ''})
        self.assertEqual(resp.status_code, 200)


class TestErrorHandling(ApiTestCase):
    def test_internal_error_does_not_leak_details(self):
        with mock.patch.object(app_module, 'address_parse',
                               side_effect=RuntimeError('secret-internal-detail')):
            resp = self.client.post('/api/parse', json={'address': ADDRESS})

        self.assertEqual(resp.status_code, 500)
        message = resp.get_json()['message']
        self.assertNotIn('secret-internal-detail', message)
        self.assertNotIn('RuntimeError', message)

    def test_failure_response_shape(self):
        resp = self.client.get('/api/parse')
        payload = resp.get_json()
        self.assertFalse(payload['success'])
        self.assertEqual(payload['data'], {})
        self.assertTrue(payload['message'])


class TestOtherEndpoints(ApiTestCase):
    def test_health(self):
        resp = self.client.get('/api/health')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['status'], 'ok')

    def test_index_page(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    def test_docs_page(self):
        resp = self.client.get('/docs')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('地址解析 API 文档', resp.get_data(as_text=True))

    def test_unknown_route_returns_404(self):
        self.assertEqual(self.client.get('/not-exists').status_code, 404)


if __name__ == '__main__':
    unittest.main()
