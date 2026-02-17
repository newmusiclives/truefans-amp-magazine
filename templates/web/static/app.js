// Auto-submit: any <select> with class "auto-submit" submits its parent form on change
document.addEventListener('change', function(event) {
    if (event.target.matches('select.auto-submit')) {
        event.target.form.requestSubmit();
    }
});
