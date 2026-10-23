import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

// Dependency-free state/DOM-stub regression tests, not a browser visual test.
// Instrument only the import and automatic bootstrap; execute production functions.
const source = await readFile(new URL('../app/static/js/shortform.js', import.meta.url), 'utf8');
function node(textContent='') {
  return {textContent, value: '', children: [], dataset: {}, attributes: {}, hidden: false,
    append(...items) {this.children.push(...items);},
    prepend(...items) {this.children.unshift(...items);},
    replaceChildren(...items) {this.children = items;},
    setAttribute(name, value) {this.attributes[name] = value;},
    addEventListener() {}, focus() {}};
}
function harness() {
  const elements = new Map();
  const get = id => {if (!elements.has(id)) elements.set(id, node()); return elements.get(id);};
  const storage = new Map();
  const requests = [];
  let handler = () => {throw new Error('Unexpected API request');};
  const context = vm.createContext({URL, document: {getElementById: get, createElement: () => node(),
    createTextNode: text => node(text), querySelectorAll: () => []},
    localStorage: {setItem: (key, value) => storage.set(key, value)},
    apiRequest: async (...args) => {requests.push(args); return handler(...args);},
    showError: (target, text) => {target.textContent = text;},
    location: {assign: path => {context.redirected = path;}}});
  const isolated = source.slice(source.indexOf('\n') + 1, source.lastIndexOf('run(async()=>{'));
  vm.runInContext(isolated + '\nglobalThis.client = {state, selectConversation, loadHistory, send, run};', context);
  const client = context.client;
  const old = {conversation_id: 1, title: 'Old conversation', version: 4, phase: 'briefing', brief: {topic: 'Old topic'}};
  client.state.conversation = old;
  client.state.userKey = 'test-user';
  client.state.historyOffset = 40;
  storage.set('test-user', '1');
  get('conversation-title').textContent = old.title;
  get('brief').append(node('Old brief'));
  get('messages').append(node('Old message'));
  get('message').value = 'Keep my request';
  const buttons = [1, 2].map(id => {const b = node(); b.dataset.id = String(id); b.setAttribute('aria-current', String(id === 1)); return b;});
  get('conversations').append(...buttons);
  return {client, get, storage, requests, old, buttons, context, handle(fn) {handler = fn;}};
}
const next = {conversation_id: 2, title: 'New conversation', version: 5, phase: 'briefing', brief: {topic: 'New topic'}};
const page = {items: [{question: 'New question', answer: 'New answer', status: 'success'}]};
function assertOld(h) {
  assert.equal(h.client.state.conversation, h.old);
  assert.equal(h.storage.get('test-user'), '1');
  assert.equal(h.get('conversation-title').textContent, 'Old conversation');
  assert.equal(h.get('brief').children[0].textContent, 'Old brief');
  assert.equal(h.get('messages').children[0].textContent, 'Old message');
  assert.equal(h.client.state.historyOffset, 40);
  assert.equal(h.buttons[0].attributes['aria-current'], 'true');
  assert.equal(h.buttons[1].attributes['aria-current'], 'false');
}
const tests = [];
const test = (name, fn) => tests.push([name, fn]);
test('history failure preserves the entire old selection', async () => {
  const h = harness();
  const failure = new Error('History unavailable');
  h.handle(url => {if (url === '/api/conversations/2') return next; throw failure;});
  await assert.rejects(h.client.selectConversation(2), error => error === failure);
  assertOld(h);
  assert.equal(h.requests[1][0], '/api/me/chats?conversation_id=2&limit=20&offset=0');
});
test('pending history does not commit; successful history commits together', async () => {
  const h = harness();
  let finishHistory, started;
  const waiting = new Promise(resolve => {started = resolve;});
  h.handle(url => {
    if (url === '/api/conversations/2') return next;
    started(); return new Promise(resolve => {finishHistory = resolve;});
  });
  const selected = h.client.selectConversation(2);
  await waiting;
  assertOld(h);
  finishHistory(page); await selected;
  assert.equal(h.client.state.conversation, next);
  assert.equal(h.storage.get('test-user'), '2');
  assert.equal(h.get('conversation-title').textContent, next.title);
  assert.equal(h.get('messages').children.length, 2);
  assert.equal(h.get('messages').children[0].children[1].textContent, 'New question');
  assert.equal(h.client.state.historyOffset, 1);
  assert.equal(h.buttons[1].attributes['aria-current'], 'true');
});
test('detail failure leaves selection untouched', async () => {
  const h = harness(); h.handle(() => {throw new Error('Detail failed');});
  await assert.rejects(h.client.selectConversation(2), /Detail failed/); assertOld(h);
  assert.equal(h.requests.length, 1);
});
test('dual failure preserves original request error identity, status, code and input', async () => {
  const h = harness();
  const original = Object.assign(new Error('AI request timed out'), {status: 504, code: 'AI_TIMEOUT'});
  h.handle(url => {if (url === '/api/chat') throw original; throw new Error('Refresh failed');});
  await assert.rejects(h.client.send('message'), error => error === original && error.status === 504 && error.code === 'AI_TIMEOUT');
  assert.equal(h.get('message').value, 'Keep my request'); assertOld(h);
});
test('failed request with successful recovery still reports original and retains input', async () => {
  const h = harness(); const original = new Error('Request failed');
  h.handle(url => {if (url === '/api/chat') throw original; if (url === '/api/conversations/1') return {...h.old, version: 5}; return page;});
  await assert.rejects(h.client.send('message'), error => error === original);
  assert.equal(h.client.state.conversation.version, 5);
  assert.equal(h.get('message').value, 'Keep my request');
});
test('successful request with history failure says request completed, without asking to resend', async () => {
  const h = harness();
  h.handle(url => {if (url === '/api/chat') return {}; if (url === '/api/conversations/1') return {...h.old, version: 5}; throw new Error('History failed');});
  await assert.rejects(h.client.send('message'), error => error.code === 'REFRESH_FAILED' && error.message.includes('요청은 완료') && error.message.includes('다시 보내지 말고'));
  assert.equal(h.get('message').value, ''); assertOld(h);
});
test('successful request with list failure is also a refresh failure', async () => {
  const h = harness();
  h.handle(url => {if (url === '/api/chat') return {}; if (url === '/api/conversations/1') return h.old; if (url.startsWith('/api/me/chats')) return page; throw new Error('List failed');});
  await assert.rejects(h.client.send('message'), error => error.code === 'REFRESH_FAILED' && error.message.includes('List failed'));
});
test('original 401 survives dual failure and redirects through run', async () => {
  const h = harness();
  h.handle(url => {if (url === '/api/chat') throw Object.assign(new Error('Login required'), {status: 401}); throw new Error('Recovery failed');});
  await h.client.run(() => h.client.send('message'));
  assert.equal(h.context.redirected, '/login'); assert.equal(h.client.state.busy, false);
});
test('refresh 401 after successful request retains authentication handling', async () => {
  const h = harness();
  h.handle(url => {if (url === '/api/chat') return {}; throw Object.assign(new Error('Login required'), {status: 401});});
  await h.client.run(() => h.client.send('message'));
  assert.equal(h.context.redirected, '/login');
});
test('older history still prepends and advances offset', async () => {
  const h = harness(); h.handle(() => page);
  await h.client.loadHistory(true);
  assert.equal(h.requests[0][0], '/api/me/chats?conversation_id=1&limit=20&offset=40');
  assert.equal(h.client.state.historyOffset, 41);
  assert.equal(h.get('messages').children.length, 3);
});
let failed = 0;
for (const [name, fn] of tests) {
  try {await fn(); console.log(`PASS: ${name}`);} catch (error) {failed++; console.error(`FAIL: ${name}\n${error.stack}`);}
}
console.log(JSON.stringify({workspace_client_checks: tests.length, failed, result: failed ? 'failed' : 'passed', limitation: 'DOM stubs; not a browser visual test'}));
if (failed) process.exitCode = 1;
