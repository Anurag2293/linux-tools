(function () {
  'use strict';

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var root_ = document.documentElement;
  var mobile = matchMedia('(max-width: 820px)');
  var page = JSON.parse($('#fv').textContent);
  var TYPES = page.types, ROOTS = page.roots, PUBLIC = page.public, MACHINE = page.machine;
  var isMac = /Mac|iPhone|iPad/.test(navigator.platform);

  var store = {
    get: function (k, d) { try { var v = localStorage.getItem('fv.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem('fv.' + k, JSON.stringify(v)); } catch (e) {} }
  };
  try { localStorage.removeItem('fv.roots'); } catch (e) {}

  var P = {
    panel: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>',
    left: '<path d="m15 18-6-6 6-6"/>', right: '<path d="m9 18 6-6-6-6"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    monitor: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    up: '<path d="M12 19V5M5 12l7-7 7 7"/>', collapse: '<path d="m7 20 5-5 5 5M7 4l5 5 5-5"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    check: '<path d="M20 6 9 17l-5-5"/>', code: '<path d="m16 18 6-6-6-6M8 6l-6 6 6 6"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    file: '<path d="M14 2.5H6.5a2 2 0 0 0-2 2v15a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V8z"/><path d="M14 2.5V8h5.5"/>',
    download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
    branch: '<circle cx="6" cy="5" r="3"/><circle cx="6" cy="19" r="3"/><circle cx="18" cy="6" r="3"/><path d="M6 8v8M18 9a9 9 0 0 1-9 9"/>',
    external: '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    wrap: '<path d="M3 6h18M3 12h15a3 3 0 0 1 0 6h-4M3 18h7"/><path d="m16 16-2 2 2 2"/>',
    lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    enter: '<path d="M9 10 4 15l5 5"/><path d="M20 4v7a4 4 0 0 1-4 4H4"/>',
    folder: '<path d="M3 6.5a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
  };
  function icon(name) { return '<svg class="i" viewBox="0 0 24 24" aria-hidden="true">' + (P[name] || P.file) + '</svg>'; }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function enc(p) { return p.split('/').map(encodeURIComponent).join('/'); }
  function viewUrl(p) { return enc(p) + '?view'; }
  function base(p) { return p.replace(/\/$/, '').split('/').pop() || '/'; }
  function typeOf(name) { var i = name.lastIndexOf('.'); return TYPES[name] || (i > 0 && TYPES[name.slice(i).toLowerCase()]) || ''; }
  function fi(name, isDir) { return '<span class="fi ' + (isDir ? 'dir' : typeOf(name)) + '"></span>'; }
  function ago(t) {
    var s = Date.now() / 1000 - t;
    if (s < 60) return 'just now';
    if (s < 3600) return Math.floor(s / 60) + 'm ago';
    if (s < 86400) return Math.floor(s / 3600) + 'h ago';
    if (s < 30 * 86400) return Math.floor(s / 86400) + 'd ago';
    var d = new Date(t * 1000);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function stamp(t) {
    var d = new Date(t * 1000);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0') +
      ' ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }
  function withView(u) { if (!/(^|[?&])view(=|&|$)/.test(u.search.slice(1))) u.search = u.search ? u.search + '&view' : '?view'; return u; }

  var main = $('#main'), content = $('#content'), toc = $('#toc'), treeEl = $('#tree');

  /* toast + clipboard */
  var toastEl = document.createElement('div'); toastEl.className = 'toast'; document.body.appendChild(toastEl);
  var toastTimer;
  function toast(text) {
    toastEl.innerHTML = icon('check') + esc(text); toastEl.classList.add('on');
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { toastEl.classList.remove('on'); }, 1600);
  }
  function copy(text, what) {
    var done = function () { toast(what + ' copied'); };
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(done, fallback);
    fallback();
    function fallback() {
      var t = document.createElement('textarea'); t.value = text; t.style.position = 'fixed'; t.style.opacity = '0';
      document.body.appendChild(t); t.select(); try { document.execCommand('copy'); done(); } catch (e) {} t.remove();
    }
  }

  /* top bar */
  var top = $('#top');
  top.innerHTML =
    '<button class="ib" id="navbtn" title="Toggle sidebar (' + (isMac ? '⌘' : 'Ctrl+') + 'B)">' + icon('panel') + '</button>' +
    '<a class="brand" href="' + viewUrl(ROOTS[0] + '/') + '"><span class="mark"></span><span class="name">' + esc(MACHINE) + '</span></a>' +
    '<svg class="slash first" viewBox="0 0 16 24"><path d="M11 3 5 21" stroke="currentColor" stroke-width="1.2" fill="none"/></svg>' +
    '<a class="ws" id="ws" href="#"><span class="fi dir"></span><span id="wsname"></span></a>' +
    '<div class="grow"></div>' +
    '<div class="navs"><button class="ib" id="back" title="Back (Alt+←)">' + icon('left') + '</button>' +
    '<button class="ib" id="fwd" title="Forward (Alt+→)">' + icon('right') + '</button></div>' +
    '<button class="search" id="searchbtn" title="Search files">' + icon('search') + '<span>Search files…</span><kbd>' + (isMac ? '⌘' : 'Ctrl ') + 'K</kbd></button>' +
    '<button class="ib" id="themebtn"></button>';

  var themes = ['system', 'light', 'dark'];
  function applyTheme(t) {
    if (t === 'system') delete root_.dataset.theme; else root_.dataset.theme = t;
    $('#themebtn').innerHTML = icon(t === 'light' ? 'sun' : t === 'dark' ? 'moon' : 'monitor');
    $('#themebtn').title = 'Theme: ' + t;
  }
  var theme = store.get('theme', 'system');
  applyTheme(theme);
  $('#themebtn').onclick = function () {
    theme = themes[(themes.indexOf(theme) + 1) % 3]; store.set('theme', theme); applyTheme(theme); toast('Theme: ' + theme);
  };

  function toggleNav() {
    if (mobile.matches) root_.classList.toggle('nav-open');
    else store.set('hidden', root_.classList.toggle('nav-hidden'));
  }
  $('#navbtn').onclick = toggleNav;
  $('#scrim').onclick = function () { root_.classList.remove('nav-open'); };

  /* In-app history. Navigation replaces the browser entry instead of pushing one, so the tab
     keeps a single entry and stays closable by a newer tab of the same workspace. */
  var hist = { back: [], fwd: [] };
  try { hist = JSON.parse(sessionStorage.getItem('fv.hist')) || hist; } catch (e) {}
  function saveHist() {
    hist.back = hist.back.slice(-100); hist.fwd = hist.fwd.slice(-100);
    try { sessionStorage.setItem('fv.hist', JSON.stringify(hist)); } catch (e) {}
  }
  function here() { return { u: location.pathname + location.search + location.hash, top: content.scrollTop }; }
  function goBack() { var e = hist.back.pop(); if (!e) return; hist.fwd.push(here()); saveHist(); navigate(e.u, { record: false, top: e.top }); }
  function goFwd() { var e = hist.fwd.pop(); if (!e) return; hist.back.push(here()); saveHist(); navigate(e.u, { record: false, top: e.top }); }
  $('#back').onclick = goBack;
  $('#fwd').onclick = goFwd;
  function navState() {
    $('#back').disabled = !hist.back.length;
    $('#fwd').disabled = !hist.fwd.length;
  }

  /* sidebar resize */
  var grip = $('#grip'), side = $('#side');
  grip.addEventListener('pointerdown', function (e) {
    e.preventDefault(); grip.setPointerCapture(e.pointerId); grip.classList.add('drag');
    var width = side.offsetWidth;
    function move(ev) { width = Math.max(200, Math.min(ev.clientX, innerWidth * 0.5)); root_.style.setProperty('--side-w', width + 'px'); }
    function up() { grip.classList.remove('drag'); grip.removeEventListener('pointermove', move); grip.removeEventListener('pointerup', up); store.set('w', Math.round(width)); }
    grip.addEventListener('pointermove', move); grip.addEventListener('pointerup', up);
  });

  /* file tree */
  var Tree = (function () {
    var root = null, open = new Set(store.get('open', []));
    var head = $('#sidehead');
    head.innerHTML = '<span class="label" id="rootlabel"></span>' +
      '<button class="ib" id="upbtn" title="Show parent folder">' + icon('up') + '</button>' +
      '<button class="ib" id="collapse" title="Collapse folders">' + icon('collapse') + '</button>';
    function save() { store.set('open', Array.from(open).slice(-500)); }
    function load(dir) {
      return fetch(enc(dir) + '?ls', { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : { entries: [], error: r.status }; })
        .catch(function () { return { entries: [], error: 1 }; });
    }
    function note(text, depth) {
      var li = document.createElement('li'); li.className = 'tnote'; li.style.setProperty('--d', depth); li.textContent = text; return li;
    }
    function fill(ul, dir, depth) {
      return load(dir).then(function (d) {
        ul.textContent = ''; var waits = [];
        d.entries.forEach(function (e) {
          var li = node(dir + e.n + (e.d ? '/' : ''), e.n, e.d, depth);
          ul.appendChild(li); if (li._loaded) waits.push(li._loaded);
        });
        if (d.more) ul.appendChild(note(d.more + ' more not shown', depth));
        if (!d.entries.length) ul.appendChild(note(d.error ? 'Cannot read' : 'Empty', depth));
        return Promise.all(waits);
      });
    }
    function setOpen(li, on) {
      var p = li.dataset.p, depth = +li.dataset.d;
      li.classList.toggle('open', on);
      if (on) open.add(p); else open.delete(p);
      save();
      if (on && !li._loaded) li._loaded = fill(li.lastChild, p, depth + 1);
      return li._loaded || Promise.resolve();
    }
    function node(p, name, isDir, depth) {
      var li = document.createElement('li'), a = document.createElement('a');
      li.dataset.p = p; li.dataset.d = depth;
      a.className = 'row'; a.style.setProperty('--d', depth); a.href = viewUrl(p); a.title = p;
      a.innerHTML = '<span class="chev">' + (isDir ? icon('right') : '') + '</span>' + fi(name, isDir) + '<span class="nm">' + esc(name) + '</span>';
      if (p === page.path) a.classList.add('active');
      li.appendChild(a);
      if (isDir) {
        var ul = document.createElement('ul'); ul.style.setProperty('--d', depth + 1); li.appendChild(ul);
        a.addEventListener('click', function (e) {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
          e.preventDefault(); setOpen(li, !li.classList.contains('open'));
        });
        if (open.has(p)) setOpen(li, true);
      }
      return li;
    }
    function find(p) { return treeEl.querySelector('li[data-p="' + CSS.escape(p) + '"]'); }
    function reveal(smooth) {
      var a = treeEl.querySelector('.row.active');
      if (!a) return;
      var y = a.getBoundingClientRect().top - treeEl.getBoundingClientRect().top + treeEl.scrollTop;
      if (y < treeEl.scrollTop + 8 || y + a.offsetHeight > treeEl.scrollTop + treeEl.clientHeight - 8)
        treeEl.scrollTo({ top: y - treeEl.clientHeight / 2, behavior: smooth ? 'smooth' : 'auto' });
    }
    function render() {
      $('#rootlabel').textContent = base(root);
      $('#rootlabel').title = root;
      $('#upbtn').hidden = ROOTS.indexOf(root.replace(/\/$/, '')) >= 0;
      var ul = document.createElement('ul'); ul.style.setProperty('--d', 0);
      treeEl.textContent = ''; treeEl.appendChild(ul);
      return fill(ul, root, 0).then(function () {
        try { var y = sessionStorage.getItem('fv.tree'); if (y !== null) treeEl.scrollTop = +y; } catch (e) {}
        return sync(page.path, false);
      });
    }
    function sync(path, smooth) {
      if (path.indexOf(root) !== 0) return Promise.resolve();
      var parts = path.slice(root.length).split('/'), acc = root, chain = Promise.resolve();
      parts.slice(0, -1).forEach(function (seg) {
        acc += seg + '/';
        var p = acc;
        chain = chain.then(function () { var li = find(p); return li ? setOpen(li, true) : null; });
      });
      return chain.then(function () {
        $$('.row.active', treeEl).forEach(function (a) { a.classList.remove('active'); });
        var li = find(path);
        if (li) li.firstChild.classList.add('active');
        reveal(smooth);
      });
    }
    $('#upbtn').onclick = function () { root = root.replace(/[^/]+\/$/, ''); render(); updateWs(); };
    $('#collapse').onclick = function () { open.clear(); save(); $$('li.open', treeEl).forEach(function (li) { li.classList.remove('open'); }); };
    addEventListener('pagehide', function () { try { sessionStorage.setItem('fv.tree', treeEl.scrollTop); } catch (e) {} });
    return {
      root: function () { return root; },
      show: function (p) {
        if (root !== p.root && (root === null || p.path.indexOf(root) !== 0)) { root = p.root; return render(); }
        return sync(p.path, true);
      }
    };
  })();

  function updateWs() {
    var r = Tree.root() || page.root;
    $('#wsname').textContent = base(r);
    $('#ws').href = viewUrl(r);
    $('#ws').title = r;
  }

  /* tabs */
  var tabs = store.get('tabs', []);
  function hints(paths) {
    // shortest trailing folder path that tells same-named tabs apart
    var out = {}, groups = {};
    paths.forEach(function (p) { (groups[base(p)] = groups[base(p)] || []).push(p); });
    Object.keys(groups).forEach(function (b) {
      var g = groups[b];
      if (g.length < 2) return;
      for (var n = 1; ; n++) {
        var tails = g.map(function (p) { return p.split('/').slice(0, -1).slice(-n).join('/'); });
        if (new Set(tails).size === g.length || n > 8) { g.forEach(function (p, i) { out[p] = tails[i]; }); return; }
      }
    });
    return out;
  }
  function renderTabs() {
    var hint = hints(tabs);
    $('#tabs').innerHTML = tabs.map(function (p) {
      var b = base(p);
      return '<a class="tab' + (p === page.path ? ' active' : '') + '" href="' + viewUrl(p) + '" title="' + esc(p) + '" data-p="' + esc(p) + '">' +
        fi(b, false) + '<span class="nm">' + esc(b) + '</span>' + (hint[p] ? '<span class="hint">&lrm;' + esc(hint[p]) + '&lrm;</span>' : '') +
        '<span class="x" role="button" title="Close">' + icon('x') + '</span></a>';
    }).join('');
    var on = $('.tab.active');
    if (on) on.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }
  function closeTab(p) {
    var i = tabs.indexOf(p); if (i < 0) return;
    tabs.splice(i, 1); store.set('tabs', tabs);
    if (p === page.path) {
      var next = tabs[Math.min(i, tabs.length - 1)];
      return navigate(viewUrl(next || p.replace(/[^/]+$/, '')));
    }
    renderTabs();
  }
  $('#tabs').addEventListener('click', function (e) {
    var x = e.target.closest('.x');
    if (x) { e.preventDefault(); e.stopPropagation(); closeTab(x.parentNode.dataset.p); }
  }, true);
  // a plain mouse wheel scrolls the tab strip sideways
  $('#tabs').addEventListener('wheel', function (e) {
    var el = e.currentTarget;
    if (e.ctrlKey || Math.abs(e.deltaX) >= Math.abs(e.deltaY) || el.scrollWidth <= el.clientWidth) return;
    e.preventDefault();
    el.scrollLeft += e.deltaMode === 1 ? e.deltaY * 20 : e.deltaY;
  }, { passive: false });
  $('#tabs').addEventListener('auxclick', function (e) {
    var t = e.target.closest('.tab'); if (t && e.button === 1) { e.preventDefault(); closeTab(t.dataset.p); }
  });
  function remember(p) {
    if (p.isDir || p.kind === 'empty' && !p.info.size) return;
    if (tabs.indexOf(p.path) < 0) {
      tabs.push(p.path);
      while (tabs.length > 12) tabs.splice(tabs[0] === p.path ? 1 : 0, 1);
      store.set('tabs', tabs);
    }
    var recent = store.get('recent', []).filter(function (x) { return x !== p.path; });
    recent.unshift(p.path); store.set('recent', recent.slice(0, 30));
  }

  /* crumbs, actions, status */
  function renderCrumbs(p) {
    var r = Tree.root() || p.root, path = p.path, out = [];
    var startAt = path.indexOf(r) === 0 ? r : '/';
    var rel = path.slice(startAt.length).replace(/\/$/, ''), acc = startAt;
    out.push('<a href="' + viewUrl(startAt) + '">' + esc(base(startAt)) + '</a>');
    var segs = rel ? rel.split('/') : [];
    segs.forEach(function (s, i) {
      acc += s + '/';
      out.push('<span class="sep">' + icon('right') + '</span>');
      if (i === segs.length - 1) out.push('<span class="cur">' + fi(s, p.isDir) + esc(s) + '</span>');
      else out.push('<a href="' + viewUrl(acc) + '">' + esc(s) + '</a>');
    });
    var c = $('#crumbs'); c.innerHTML = out.join(''); pinCrumbs();
  }
  // keep the current file in view once fonts and the action buttons have settled the width
  function pinCrumbs() { var c = $('#crumbs'); c.scrollLeft = c.scrollWidth; }
  if (window.ResizeObserver) new ResizeObserver(pinCrumbs).observe($('#crumbs'));
  if (document.fonts) document.fonts.ready.then(pinCrumbs);

  var sel = null;
  function lineSuffix() { return sel ? ':' + sel[0] + (sel[1] !== sel[0] ? '-' + sel[1] : '') : ''; }
  function renderActions(p) {
    var h = [];
    if (p.kind === 'code') h.push('<button class="btn ghost sm' + (root_.classList.contains('wrap') ? ' on' : '') + '" id="wrapbtn" title="Toggle word wrap">' + icon('wrap') + '<span class="lbl">Wrap</span></button>');
    p.actions.forEach(function (a) {
      h.push('<a class="btn ghost sm" href="' + esc(a.href) + '"' + (a.target ? ' target="' + a.target + '"' : '') +
        (a.download ? ' download="' + esc(a.download) + '"' : '') + (a.native ? ' data-native' : '') + ' title="' + esc(a.label) + '">' +
        icon(a.icon) + '<span class="lbl">' + esc(a.label) + '</span></a>');
    });
    h.push('<button class="btn ghost sm" id="copylink" title="Copy tailnet link">' + icon('link') + '<span class="lbl">Copy link</span></button>');
    if (p.editors.length) {
      h.push('<span class="vsep"></span>');
      p.editors.forEach(function (ed, i) {
        h.push('<a class="btn sm' + (i === 0 ? ' primary' : '') + '" data-tpl="' + esc(ed.tpl) + '" data-native href="#">' + esc(ed.label) + '</a>');
      });
    }
    $('#actions').innerHTML = h.join('');
    var w = $('#wrapbtn');
    if (w) w.onclick = function () { var on = root_.classList.toggle('wrap'); store.set('wrap', on); w.classList.toggle('on', on); };
    $('#copylink').onclick = function () { copy(PUBLIC + enc(page.path) + lineSuffix(), 'Link'); };
    updateEditors();
  }
  function updateEditors() {
    var a = sel ? sel[0] : 1, b = sel ? sel[1] : 1;
    $$('#actions [data-tpl]').forEach(function (el) { el.href = el.dataset.tpl.replace('{line}', a).replace('{end}', b); });
  }
  function renderStatus(p) {
    var i = p.info || {}, s = [];
    s.push('<span class="it"><span class="dot"></span>' + esc(MACHINE) + '</span>');
    if (p.git) {
      var branch = p.git.branch + (p.git.detached ? ' (detached)' : '');
      s.push('<span class="it branch" title="' + esc((p.git.detached ? 'Detached HEAD: ' : 'Git branch: ') + p.git.branch) + '">' +
        icon('branch') + '<span class="nm">' + esc(branch) + '</span></span>');
    }
    s.push('<button class="it path hide-m" id="copypath" title="Copy local path">' + esc(p.path) + '</button>');
    s.push('<span class="grow"></span>');
    if (sel) s.push('<span class="it">Ln ' + sel[0] + (sel[1] !== sel[0] ? '–' + sel[1] : '') + '</span>');
    if (i.lines) s.push('<span class="it hide-m">' + i.lines.toLocaleString() + ' lines</span>');
    if (i.items !== undefined) s.push('<span class="it">' + i.items + ' items</span>');
    if (i.lang) s.push('<span class="it">' + esc(i.lang) + '</span>');
    if (i.size) s.push('<span class="it">' + esc(i.size) + '</span>');
    if (i.mtime) s.push('<span class="it hide-m" title="' + stamp(i.mtime) + '">Modified ' + ago(i.mtime) + '</span>');
    $('#status').innerHTML = s.join('');
    var cp = $('#copypath'); if (cp) cp.onclick = function () { copy(page.path + lineSuffix(), 'Path'); };
  }

  var gitRefresh = null;
  function refreshGit() {
    if (document.hidden || page.transient || gitRefresh) return;
    var current = page;
    gitRefresh = fetch(enc(current.path) + '?git', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : { git: null }; })
      .then(function (data) {
        if (page !== current) return;
        current.git = data.git; renderStatus(current);
      })
      .catch(function () {})
      .finally(function () { gitRefresh = null; });
  }
  addEventListener('focus', refreshGit);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refreshGit(); });

  /* line selection */
  function parseHash() {
    var m = location.hash.match(/^#L-?(\d+)(?:-L?(\d+))?$/);
    if (m) return [+m[1], +(m[2] || m[1])];
    return page.line ? [page.line, page.end || page.line] : null;
  }
  function select(range, scroll) {
    $$('.hl span.sel', main).forEach(function (el) { el.classList.remove('sel'); });
    sel = range;
    if (range) {
      var a = Math.min(range[0], range[1]), b = Math.max(range[0], range[1]); sel = [a, b];
      for (var n = a; n <= b && n - a < 5000; n++) { var el = document.getElementById('L-' + n); if (el) el.classList.add('sel'); }
      var first = document.getElementById('L-' + a);
      if (first && scroll) {
        var y = first.getBoundingClientRect().top - content.getBoundingClientRect().top + content.scrollTop;
        content.scrollTop = y - content.clientHeight / 3;
      }
    }
    updateEditors(); renderStatus(page);
  }
  main.addEventListener('click', function (e) {
    var tab = e.target.closest('.sheet-tab'); if (!tab) return;
    $$('.sheet-tab', main).forEach(function (t) { t.classList.toggle('on', t === tab); });
    $$('.sheet', main).forEach(function (s) { s.hidden = s.dataset.sheet !== tab.dataset.sheet; });
  });
  main.addEventListener('click', function (e) {
    var ln = e.target.closest('.linenos'); if (!ln) return;
    var n = +ln.textContent.trim();
    var range = e.shiftKey && sel ? [sel[0], n] : [n, n];
    select(range, false);
    var h = '#L-' + sel[0] + (sel[1] !== sel[0] ? '-' + sel[1] : '');
    history.replaceState(history.state, '', location.pathname + location.search + h);
  });

  /* outline */
  var spy = null;
  function slug(t) { return t.toLowerCase().replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-').slice(0, 64) || 'section'; }
  function buildToc() {
    if (spy) { spy.disconnect(); spy = null; }
    var hs = $$('.md h2, .md h3', main);
    if (main.className !== 'doc' || hs.length < 2) { content.classList.remove('has-toc'); toc.innerHTML = ''; return; }
    var seen = {};
    toc.innerHTML = '<div class="t">' + icon('list') + 'On this page</div>' + hs.map(function (h) {
      if (!h.id) { var s = slug(h.textContent), k = s; while (seen[k] || document.getElementById(k)) k = s + '-' + (seen[s] = (seen[s] || 0) + 1); h.id = k; }
      seen[h.id] = 1;
      return '<a class="l' + h.tagName[1] + '" href="#' + esc(h.id) + '" data-toc>' + esc(h.textContent) + '</a>';
    }).join('');
    content.classList.add('has-toc');
    var links = {}; $$('a', toc).forEach(function (a) { links[a.getAttribute('href').slice(1)] = a; });
    spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { $$('a.on', toc).forEach(function (a) { a.classList.remove('on'); }); if (links[en.target.id]) links[en.target.id].classList.add('on'); }
      });
    }, { root: content, rootMargin: '0px 0px -75% 0px' });
    hs.forEach(function (h) { spy.observe(h); });
  }
  toc.addEventListener('click', function (e) {
    var a = e.target.closest('a[data-toc]'); if (!a) return;
    e.preventDefault();
    var t = document.getElementById(a.getAttribute('href').slice(1));
    if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' });
    history.replaceState(history.state, '', location.pathname + location.search + a.getAttribute('href'));
  });

  /* empty-state icons, relative times */
  function decorate() {
    $$('.empty-icon[data-icon]', main).forEach(function (el) { el.innerHTML = icon(el.dataset.icon); });
    $$('.ftime[data-t]', main).forEach(function (el) { el.textContent = ago(+el.dataset.t); el.title = stamp(+el.dataset.t); });
  }

  /* page lifecycle */
  function show(p, opts) {
    opts = opts || {};
    page = p;
    if (p.body !== undefined) { main.className = p.kind; main.innerHTML = p.body; }
    document.title = p.title + ' · ' + base(p.root);
    content.scrollTop = 0;
    sel = null;
    root_.classList.remove('nav-open');
    decorate();
    remember(p);
    Tree.show(p);
    updateWs();
    renderTabs();
    renderCrumbs(p);
    renderActions(p);
    buildToc();
    if (p.kind === 'code') select(parseHash(), true); else renderStatus(p);
    if (opts.top !== undefined) content.scrollTop = opts.top;
    else if (location.hash && p.kind !== 'code') { var t = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (t) t.scrollIntoView(); }
    navState();
    claimRoot();
  }

  /* One browser tab per workspace: a tab announces the root it shows; an older tab on the
     same root hands its history to the newer one and closes itself. */
  var me = Math.random().toString(36).slice(2), claim = null, chan = null;
  try { chan = new BroadcastChannel('fv'); } catch (e) {}
  function claimRoot() {
    if (!chan || page.transient || (claim && claim.root === page.root)) return;
    claim = { root: page.root, at: Date.now() };
    chan.postMessage({ type: 'claim', root: claim.root, at: claim.at, id: me });
  }
  function newer(m) { return m.at > claim.at || (m.at === claim.at && m.id > me); }
  if (chan) chan.onmessage = function (ev) {
    var m = ev.data;
    if (m.type === 'claim' && claim && m.id !== me && m.root === claim.root && newer(m)) {
      chan.postMessage({ type: 'handoff', to: m.id, back: hist.back.concat([here()]) });
      yieldTab();
    } else if (m.type === 'handoff' && m.to === me) {
      var back = m.back, last = back[back.length - 1];
      if (last && last.u === here().u) back = back.slice(0, -1);
      hist.back = back.concat(hist.back); saveHist(); navState();
    }
  };
  function yieldTab() {
    claim = null;
    window.close();
    setTimeout(function () {
      var o = document.createElement('div'); o.className = 'yielded';
      o.innerHTML = '<div class="empty"><div class="empty-icon">' + icon('external') + '</div><h2>Open in a newer tab</h2>' +
        '<p>' + esc(base(page.root)) + ' moved to the tab you opened last. This tab could not close itself.</p>' +
        '<div class="empty-actions"><button class="btn primary">Use this tab</button></div></div>';
      o.querySelector('button').onclick = function () { o.remove(); claimRoot(); };
      document.body.appendChild(o);
    }, 250);
  }
  if (page.transient) addEventListener('blur', function () { setTimeout(function () { if (page.transient) window.close(); }, 300); }, { once: true });

  var progress = $('#progress'), inflight = null, loaded = location.pathname + location.search;
  function navigate(href, opts) {
    opts = opts || {};
    var u = withView(new URL(href, location.href));
    if (opts.record !== false) { hist.back.push(here()); hist.fwd = []; saveHist(); }
    if (inflight) inflight.abort();
    inflight = new AbortController();
    progress.className = 'progress'; void progress.offsetWidth; progress.className = 'progress run';
    return fetch(u.href, { headers: { 'X-FV-Partial': '1' }, signal: inflight.signal })
      .then(function (r) {
        if (!(r.headers.get('content-type') || '').includes('application/json')) { location.href = u.href; return; }
        return r.json().then(function (p) {
          var fin = new URL(r.url); fin.hash = u.hash;
          history.replaceState(null, '', fin.pathname + fin.search + fin.hash);
          loaded = fin.pathname + fin.search;
          show(p, { top: opts.top });
        });
      })
      .catch(function (e) { if (e.name !== 'AbortError') location.href = u.href; })
      .finally(function () { progress.className = 'progress done'; });
  }
  history.scrollRestoration = 'manual';
  addEventListener('popstate', function () {
    if (location.pathname + location.search === loaded) { if (page.kind === 'code') select(parseHash(), true); return; }
    navigate(location.href, { record: false });
  });
  addEventListener('mouseup', function (e) {
    if (e.button === 3) { e.preventDefault(); goBack(); }
    if (e.button === 4) { e.preventDefault(); goFwd(); }
  });
  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest('a[href]'); if (!a) return;
    if ((a.target && a.target !== '_self') || a.hasAttribute('download') || a.hasAttribute('data-native')) return;
    var u = new URL(a.href, location.href);
    if (u.origin !== location.origin || u.pathname.indexOf('/_fv/') === 0) return;
    if (/(^|[?&])(raw|embed)(=|&|$)/.test(u.search.slice(1))) return;
    e.preventDefault();
    if (u.pathname === location.pathname && u.search === location.search && u.hash) {
      var t = document.getElementById(decodeURIComponent(u.hash.slice(1)));
      if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return history.replaceState(null, '', u.pathname + u.search + u.hash);
    }
    navigate(u.href);
  });

  /* palette */
  var pal = document.createElement('div');
  pal.className = 'pal-wrap'; pal.hidden = true;
  pal.innerHTML = '<div class="pal" role="dialog" aria-label="Search files"><div class="pal-in">' + icon('search') +
    '<input id="palq" placeholder="Search files by name or path…" autocomplete="off" spellcheck="false"><span class="spin" id="palspin"></span><kbd>Esc</kbd></div>' +
    '<div class="pal-list" id="pall"></div><div class="pal-foot"><span><kbd>↑</kbd><kbd>↓</kbd> to navigate</span>' +
    '<span><kbd>↵</kbd> to open</span><span class="grow"></span><span id="palroot"></span></div></div>';
  document.body.appendChild(pal);
  var palq = $('#palq'), pall = $('#pall'), items = [], cursor = 0, palCtl = null, palTimer = null;
  function openPal() {
    pal.hidden = false; palq.value = ''; $('#palroot').innerHTML = icon('folder') + esc(base(Tree.root() || page.root));
    listRecent(); setTimeout(function () { palq.focus(); }, 0);
  }
  function closePal() { pal.hidden = true; if (palCtl) palCtl.abort(); }
  function mark(name, q) {
    var out = '', j = 0, lq = q.toLowerCase(), ln = name.toLowerCase(), idx = ln.indexOf(lq);
    if (lq && idx >= 0) return esc(name.slice(0, idx)) + '<b>' + esc(name.slice(idx, idx + q.length)) + '</b>' + esc(name.slice(idx + q.length));
    for (var i = 0; i < name.length; i++) {
      if (j < lq.length && ln[i] === lq[j]) { out += '<b>' + esc(name[i]) + '</b>'; j++; } else out += esc(name[i]);
    }
    return out;
  }
  function draw(list, q, group) {
    items = list; cursor = 0;
    if (!list.length) { pall.innerHTML = '<div class="pal-none">' + (q ? 'No files match “' + esc(q) + '”.' : 'Type to search files.') + '</div>'; return; }
    var r = Tree.root() || page.root;
    pall.innerHTML = (group ? '<div class="pal-group">' + group + '</div>' : '') + list.map(function (p, i) {
      var b = base(p), dir = p.slice(0, p.length - b.length).replace(/\/$/, '');
      if (dir.indexOf(r) === 0) dir = dir.slice(r.length) || '.';
      return '<a class="pal-item' + (i === 0 ? ' on' : '') + '" href="' + viewUrl(p) + '" data-i="' + i + '">' + fi(b, false) +
        '<span class="nm">' + mark(b, q.replace(/\s+/g, '')) + '</span><span class="dir">&lrm;' + esc(dir) + '&lrm;</span>' +
        '<span class="enter">' + icon('enter') + '</span></a>';
    }).join('');
  }
  function listRecent() {
    var recent = store.get('recent', []).filter(function (p) { return p !== page.path; }).slice(0, 12);
    draw(recent, '', recent.length ? 'Recent' : '');
  }
  function query() {
    var q = palq.value.trim(), r = Tree.root() || page.root;
    if (!q) return listRecent();
    if (palCtl) palCtl.abort(); palCtl = new AbortController();
    $('#palspin').classList.add('on');
    fetch(enc(r) + '?find=' + encodeURIComponent(q), { signal: palCtl.signal })
      .then(function (res) { return res.json(); })
      .then(function (d) { draw(d.results.map(function (rel) { return r + rel; }), q, 'Files'); })
      .catch(function () {})
      .finally(function () { $('#palspin').classList.remove('on'); });
  }
  function move(d) {
    if (!items.length) return;
    var els = $$('.pal-item', pall);
    els[cursor].classList.remove('on');
    cursor = (cursor + d + items.length) % items.length;
    els[cursor].classList.add('on'); els[cursor].scrollIntoView({ block: 'nearest' });
  }
  palq.addEventListener('input', function () { clearTimeout(palTimer); palTimer = setTimeout(query, 70); });
  palq.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown' || (e.ctrlKey && e.key === 'n')) { e.preventDefault(); move(1); }
    else if (e.key === 'ArrowUp' || (e.ctrlKey && e.key === 'p')) { e.preventDefault(); move(-1); }
    else if (e.key === 'Enter' && items[cursor]) { e.preventDefault(); closePal(); navigate(viewUrl(items[cursor])); }
    else if (e.key === 'Escape') { e.preventDefault(); closePal(); }
  });
  pall.addEventListener('mousemove', function (e) {
    var it = e.target.closest('.pal-item'); if (!it || +it.dataset.i === cursor) return;
    $$('.pal-item.on', pall).forEach(function (x) { x.classList.remove('on'); });
    it.classList.add('on'); cursor = +it.dataset.i;
  });
  pall.addEventListener('click', function () { closePal(); }, true);
  pal.addEventListener('mousedown', function (e) { if (e.target === pal) closePal(); });
  $('#searchbtn').onclick = openPal;

  /* keyboard */
  document.addEventListener('keydown', function (e) {
    var mod = e.metaKey || e.ctrlKey, typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if (mod && (e.key === 'k' || e.key === 'p')) { e.preventDefault(); pal.hidden ? openPal() : closePal(); return; }
    if (mod && e.key === 'b') { e.preventDefault(); toggleNav(); return; }
    if (e.key === 'Escape') { root_.classList.remove('nav-open'); if (!pal.hidden) closePal(); return; }
    if (typing) return;
    if (e.altKey && e.key === 'ArrowLeft') { e.preventDefault(); goBack(); }
    if (e.altKey && e.key === 'ArrowRight') { e.preventDefault(); goFwd(); }
    if (e.key === '/' && !mod) { e.preventDefault(); openPal(); }
  });

  setInterval(function () { if (page.info && page.info.mtime) renderStatus(page); decorate(); refreshGit(); }, 60000);
  show(page);
})();
