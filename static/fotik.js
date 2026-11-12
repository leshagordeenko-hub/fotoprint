/* ИИ-ассистент «Фотик». Подключается после app.js и использует его помощники: $, esc, api, st, I, ROUTES, route, ss.
   Ключ Claude API на фронтенде не нужен и сюда не попадает: браузер обращается только к /api/fotik. */
'use strict';
(() => {
  const QUICK = ['Что изменилось за неделю?', 'Есть ли аномалии?', 'Прогноз на месяц'];
  const KEY = () => 'fp:fotik:' + (st.user?.login || '');
  const MAX_KEEP = 30;
  const sendIco = ic('<path d="M5 12h14M13 6l6 6-6 6"/>');
  const clearIco = ic('<path d="M3 6h18M8 6V4h8v2M6 6l1 14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-14"/>');
  let msgs = [], busy = false, failed = null;

  /* ---------- разметка */
  const fab = document.createElement('button');
  fab.className = 'fotik-fab'; fab.type = 'button'; fab.hidden = true;
  fab.setAttribute('aria-label', 'Открыть ИИ-ассистента Фотик'); fab.setAttribute('aria-expanded', 'false'); fab.setAttribute('aria-controls', 'fotik');
  fab.innerHTML = '<span class="fotik-face" aria-hidden="true"><img src="fotik-face.jpg" alt=""><i class="fotik-wink"></i></span><span class="fotik-tag" aria-hidden="true">Спросить Фотика</span>';

  const box = document.createElement('section');
  box.className = 'fotik'; box.id = 'fotik'; box.hidden = true;
  box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', 'ИИ-ассистент Фотик');
  box.innerHTML = `
    <header class="fotik-head">
      <img src="fotik-face.jpg" alt="">
      <div class="fwho"><b>Фотик</b><small id="fotik-ctx">Аналитик дашборда</small></div>
      <button type="button" data-f="clear" aria-label="Очистить переписку" title="Очистить переписку">${clearIco}</button>
      <button type="button" data-f="close" aria-label="Закрыть Фотика" title="Закрыть · Esc">${I.x}</button>
    </header>
    <div class="fotik-log" id="fotik-log" aria-live="polite"></div>
    <div class="fotik-quick" role="group" aria-label="Быстрые вопросы">${QUICK.map(q => `<button type="button" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div>
    <form class="fotik-form" novalidate>
      <label class="sr" for="fotik-in">Вопрос Фотику</label>
      <textarea id="fotik-in" rows="1" maxlength="2000" placeholder="Спросите про показатели…"></textarea>
      <button class="send" type="submit" aria-label="Отправить">${sendIco}</button>
    </form>`;
  document.body.append(fab, box);
  const log = $('#fotik-log', box), inp = $('#fotik-in', box), form = $('form', box);

  /* ---------- вывод сообщений: экранируем, затем жирный, списки, абзацы */
  function md(text) {
    const lines = esc(text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
      .replace(/(\d) (?=\d{3}\b)/g, '$1\u00a0').replace(/(\d) (?=%|BYN|п\.п\.|дн\.|изд|заказ)/g, '$1\u00a0').split('\n');
    let html = '', list = false;
    for (const raw of lines) {
      const l = raw.trim(), m = l.match(/^(?:[-•*]|\d+[.)])\s+(.*)$/);
      if (m) { if (!list) { html += '<ul>'; list = true; } html += `<li>${m[1]}</li>`; continue; }
      if (list) { html += '</ul>'; list = false; }
      if (l) html += `<p>${l.replace(/^#{1,4}\s*/, '')}</p>`;
    }
    return html + (list ? '</ul>' : '');
  }
  const ctxLine = c => c ? `${c.period} · ${c.product}${c.department !== 'Все подразделения' ? ' · ' + c.department : ''}` : '';
  function draw() {
    if (!msgs.length && !busy && !failed) {
      log.innerHTML = `<div class="fotik-hello"><img src="fotik.jpg" alt="Фотик — робот с фотокнигой"><h3>Привет, я Фотик!</h3>
        <p>Разберу показатели дашборда: что изменилось, где аномалии и чего ждать дальше. Спросите своими словами или выберите вопрос ниже.</p></div>`;
    } else {
      log.innerHTML = msgs.map(m => m.role === 'user'
        ? `<div class="fm u">${esc(m.content)}</div>`
        : `<div class="fm a"><img src="fotik-face.jpg" alt=""><div class="fbub">${md(m.content)}${m.ctx ? `<span class="fmeta">По данным: ${esc(ctxLine(m.ctx))}</span>` : ''}</div></div>`).join('')
        + (failed ? `<div class="fm a ferr"><img src="fotik-face.jpg" alt=""><div class="fbub" role="alert">${esc(failed.error)}<br><button type="button" data-f="retry">Повторить вопрос</button></div></div>` : '')
        + (busy ? `<div class="fotik-think" role="status"><img src="fotik-face.jpg" alt="">Фотик думает<i aria-hidden="true"><span></span><span></span><span></span></i></div>` : '');
    }
    log.scrollTop = log.scrollHeight;
    $$('.fotik-quick button', box).forEach(b => b.disabled = busy);
    $('.send', box).disabled = busy;
  }
  function updateCtx() {
    if (!st.meta || !st.F) return;
    const p = st.meta.periods.find(x => x.key === st.F.period)?.label || '';
    const pr = st.F.product === 'all' ? 'Все продукты' : (st.meta.products?.find(x => x.id === st.F.product)?.name || '');
    const dp = st.F.dept === 'all' ? '' : (st.meta.departments?.find(x => x.id === st.F.dept)?.name || '');
    $('#fotik-ctx').textContent = 'Видит: ' + [p.replace(' (текущий)', ''), pr, dp].filter(Boolean).join(' · ');
  }
  const save = () => ss.set(KEY(), msgs.slice(-MAX_KEEP));

  /* ---------- открытие / закрытие */
  let lastFocus = null;
  function open() {
    lastFocus = document.activeElement; updateCtx();
    box.hidden = false; fab.setAttribute('aria-expanded', 'true'); draw();
    setTimeout(() => inp.focus(), 30);
  }
  function close() {
    box.hidden = true; fab.setAttribute('aria-expanded', 'false');
    (lastFocus && document.contains(lastFocus) ? lastFocus : fab).focus();
  }

  /* ---------- отправка */
  async function ask(q) {
    q = String(q || '').trim();
    if (!q || busy) return;
    const history = msgs.map(({ role, content }) => ({ role, content }));
    msgs.push({ role: 'user', content: q }); failed = null; busy = true; inp.value = ''; grow(); draw(); save();
    try {
      const r = await api('/fotik', { method: 'POST', body: { question: q, history, filters: { period: st.F.period, dept: st.F.dept, product: st.F.product }, screen: ROUTES[route()]?.title } });
      msgs.push({ role: 'assistant', content: r.answer, ctx: r.context });
    } catch (e) {
      if (e.status === 401) return;
      msgs.pop(); failed = { q, error: e.message }; inp.value = q; grow();
    } finally {
      busy = false; save();
      if (!box.hidden) { draw(); if (!box.contains(document.activeElement) || document.activeElement.disabled) inp.focus(); }
    }
  }
  const grow = () => { inp.style.height = 'auto'; inp.style.height = Math.min(120, inp.scrollHeight + 2) + 'px'; };

  fab.addEventListener('click', open);
  box.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.q) ask(b.dataset.q);
    else if (b.dataset.f === 'close') close();
    else if (b.dataset.f === 'clear') { if (busy) return; msgs = []; failed = null; save(); draw(); inp.focus(); }
    else if (b.dataset.f === 'retry') { const q = failed.q; failed = null; inp.value = ''; ask(q); }
  });
  form.addEventListener('submit', e => { e.preventDefault(); ask(inp.value); });
  inp.addEventListener('input', grow);
  inp.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(inp.value); } });
  // Esc закрывает Фотика, если поверх нет модального окна дашборда (фокус мог уйти с отключённой кнопки)
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape' || box.hidden || !$('#modal').hidden) return;
    if (box.contains(e.target) || e.target === document.body) { e.stopImmediatePropagation(); close(); }
  }, true);

  /* ---------- показываем кнопку только после входа; переписка — своя у каждого пользователя */
  const app = $('#app');
  let who = null;
  const sync = () => {
    const on = !app.hidden && !!st.user;
    fab.hidden = !on;
    if (on) { if (who !== st.user.login) { who = st.user.login; msgs = ss.get(KEY()) || []; } updateCtx(); }
    else { if (who) ss.del('fp:fotik:' + who); who = null; box.hidden = true; fab.setAttribute('aria-expanded', 'false'); msgs = []; failed = null; }
  };
  new MutationObserver(sync).observe(app, { attributes: true, attributeFilter: ['hidden'] });
  new MutationObserver(updateCtx).observe($('#fbar'), { childList: true, subtree: true });
  addEventListener('hashchange', updateCtx);
  sync();
})();
