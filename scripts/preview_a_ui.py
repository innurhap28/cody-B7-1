"""LOCAL MOCK ONLY. No account, AI, DB, production imports, or outbound requests."""
import argparse
import copy
import hashlib
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import RLock
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {f'/static/{p}': ROOT / 'app/static' / p for p in (
    'css/shortform.css', 'js/auth.js', 'js/common.js', 'js/shortform.js')}
ASSETS['/__preview.js'] = ROOT / 'scripts/preview_a_ui.js'
ERRORS = {'conflict': (409, 'VERSION_CONFLICT'), 'busy': (409, 'CONVERSATION_BUSY'),
          'timeout': (504, 'AI_TIMEOUT'), 'invalid': (502, 'AI_INVALID_RESPONSE'),
          'unavailable': (503, 'AI_UNAVAILABLE'), 'unauthorized': (401, 'UNAUTHORIZED')}
BANNER = '''<aside id="mock-banner" style="background:#fff0bb;color:#241a00;padding:12px;border:3px solid #986500;position:relative;z-index:9">
<strong>MOCK / A UI 전용 테스트 · 실제 인증/AI/DB 없음</strong><br>
실제 개인정보·비밀번호 금지. 입력은 가짜 계정으로 고정됩니다. 대화는 메모리에만 보관되며 종료 시 사라집니다.
<label>다음 채팅 요청 <select id="mock-scenario"><option value="normal">정상</option>
<option value="conflict">409 버전 충돌</option><option value="busy">409 처리 중</option>
<option value="timeout">504 AI timeout (즉시 응답)</option><option value="invalid">502 잘못된 AI 응답</option>
<option value="unavailable">503 AI 사용 불가</option><option value="unauthorized">401 로그인 이동</option></select></label>
<button id="mock-seed" type="button">페이지네이션용 25개 대화/기록</button>
<button id="mock-reset" type="button">모두 초기화</button><span id="mock-notice" role="status"></span>
</aside>'''


def reference():
    data = ROOT / 'app/data/shortform'
    raw = (data / 'cards.jsonl').read_bytes()
    sources_raw = (data / 'sources.json').read_bytes()
    card = json.loads(raw.decode('utf-8').splitlines()[0])
    source = next(s for s in json.loads(sources_raw) if s['source_id'] == card['source_id'])
    return dict(card_id=card['card_id'], source_id=source['source_id'], source_title=source['title'],
                author=source['author'], url=card['url'], locator=card['locator'],
                pdf_url=source.get('pdf_url'), pdf_page_start=card['locator'].get('pdf_page_start'),
                pdf_page_end=card['locator'].get('pdf_page_end'), concept=card['concept'],
                license=source['license'], license_url=source['license_url'], changes=card['changes'],
                knowledge_version='kb-' + hashlib.sha256(sources_raw+b'\n'+raw).hexdigest()[:16],
                limitations=card['limitations'], application_notes=card['application_notes'],
                research_topic_ids=card.get('research_topic_ids', []))


def brief(ready=False):
    return dict(schema_version='brief.v1', topic='MOCK 쉬운 아침 메뉴' if ready else None,
                goal='정보 전달' if ready else None,
                audience=dict(segment='자취생' if ready else None, age_range='20대' if ready else None, prior_knowledge=None),
                duration_sec=30 if ready else None, presentation_mode='hands_only' if ready else None,
                characters=[], direction_style='차분한 시연' if ready else None, tone='친근함' if ready else None,
                core_message='간단한 아침을 준비해 보세요' if ready else None,
                constraints=[], proposed_defaults=[], confirmed=False)


def script(revision):
    return dict(script_id=revision, revision=revision, title='MOCK 30초 아침 메뉴', duration_sec=30,
                structure=dict(name='도입–시연–정리', reason='UI 출력 확인을 위한 고정 예시입니다.'),
                scenes=[dict(scene_no=i+1, start_sec=i*10, end_sec=(i+1)*10,
                             purpose=['도입', '시연', '정리'][i], visual='테이블 위 재료와 손을 촬영합니다.',
                             dialogue='간단한 아침을 함께 준비해요.' if revision == 1 else '수정된 MOCK 대사입니다.',
                             caption='MOCK 테스트 자막', direction='고정 카메라로 촬영합니다.') for i in range(3)],
                rationale=[dict(scene_nos=[1,2,3], card_ids=[reference()['card_id']],
                                explanation='시청자의 정보 탐색 목적을 고려한 예시이며 실제 AI 분석이 아닙니다.')],
                change_summary='MOCK 대사를 변경했습니다.' if revision > 1 else None)


class State:
    def __init__(self):
        self.reset()

    def reset(self):
        self.logged_in = False
        self.conversations = {}
        self.turns = {}
        self.scenario = 'normal'

    def create(self, title='새 릴스 기획'):
        cid = len(self.conversations) + 1
        item = dict(conversation_id=cid, title=title, version=0, phase='briefing',
                    processing=False, brief=brief(), latest_script=None)
        self.conversations[cid] = item
        self.turns[cid] = []
        return item

    def chat(self, body):
        cid = body.get('conversation_id')
        item = self.conversations.get(cid)
        if item is None:
            return 404, dict(error='NOT_FOUND', message='MOCK 대화를 찾을 수 없습니다.')
        if self.scenario != 'normal':
            scenario, self.scenario = self.scenario, 'normal'
            status, code = ERRORS[scenario]
            if scenario == 'unauthorized':
                self.logged_in = False
            return status, dict(error=code, message=f'MOCK 테스트 오류: {code}. 새로 불러오기 후 다시 시도하세요.')
        if body.get('expected_version') != item['version']:
            return 409, dict(error='VERSION_CONFLICT', message='MOCK 버전 충돌: 새로 불러오세요.')
        action = body.get('action')
        message = body.get('message')
        if action not in ('message', 'generate', 'revise') or not isinstance(message, str) or not 1 <= len(message.strip()) <= 6000:
            return 422, dict(error='VALIDATION_ERROR', message='메시지/동작을 확인하세요.')
        if action == 'generate' and item['phase'] != 'ready':
            return 409, dict(error='BRIEF_NOT_READY', message='먼저 두 번 메시지를 보내 MOCK 조건을 정리하세요.')
        if action == 'revise' and (not item['latest_script'] or body.get('base_script_id') != item['latest_script']['script_id']):
            return 409, dict(error='SCRIPT_CONFLICT', message='수정할 MOCK 대본을 확인하세요.')
        if action == 'message':
            ready = item['version'] >= 1
            item['brief'] = brief(ready)
            item['phase'] = 'ready' if ready else 'briefing'
            item['latest_script'] = None
            answer = 'MOCK 제작 조건이 준비됐어요. 대본 작성 버튼을 눌러 주세요.' if ready else 'MOCK 질문: 시청자와 영상 길이를 정해 주세요. 한 번 더 보내면 준비됩니다.'
            result = dict(reply_type='brief_summary' if ready else 'question', script=None, references=[],
                          missing_fields=[] if ready else ['audience.segment', 'duration_sec'],
                          follow_up_questions=[] if ready else [dict(field='audience.segment', question='누가 볼 영상인가요?', suggestions=['20대 자취생, 30초', '초보 요리사, 30초'])])
        else:
            revision = (item['latest_script']['revision']+1) if action == 'revise' else 1
            item['latest_script'] = script(revision)
            item['phase'] = 'drafted'
            item['brief']['confirmed'] = True
            answer = 'MOCK 대본입니다. 실제 AI 생성 결과가 아닙니다.'
            result = dict(reply_type='revision' if action == 'revise' else 'script',
                          script=copy.deepcopy(item['latest_script']), references=[reference()], missing_fields=[], follow_up_questions=[])
        item['version'] += 1
        result.update(phase=item['phase'], answer=answer, brief=copy.deepcopy(item['brief']))
        self.turns[cid].insert(0, dict(id=len(self.turns[cid])+1, conversation_id=cid, question=message,
                                     answer=answer, status='success', error_code=None, response=result))
        return 200, result


def render(action=None):
    name = 'auth' if action else 'workspace'
    html = (ROOT / f'app/templates/shortform/{name}.html').read_text(encoding='utf-8')
    if action:
        html = re.sub(r'{% if action == \'signup\' %}(.*?){% endif %}', lambda m: m[1] if action == 'signup' else '', html, flags=re.S)
        html = re.sub(r"{{ '([^']*)' if action == 'signup' else '([^']*)' }}", lambda m: m[1] if action == 'signup' else m[2], html)
        html = html.replace('{{ action }}', action)
        # Fixed inert test values: no editable identity/password fields, including before JS loads.
        html = html.replace('id="email"', 'value="preview@example.invalid" readonly id="email"')
        html = html.replace('type="password"', 'type="text" value="MOCK-ONLY-123" readonly')
        html = re.sub(r'autocomplete="[^"]+"', 'autocomplete="off"', html)
    html = html.replace('{{ email }}', 'MOCK preview@example.invalid')
    html = re.sub(r'(<body[^>]*>)', r'\1'+BANNER, html, count=1)
    return html.replace('</body>', '<script src="/__preview.js"></script></body>')


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)  # Bound idle/preconnect and incomplete-request lifetime.

    def handle(self):
        try:
            super().handle()
        except (ConnectionError, TimeoutError):
            # Browser navigation/refresh can abandon a speculative connection.
            self.close_connection = True

    def log_message(self, *_args):
        pass  # Do not log URLs, credentials, or conversation content.

    def reply(self, status, data, content_type='application/json; charset=utf-8'):
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8') if content_type.startswith('application/json') else data
        self.send_response(status)
        for key, value in {'Content-Type': content_type, 'Content-Length': str(len(payload)), 'Cache-Control': 'no-store',
                           'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                           'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"}.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def allowed(self):
        expected = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != expected:
            self.reply(403, dict(error='LOCAL_ONLY', message='Use the printed 127.0.0.1 URL.'))
            return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + expected:
            self.reply(403, dict(error='LOCAL_ONLY', message='Cross-origin requests are blocked.'))
            return False
        return True

    def do_GET(self):
        # Headers have already been read; idle preconnections never hold this lock.
        with self.server.state_lock:
            self.handle_get()

    def handle_get(self):
        if not self.allowed(): return
        parsed = urlsplit(self.path)
        path, query, state = parsed.path, parse_qs(parsed.query), self.server.state
        if path in ASSETS:
            mime = 'text/css' if path.endswith('.css') else 'text/javascript'
            return self.reply(200, ASSETS[path].read_bytes(), mime+'; charset=utf-8')
        if path in ('/', '/login', '/signup'):
            action = path[1:] if path != '/' else (None if state.logged_in else 'login')
            return self.reply(200, render(action).encode('utf-8'), 'text/html; charset=utf-8')
        if path.startswith('/api/') and not state.logged_in:
            return self.reply(401, dict(error='UNAUTHORIZED', message='MOCK 로그인을 해 주세요.'))
        if path == '/api/me': return self.reply(200, dict(id=987654321, email='preview@example.invalid'))
        if path == '/api/conversations' or path == '/api/me/chats':
            try:
                limit = max(1, min(50, int(query.get('limit', ['20'])[0])))
                offset = max(0, int(query.get('offset', ['0'])[0]))
                items = list(reversed(list(state.conversations.values()))) if path == '/api/conversations' else state.turns.get(int(query.get('conversation_id', ['0'])[0]), [])
            except ValueError:
                return self.reply(422, dict(error='VALIDATION_ERROR', message='Invalid pagination.'))
            return self.reply(200, dict(items=items[offset:offset+limit], total=len(items), limit=limit, offset=offset))
        match = re.fullmatch(r'/api/conversations/(\d+)', path)
        if match and int(match[1]) in state.conversations:
            return self.reply(200, state.conversations[int(match[1])])
        self.reply(404, dict(error='NOT_FOUND', message='No such MOCK route.'))

    def do_POST(self):
        if not self.allowed(): return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 32768: raise ValueError()
            body = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(body, dict): raise ValueError()
        except (ValueError, UnicodeDecodeError):
            return self.reply(422, dict(error='VALIDATION_ERROR', message='Invalid JSON body.'))
        # Read the request body before locking shared mock state.
        with self.server.state_lock:
            self.handle_post(body)

    def handle_post(self, body):
        path, state = urlsplit(self.path).path, self.server.state
        if path in ('/api/auth/login', '/api/auth/signup'):
            # Refuse any real credentials; do not retain credentials or request bodies.
            if body != dict(email='preview@example.invalid', password='MOCK-ONLY-123'):
                return self.reply(422, dict(error='MOCK_ONLY', message='고정 MOCK 값만 허용합니다. 실제 계정 정보는 입력하지 마세요.'))
            if path.endswith('login'): state.logged_in = True
            return self.reply(200, dict(mock=True))
        if path == '/api/auth/logout':
            state.logged_in = False
            return self.reply(204, b'', 'text/plain')
        if path == '/__preview/reset':
            state.reset()
            return self.reply(200, dict(mock=True))
        if not state.logged_in:
            return self.reply(401, dict(error='UNAUTHORIZED', message='MOCK 로그인을 해 주세요.'))
        if path == '/__preview/scenario' and body.get('scenario') in ('normal', *ERRORS):
            state.scenario = body['scenario']
            return self.reply(200, dict(mock=True))
        if path == '/__preview/seed':
            for i in range(25):
                item = state.create(f'MOCK 페이지네이션 {i+1:02d}')
                for j in range(25):
                    state.chat(dict(conversation_id=item['conversation_id'], expected_version=item['version'], action='message', message=f'MOCK 기록 {j+1:02d}'))
            return self.reply(200, dict(mock=True))
        if path == '/api/conversations':
            title = body.get('title', '새 릴스 기획')
            if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
                return self.reply(422, dict(error='VALIDATION_ERROR', message='Invalid title.'))
            return self.reply(201, state.create(title.strip()))
        if path == '/api/chat':
            if type(body.get('conversation_id')) is not int:
                return self.reply(422, dict(error='VALIDATION_ERROR', message='Invalid conversation id.'))
            status, result = state.chat(body)
            return self.reply(status, result)
        self.reply(404, dict(error='NOT_FOUND', message='No such MOCK route.'))


def make_server(port=8765):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.state_lock = RLock()
    server.state = State()
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    for path in [*ASSETS.values(), ROOT/'app/templates/shortform/auth.html', ROOT/'app/templates/shortform/workspace.html']:
        if not path.is_file(): parser.error(f'Missing required preview source: {path.name}')
    reference()
    try:
        server = make_server(args.port)
    except OSError as error:
        parser.exit(1, f'Cannot bind local preview port: {error}. Try --port 8766.\n')
    print(f'MOCK ONLY: http://127.0.0.1:{server.server_port}/login\nNo real auth, AI or DB. Ctrl+C to stop.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
