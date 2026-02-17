// CSRF: read _csrf cookie and send as X-CSRF-Token header on every htmx request
document.addEventListener('htmx:configRequest', function(event) {
    var match = document.cookie.match(/(?:^|;\s*)_csrf=([^;]*)/);
    if (match) {
        event.detail.headers['X-CSRF-Token'] = match[1];
    }
});
