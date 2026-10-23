export class RequestFailure extends Error {
  constructor(message, status = 0, code = '') {
    super(message);
    this.name = 'RequestFailure';
    this.status = status;
    this.code = code;
  }
}

export async function apiRequest(path, options = {}) {
  const {method = 'GET', body, timeoutMs = 65000} = options;
  const cancellation = new AbortController();
  const deadline = setTimeout(() => cancellation.abort(), timeoutMs);
  try {
    const headers = new Headers({Accept: 'application/json'});
    if (body !== undefined) headers.set('Content-Type', 'application/json');
    const reply = await fetch(path, {method, headers, credentials: 'same-origin',
      signal: cancellation.signal, body: body === undefined ? undefined : JSON.stringify(body)});
    if (reply.status === 204) return null;
    const result = await reply.json().catch(() => null);
    if (!reply.ok) {
      throw new RequestFailure(result?.message || '요청을 완료하지 못했습니다.', reply.status, result?.error || '');
    }
    if (result === null) throw new RequestFailure('서버 응답 형식을 확인하지 못했습니다.', reply.status);
    return result;
  } catch (failure) {
    if (failure.name === 'AbortError') throw new RequestFailure('응답이 지연되고 있습니다. 대화 기록에서 저장 여부를 확인해 주세요.');
    if (failure instanceof TypeError) throw new RequestFailure('서버에 연결하지 못했습니다. 연결 상태를 확인해 주세요.');
    throw failure;
  } finally {
    clearTimeout(deadline);
  }
}

export function showError(target, message) {
  if (!target) return;
  target.replaceChildren(document.createTextNode(message || ''));
  target.hidden = !message;
}

const logout = document.getElementById('logout-button');
logout?.addEventListener('click', async () => {
  logout.disabled = true;
  try {
    await apiRequest('/api/auth/logout', {method: 'POST'});
    window.location.replace('/login');
  } catch (failure) {
    showError(document.getElementById('global-error'), failure.message);
    logout.disabled = false;
  }
});
