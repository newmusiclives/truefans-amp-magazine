// Auto-submit: any <select> with class "auto-submit" submits its parent form on change
document.addEventListener('change', function(event) {
    if (event.target.matches('select.auto-submit')) {
        event.target.form.requestSubmit();
    }
});

// Toggle expand/collapse for post content cells
document.addEventListener('click', function(event) {
    var td = event.target.closest('.post-toggle');
    if (td) {
        td.classList.toggle('expanded');
    }
});
