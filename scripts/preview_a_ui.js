// Preview-only controls. Production JavaScript files remain untouched.
const request = async (path, body = {}) => {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  if (!response.ok) throw new Error('MOCK 로그인을 먼저 해 주세요.');
};
const notice = document.getElementById('mock-notice');
const protect = (action) => async () => {
  try {await action();} catch(error) {notice.textContent = error.message;}
};
document.getElementById('mock-scenario').addEventListener('change', protect(async () => {
  await request('/__preview/scenario', {scenario:document.getElementById('mock-scenario').value});
  notice.textContent='다음 채팅 요청에 한 번 적용합니다.';
}));
document.getElementById('mock-reset').addEventListener('click', protect(async () => {
  await request('/__preview/reset');
  localStorage.removeItem('shortform-conversation-987654321');
  location.assign('/login');
}));
document.getElementById('mock-seed').addEventListener('click', protect(async () => {
  await request('/__preview/scenario', {scenario:'normal'});
  await request('/__preview/seed');
  localStorage.removeItem('shortform-conversation-987654321');
  location.assign('/');
}));
// Keep provenance visible; intercept ordinary link clicks (not browser context menus).
// The preview makes no automatic outbound calls. Do not open sources in new tabs during offline testing.
document.addEventListener('click', (event) => {
  const link=event.target.closest('a[href]');
  if (link && new URL(link.href, location.href).origin !== location.origin) {
    event.preventDefault();
    notice.textContent='MOCK에서는 외부 출처 링크를 열지 않습니다. 실제 링크는 B 통합 후 별도 확인하세요.';
  }
});
