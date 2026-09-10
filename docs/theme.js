// Theme, navigation, and shared helpers.
// Theme runs synchronously in <head> to prevent a flash of the wrong scheme.

(function () {
    var saved = localStorage.getItem('theme');
    if (saved === 'light' || saved === 'dark') {
        document.documentElement.setAttribute('data-theme', saved);
    }
})();

function currentTheme() {
    return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

function applyTheme(next) {
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);

    var label = next === 'light' ? 'Switch to dark theme' : 'Switch to light theme';
    document.querySelectorAll('.theme-toggle').forEach(function (btn) {
        btn.setAttribute('aria-label', label);
    });
    document.querySelectorAll('.theme-toggle--overlay').forEach(function (btn) {
        btn.textContent = next === 'light' ? 'Dark theme' : 'Light theme';
    });

    var meta = document.querySelectorAll('meta[name="theme-color"]');
    var color = next === 'light' ? '#faf6ef' : '#14131c';
    meta.forEach(function (el) {
        el.setAttribute('content', color);
        el.removeAttribute('media');
    });
}

function toggleTheme() {
    applyTheme(currentTheme() === 'light' ? 'dark' : 'light');
}

function initNav() {
    var overlay = document.getElementById('nav-overlay');
    var toggle = document.querySelector('.site-nav__toggle');
    if (!overlay || !toggle) return;

    var closeBtn = overlay.querySelector('.site-nav__close');

    function openMenu() {
        overlay.classList.add('open');
        document.body.classList.add('nav-open');
        toggle.setAttribute('aria-expanded', 'true');
        toggle.setAttribute('aria-label', 'Close menu');
        if (closeBtn) closeBtn.focus();
    }

    function closeMenu() {
        if (!overlay.classList.contains('open')) return;
        overlay.classList.remove('open');
        document.body.classList.remove('nav-open');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.setAttribute('aria-label', 'Open menu');
        toggle.focus();
    }

    toggle.addEventListener('click', function () {
        if (overlay.classList.contains('open')) closeMenu();
        else openMenu();
    });

    if (closeBtn) closeBtn.addEventListener('click', closeMenu);

    overlay.querySelectorAll('a').forEach(function (link) {
        link.addEventListener('click', closeMenu);
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeMenu();
    });

    document.querySelectorAll('.theme-toggle').forEach(function (btn) {
        btn.addEventListener('click', toggleTheme);
    });

    document.querySelectorAll('.theme-toggle--overlay').forEach(function (btn) {
        btn.addEventListener('click', function () {
            toggleTheme();
            closeMenu();
        });
    });
}

function formatAcimDate(dateStr, month) {
    if (!dateStr) return '';
    var d = new Date(dateStr + 'T12:00:00');
    return d.toLocaleDateString('en-US', {
        year: 'numeric',
        month: month || 'long',
        day: 'numeric'
    });
}

function formatAcimSource(ref) {
    if (!ref) return '';
    var map = {
        'Manual': 'Manual for Teachers',
        'Workbook': 'Workbook for Students',
        'Text Part A': 'The Text',
        'Text Part B': 'The Text',
        'Text': 'The Text'
    };
    return map[ref] || ref;
}

function normalizeAcimText(text) {
    if (!text) return '';
    var lines = text.replace(/\r\n/g, '\n').split('\n');
    var paras = [];
    var buf = '';

    function flush() {
        var t = buf.replace(/[ \t]+/g, ' ').trim();
        if (t) paras.push(t);
        buf = '';
    }

    lines.forEach(function (line) {
        var t = line.trim();
        if (!t) {
            flush();
            return;
        }
        if (/^[\[“"']/.test(t) || /^\[[0-9]+\]/.test(t)) {
            flush();
            paras.push(t);
            return;
        }
        if (buf && /[.!?:]["”']?$/.test(buf) && /^[A-Z“"\[]/.test(t)) {
            flush();
            buf = t;
            return;
        }
        buf = buf ? buf + ' ' + t : t;
    });
    flush();
    return paras.join('\n\n');
}

function renderAcimParagraphs(el, text) {
    if (!el) return;
    el.textContent = '';
    var cleaned = normalizeAcimText(text);
    if (!cleaned) return;
    cleaned.split(/\n\n+/).forEach(function (chunk) {
        var p = document.createElement('p');
        p.textContent = chunk.trim();
        el.appendChild(p);
    });
}

function stripLessonPrefix(title, number) {
    if (!title) return '';
    var re = new RegExp('^Lesson\\s+' + (number || '\\d+') + '\\s*:\\s*', 'i');
    return title.replace(re, '').trim();
}

document.addEventListener('DOMContentLoaded', function () {
    applyTheme(currentTheme());
    initNav();
});
