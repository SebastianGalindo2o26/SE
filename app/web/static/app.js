document.addEventListener('click', (event) => {
  const open = document.querySelector('.edit-menu[open]');
  if (open && !open.contains(event.target)) open.removeAttribute('open');
});

document.querySelectorAll('form').forEach((form) => {
  form.addEventListener('submit', () => {
    const button = form.querySelector('button[type="submit"],button:not([type])');
    if (!button || form.hasAttribute('onsubmit')) return;
    button.disabled = true;
    if (form.action.endsWith('/monitor')) button.textContent = '…';
    else if (form.action.endsWith('/apis')) button.textContent = 'Guardando…';
  });
});

document.querySelectorAll('[data-auth-fields]').forEach((fields) => {
  const select = fields.querySelector('[data-auth-type]');
  const header = fields.querySelector('[data-auth-header]');
  const username = fields.querySelector('[data-auth-username]');
  const secret = fields.querySelector('[data-auth-secret]');
  const help = fields.querySelector('[data-auth-help]');
  const secretLabel = fields.querySelector('[data-auth-secret-label]');
  const refresh = () => {
    const mode = select.value;
    header.hidden = mode !== 'api_key_header';
    username.hidden = mode !== 'basic';
    secret.hidden = mode === 'none';
    help.hidden = mode === 'none';
    secretLabel.textContent = mode === 'basic' ? 'Contraseña' : mode === 'bearer' ? 'Bearer token' : 'API key';
  };
  select.addEventListener('change', refresh);
  refresh();
});
