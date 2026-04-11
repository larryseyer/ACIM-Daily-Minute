// Theme toggle — loads synchronously in <head> to prevent flash
(function () {
    var saved = localStorage.getItem('theme');
    if (saved === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    }
})();

function toggleTheme() {
    var html = document.documentElement;
    var current = html.getAttribute('data-theme');
    var next = current === 'light' ? 'dark' : 'light';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);

    // Update all toggle button icons
    var toggles = document.querySelectorAll('.theme-toggle');
    toggles.forEach(function (btn) {
        btn.textContent = next === 'light' ? '\u2600' : '\u263E';
    });
}

// Set initial icon once DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    var theme = document.documentElement.getAttribute('data-theme') || 'dark';
    var toggles = document.querySelectorAll('.theme-toggle');
    toggles.forEach(function (btn) {
        btn.textContent = theme === 'light' ? '\u2600' : '\u263E';
    });
});
