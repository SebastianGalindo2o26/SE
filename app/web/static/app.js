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
