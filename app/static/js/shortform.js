import {apiRequest, showError} from './common.js';

const $ = (id) => document.getElementById(id);
const state = {conversation: null, busy: false, historyOffset: 0, listOffset: 0, userKey: ''};
const labels = {'topic':'주제','goal':'목적','audience':'시청자','duration_sec':'길이','presentation_mode':'등장 방식','characters':'등장인물','direction_style':'연출','tone':'말투','core_message':'핵심 메시지','constraints':'제작 제약','proposed_defaults':'미확정 제안'};
const modes = {on_camera:'직접 출연',hands_only:'손만 출연',voiceover:'내레이션',mixed:'혼합',no_people:'인물 없음'};
const phases = {briefing:'제작 조건 정리 중',ready:'기획 확인 후 대본 작성',drafted:'대본 작성 완료'};
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function lock(busy) {
  state.busy = busy;
  for (const node of document.querySelectorAll('main button, #message')) node.disabled = busy;
  $('send').disabled = busy || !state.conversation || state.conversation.processing;
  $('status').textContent = busy ? '기획을 정리하고 있어요. 잠시만 기다려 주세요…' : '';
}
function renderBrief(conversation) {
  $('conversation-title').textContent = conversation.title;
  $('phase').textContent = conversation.processing ? '이전 요청 처리 중 · 잠시 후 새로 불러오세요' : phases[conversation.phase];
  $('brief').replaceChildren();
  const brief = conversation.brief || {};
  for (const [key,label] of Object.entries(labels)) {
    let value = brief[key];
    if (key === 'audience') value = [value?.segment,value?.age_range,value?.prior_knowledge].filter(Boolean).join(' / ');
    else if (key === 'presentation_mode') value = modes[value];
    else if (key === 'duration_sec' && value) value = `${value}초`;
    else if (Array.isArray(value)) value = value.join(', ') || '별도 설정 없음';
    $('brief').append(element('dt',label),element('dd',value || '함께 정할 예정'));
  }
  $('generate').hidden = conversation.phase !== 'ready' || conversation.processing;
  $('revise').hidden = conversation.phase !== 'drafted' || !conversation.latest_script || conversation.processing;
  $('refresh-conversation').hidden = false;
}
function sourceLink(url, text) {
  const a = element('a',text);
  try {const parsed = new URL(url); if (parsed.protocol === 'https:') {a.href = parsed.href; a.target='_blank'; a.rel='noopener noreferrer';}} catch {}
  return a;
}
function renderScript(script, references) {
  const block = element('section');
  block.append(element('h2',`${script.title}${script.revision ? ` · 버전 ${script.revision}` : ''}`));
  block.append(element('p',`${script.structure.name} — ${script.structure.reason}`,'text'));
  for (const scene of script.scenes) {
    const part = element('section',undefined,'script-scene');
    part.append(element('h3',`${scene.scene_no}. ${scene.start_sec}–${scene.end_sec}초 · ${scene.purpose}`));
    for (const [name,key] of [['화면','visual'],['대사·내레이션','dialogue'],['자막','caption'],['연출','direction']]) {
      if (scene[key]) part.append(element('p',`${name}: ${scene[key]}`));
    }
    block.append(part);
  }
  if (script.change_summary) block.append(element('p',`수정 내용: ${script.change_summary}`,'text'));
  block.append(element('h3','원리와 장면의 연결'));
  for (const item of script.rationale) block.append(element('p',`장면 ${item.scene_nos.join(', ')}: ${item.explanation} [${item.card_ids.join(', ')}]`,'text'));
  if (references?.length) block.append(renderReferences(references));
  return block;
}
function renderReferences(references) {
    const refs = element('div',undefined,'references');
    refs.append(element('h3','참고한 자료'));
    const list = element('ul');
    for (const ref of references) {
      const li = element('li');
      const pages = ref.pdf_page_start ? ` · PDF ${ref.pdf_page_start}${ref.pdf_page_end !== ref.pdf_page_start ? '–'+ref.pdf_page_end : ''}쪽` : '';
      li.append(sourceLink(ref.url,ref.source_title),document.createTextNode(` · ${ref.author} · ${ref.locator.heading}${pages} · ${ref.card_id} · `),
        sourceLink(ref.license_url,ref.license),element('p',ref.changes));
      if (ref.pdf_url && ref.pdf_url !== ref.url) li.append(sourceLink(ref.pdf_url,'공개 PDF'));
      if (ref.limitations?.length) li.append(element('p',`적용 범위: ${ref.limitations.join(' ')}`));
      list.append(li);
    }
    refs.append(list); return refs;
}
function bubble(role, text, payload) {
  const box = element('article',undefined,`bubble ${role}`);
  box.append(element('h3',role === 'user' ? '나의 아이디어' : '대본 코치'),element('p',text,'text'));
  if (payload?.script) box.append(renderScript(payload.script,payload.references));
  else if (payload?.references?.length) box.append(renderReferences(payload.references));
  if (payload?.follow_up_questions?.length) {
    const choices = element('div',undefined,'choices');
    for (const question of payload.follow_up_questions) for (const choice of question.suggestions) {
      const button = element('button',choice); button.type='button';
      button.addEventListener('click',()=>{$('message').value=choice;$('message').focus();}); choices.append(button);
    }
    box.append(choices);
  }
  return box;
}
function turnNodes(turn) {
  const nodes = [bubble('user',turn.question)];
  if (turn.status === 'success') nodes.push(bubble('assistant',turn.answer,turn.response));
  else nodes.push(bubble('assistant',turn.status === 'processing' ? '이 요청은 아직 처리 중입니다. 새로 불러오기로 확인해 주세요.' : `이 요청은 완료되지 않았습니다. (${turn.error_code || turn.status})`));
  return nodes;
}
async function loadHistory(older=false) {
  const page = await apiRequest(`/api/me/chats?conversation_id=${state.conversation.conversation_id}&limit=20&offset=${older ? state.historyOffset : 0}`);
  const nodes = [...page.items].reverse().flatMap(turnNodes);
  if (older) $('messages').prepend(...nodes); else $('messages').replaceChildren(...nodes);
  state.historyOffset = (older ? state.historyOffset : 0) + page.items.length;
  $('more-history').hidden = page.items.length < 20;
}
async function selectConversation(id) {
  const conversation = await apiRequest(`/api/conversations/${id}`);
  state.conversation = conversation;
  localStorage.setItem(state.userKey,String(id));
  renderBrief(conversation);
  await loadHistory();
  for (const node of $('conversations').children) node.setAttribute('aria-current',String(Number(node.dataset.id) === id));
}
async function loadList(more=false) {
  const page = await apiRequest(`/api/conversations?limit=20&offset=${more ? state.listOffset : 0}`);
  if (!more) $('conversations').replaceChildren();
  for (const item of page.items) {
    const button = element('button',item.title); button.type='button'; button.dataset.id=item.conversation_id;
    button.setAttribute('aria-current',String(state.conversation?.conversation_id === item.conversation_id));
    button.addEventListener('click',()=>run(()=>selectConversation(item.conversation_id))); $('conversations').append(button);
  }
  state.listOffset = (more ? state.listOffset : 0) + page.items.length;
  $('more-conversations').hidden = page.items.length < 20;
  return page.items;
}
async function run(task) {
  if (state.busy) return;
  showError($('workspace-error'),''); lock(true);
  try {await task();}
  catch (error) {
    if (error.status === 401) {location.assign('/login');return;}
    showError($('workspace-error'),error.message);
  } finally {lock(false);}
}
async function send(action) {
  if (!state.conversation) throw new Error('새 릴스 기획을 먼저 시작해 주세요.');
  const message = action === 'generate' ? '확인한 제작 조건으로 대본을 작성해 주세요.' : $('message').value.trim();
  if (!message) throw new Error('아이디어나 수정 요청을 입력해 주세요.');
  const body = {conversation_id:state.conversation.conversation_id,expected_version:state.conversation.version,action,message};
  if (action === 'revise') body.base_script_id = state.conversation.latest_script.script_id;
  try {
    await apiRequest('/api/chat',{method:'POST',body,timeoutMs:135000});
    if (action !== 'generate') $('message').value='';
  } finally {
    // Recover the server's version even if the browser timed out or another tab won.
    await selectConversation(body.conversation_id);
  }
  await loadList();
}
$('chat-form').addEventListener('submit',(event)=>{event.preventDefault();run(()=>send('message'));});
$('generate').addEventListener('click',()=>run(()=>send('generate')));
$('revise').addEventListener('click',()=>run(()=>send('revise')));
$('new-conversation').addEventListener('click',()=>run(async()=>{
  const item = await apiRequest('/api/conversations',{method:'POST',body:{title:'새 릴스 기획'}});
  await selectConversation(item.conversation_id); await loadList(); $('message').focus();
}));
$('more-history').addEventListener('click',()=>run(()=>loadHistory(true)));
$('more-conversations').addEventListener('click',()=>run(()=>loadList(true)));
$('refresh-conversation').addEventListener('click',()=>run(()=>selectConversation(state.conversation.conversation_id)));
run(async()=>{
  const user = await apiRequest('/api/me'); state.userKey=`shortform-conversation-${user.id}`;
  const list = await loadList(); const saved=Number(localStorage.getItem(state.userKey));
  if (saved) {
    try {await selectConversation(saved);return;} catch (error) {if(error.status!==404) throw error;}
  }
  if (list.length) await selectConversation(list[0].conversation_id);
});
