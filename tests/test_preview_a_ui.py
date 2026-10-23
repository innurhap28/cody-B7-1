"""Dependency-free integration tests for the isolated preview, not B/C integration."""
import importlib.util
import json
from pathlib import Path
import threading
import socket
from concurrent.futures import ThreadPoolExecutor
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preview_a_ui', ROOT/'scripts/preview_a_ui.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = preview.make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.server.state.reset()

    def request(self, path, body=None, headers=None):
        req = Request(self.url+path, data=None if body is None else json.dumps(body).encode(), headers=headers or {})
        try:
            response = urlopen(req, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw and 'application/json' in response.headers.get('Content-Type', '') else raw

    def login(self):
        self.assertEqual(self.request('/api/auth/login', dict(email='preview@example.invalid', password='MOCK-ONLY-123'))[0], 200)

    def test_idle_preconnect_does_not_block_login(self):
        # Browsers may open a speculative TCP connection without sending headers.
        # The original single-threaded HTTPServer blocked the next GET here.
        with socket.create_connection(self.server.server_address, timeout=2) as idle:
            with socket.create_connection(self.server.server_address, timeout=2) as partial:
                partial.sendall(b'GET /login HTTP/1.1\r\n')
                self.assertEqual(self.request('/login')[0], 200)
                self.assertEqual(self.request('/static/js/auth.js')[0], 200)

    def test_concurrent_creates_are_serialized(self):
        self.login()
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda _: self.request('/api/conversations', {}), range(12)))
        self.assertTrue(all(status == 201 for status, _ in results))
        self.assertEqual(len({item['conversation_id'] for _, item in results}), 12)
        self.assertEqual(len(self.server.state.conversations), 12)

    def test_template_render_and_fixed_identity(self):
        for page in ('/login', '/signup'):
            status, raw = self.request(page)
            self.assertEqual(status, 200)
            html = raw.decode()
            self.assertIn('MOCK / A UI', html)
            self.assertNotIn('{{', html)
            self.assertNotIn('{%', html)
            self.assertNotIn('type="password"', html)
            self.assertIn('value="preview@example.invalid" readonly', html)
            self.assertIn('value="MOCK-ONLY-123" readonly', html)
        self.assertNotIn('id="password-confirm"', self.request('/login')[1].decode())
        self.assertIn('id="password-confirm"', self.request('/signup')[1].decode())

    def test_real_credentials_rejected(self):
        self.assertEqual(self.request('/api/auth/signup', dict(email='someone@example.org', password='do-not-use-real-passwords'))[0], 422)
        self.assertFalse(self.server.state.logged_in)
        self.assertEqual(set(vars(self.server.state)), {'logged_in','conversations','turns','scenario'})

    def test_signup_login_logout(self):
        fixed = dict(email='preview@example.invalid', password='MOCK-ONLY-123')
        self.assertEqual(self.request('/api/auth/signup', fixed)[0], 200)
        self.assertEqual(self.request('/api/me')[0], 401)
        self.login()
        self.assertEqual(self.request('/api/me')[1]['email'], fixed['email'])
        self.assertEqual(self.request('/api/auth/logout', {})[0], 204)
        self.assertEqual(self.request('/api/me')[0], 401)

    def test_workflow_and_history_snapshot(self):
        self.login()
        _, item = self.request('/api/conversations', {'title':'MOCK'})
        cid = item['conversation_id']
        def chat(action, version, **extra):
            return self.request('/api/chat', dict(conversation_id=cid, expected_version=version, action=action, message='MOCK', **extra))
        self.assertEqual(chat('generate',0)[0], 409)
        self.assertEqual(chat('message',0)[1]['phase'], 'briefing')
        self.assertEqual(chat('message',1)[1]['phase'], 'ready')
        result = chat('generate',2)[1]
        self.assertEqual(result['script']['revision'], 1)
        self.assertTrue(result['brief']['confirmed'])
        self.assertEqual(chat('revise',3,base_script_id=999)[0], 409)
        result = chat('revise',3,base_script_id=1)[1]
        self.assertEqual(result['script']['revision'], 2)
        turns = self.request(f'/api/me/chats?conversation_id={cid}')[1]['items']
        self.assertEqual(len(turns), 4)
        self.assertEqual(turns[1]['response']['script']['revision'], 1)
        self.assertEqual(self.request(f'/api/conversations/{cid}')[1]['version'],4)
        self.assertEqual(chat('message',0)[0],409)

    def test_each_error_is_one_shot(self):
        for scenario, (status, code) in preview.ERRORS.items():
            with self.subTest(scenario=scenario):
                self.login()
                cid = self.request('/api/conversations', {})[1]['conversation_id']
                self.assertEqual(self.request('/__preview/scenario', {'scenario':scenario})[0],200)
                body=dict(conversation_id=cid,expected_version=0,action='message',message='MOCK')
                failed = self.request('/api/chat',body)
                self.assertEqual(failed, (status, dict(error=code,message=f'MOCK 테스트 오류: {code}. 새로 불러오기 후 다시 시도하세요.')))
                self.login()
                self.assertEqual(self.request('/api/chat',body)[0],200)

    def test_seed_pagination_and_reset(self):
        self.login()
        self.assertEqual(self.request('/__preview/seed', {})[0],200)
        first=self.request('/api/conversations?limit=20')[1]
        second=self.request('/api/conversations?limit=20&offset=20')[1]
        self.assertEqual((len(first['items']),len(second['items'])),(20,5))
        self.assertEqual(len(self.request('/api/me/chats?conversation_id=25&offset=20')[1]['items']),5)
        self.request('/__preview/reset', {})
        self.assertEqual(self.server.state.conversations,{})
        self.assertFalse(self.server.state.logged_in)

    def test_allowlist_and_origin(self):
        self.login()
        for path in ('/.env','/app/main.py','/static/../.env','/static/%2e%2e/.env','/scripts/preview_a_ui.py','/does-not-exist'):
            self.assertEqual(self.request(path)[0],404,path)
        for path in preview.ASSETS:
            self.assertEqual(self.request(path)[0],200,path)
        self.assertEqual(self.request('/api/me',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/__preview/reset',{}, {'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.server.server_address[0], '127.0.0.1')

    def test_invalid_requests(self):
        self.login()
        self.assertEqual(self.request('/api/conversations',{'title':[]})[0],422)
        self.assertEqual(self.request('/api/chat',{'conversation_id':[]})[0],422)
        self.assertEqual(self.request('/api/conversations?offset=x')[0],422)
        self.assertEqual(self.request('/api/conversations/999')[0],404)
        self.assertEqual(self.request('/api/chat',dict(conversation_id=999))[0],404)

    def test_fixture_provenance_shape(self):
        ref=preview.reference()
        self.assertTrue(ref['url'].startswith('https://'))
        self.assertTrue(ref['license_url'].startswith('https://'))
        self.assertTrue(ref['locator']['heading'])
        self.assertTrue(ref['source_title'])
        draft=preview.script(1)
        self.assertEqual(draft['rationale'][0]['card_ids'],[ref['card_id']])
        self.assertEqual(draft['scenes'][-1]['end_sec'],30)


if __name__ == '__main__':
    unittest.main()
