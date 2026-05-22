/* DNS Manager — Client-Side JavaScript */

(function() {
    const htmlEl = document.documentElement;
    const stored = localStorage.getItem('dns-manager-theme');
    if (stored) htmlEl.setAttribute('data-bs-theme', stored);

    const toggleBtn = document.getElementById('themeToggle');
    const icon = document.getElementById('themeIcon');

    function updateIcon() {
        if (!icon) return;
        const current = htmlEl.getAttribute('data-bs-theme');
        icon.className = current === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    }
    updateIcon();

    if (toggleBtn) {
        toggleBtn.addEventListener('click', function() {
            const current = htmlEl.getAttribute('data-bs-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            htmlEl.setAttribute('data-bs-theme', next);
            localStorage.setItem('dns-manager-theme', next);
            updateIcon();
        });
    }
})();

(function() {
    const btn = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    if (btn && sidebar) {
        btn.addEventListener('click', function() { sidebar.classList.toggle('show'); });
        document.addEventListener('click', function(e) {
            if (window.innerWidth < 768 && sidebar.classList.contains('show')) {
                if (!sidebar.contains(e.target) && !btn.contains(e.target)) {
                    sidebar.classList.remove('show');
                }
            }
        });
    }
})();

function confirmDelete(type, name) {
    return confirm('Are you sure you want to delete this ' + type + ': ' + name + '?\n\nThis action cannot be undone.');
}

(function() {
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) bsAlert.close();
        }, 5000);
    });
})();
