import {apiRequest, showError} from './common.js';

const accountForm = document.getElementById('auth-form');
const submit = document.getElementById('auth-submit');
const notice = document.getElementById('form-error');

accountForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (submit.disabled || !accountForm.reportValidity()) return;
  showError(notice, '');
  const signup = accountForm.dataset.action === 'signup';
  const values = new FormData(accountForm);
  const password = String(values.get('password') || '');
  if (signup && password !== document.getElementById('password-confirm').value) {
    showError(notice, '입력한 두 비밀번호가 다릅니다.');
    return;
  }
  if (new TextEncoder().encode(password).byteLength > 72) {
    showError(notice, '비밀번호는 UTF-8 기준 72바이트 이내로 입력해 주세요.');
    return;
  }
  submit.disabled = true;
  const originalLabel = submit.textContent;
  submit.textContent = signup ? '가입 정보를 저장하고 있어요…' : '로그인하고 있어요…';
  try {
    await apiRequest(signup ? '/api/auth/signup' : '/api/auth/login', {
      method: 'POST', timeoutMs: 15000,
      body: {email: String(values.get('email') || ''), password},
    });
    window.location.replace(signup ? '/login' : '/');
  } catch (failure) {
    showError(notice, failure.message);
  } finally {
    submit.disabled = false;
    submit.textContent = originalLabel;
  }
});
