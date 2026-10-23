import assert from 'node:assert/strict';

globalThis.document = {getElementById: () => null, createTextNode: text => ({textContent: text})};
const {apiRequest, showError} = await import('../app/static/js/common.js');
let passed = 0;

globalThis.fetch = async (url, options) => {
  assert.equal(url, '/api/chat');
  assert.equal(options.credentials, 'same-origin');
  assert.equal(options.headers.get('content-type'), 'application/json');
  assert.deepEqual(JSON.parse(options.body), {message: 'example'});
  return new Response(JSON.stringify({answer: 'result'}), {status: 200});
};
assert.deepEqual(await apiRequest('/api/chat', {method: 'POST', body: {message: 'example'}}), {answer: 'result'});
passed++;

globalThis.fetch = async () => new Response(null, {status: 204});
assert.equal(await apiRequest('/api/auth/logout', {method: 'POST'}), null);
passed++;

globalThis.fetch = async () => new Response(JSON.stringify({error: 'AI_TIMEOUT', message: 'safe error'}), {status: 504});
await assert.rejects(apiRequest('/api/chat'), error => error.status === 504 && error.code === 'AI_TIMEOUT' && error.message === 'safe error');
passed++;

globalThis.fetch = async () => { throw new DOMException('private transport detail', 'AbortError'); };
await assert.rejects(apiRequest('/api/chat'), error => !error.message.includes('private') && error.message.includes('지연'));
passed++;

function element() {
  return {hidden: true, disabled: false, textContent: 'submit', replaceChildren(node) { this.textContent = node.textContent; }};
}

const errorBox = element();
showError(errorBox, '<script>untrusted</script>');
assert.equal(errorBox.textContent, '<script>untrusted</script>');
assert.equal(errorBox.hidden, false);
showError(errorBox, '');
assert.equal(errorBox.hidden, true);
passed++;

async function formCase({signup, password, confirmation, status = 200}) {
  const button = element();
  const notice = element();
  const form = {dataset: {action: signup ? 'signup' : 'login'}, reportValidity: () => true,
    addEventListener(_name, handler) { this.handler = handler; }, values: {email: 'user@example.com', password}};
  const targets = {'auth-form': form, 'auth-submit': button, 'form-error': notice, 'password-confirm': {value: confirmation}};
  document.getElementById = name => targets[name] ?? null;
  let redirected, requests = [];
  globalThis.window = {location: {replace: path => { redirected = path; }}};
  globalThis.FormData = class { constructor(source) { this.source = source; } get(name) { return this.source.values[name]; } };
  globalThis.fetch = async (url, options) => {
    requests.push({url, body: JSON.parse(options.body)});
    return new Response(JSON.stringify(status === 200 ? {id: 1, email: 'user@example.com'} : {error: 'INVALID_CREDENTIALS', message: 'safe credential error'}), {status});
  };
  await import(`../app/static/js/auth.js?case=${passed}`);
  await form.handler({preventDefault() {}});
  assert.equal(button.disabled, false);
  return {redirected, requests, notice};
}

let result = await formCase({signup: true, password: 'New-password-1234', confirmation: 'New-password-1234'});
assert.equal(result.requests[0].url, '/api/auth/signup');
assert.deepEqual(Object.keys(result.requests[0].body).sort(), ['email', 'password']);
assert.equal(result.redirected, '/login');
passed++;

result = await formCase({signup: true, password: 'New-password-1234', confirmation: 'different-password'});
assert.equal(result.requests.length, 0);
assert.equal(result.notice.hidden, false);
passed++;

result = await formCase({signup: true, password: '가'.repeat(25), confirmation: '가'.repeat(25)});
assert.equal(result.requests.length, 0);
assert.equal(result.notice.hidden, false);
passed++;

result = await formCase({signup: false, password: 'New-password-1234', status: 401});
assert.equal(result.requests[0].url, '/api/auth/login');
assert.equal(result.redirected, undefined);
assert.equal(result.notice.textContent, 'safe credential error');
passed++;

console.log(JSON.stringify({browser_client_checks: passed, result: 'passed', limitation: 'DOM stubs; not a browser visual test'}));
