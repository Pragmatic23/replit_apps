document.addEventListener('DOMContentLoaded', function() {
    const form = document.querySelector('form');
    const loadingSpinner = document.getElementById('loadingSpinner');
    
    if (form) {
        form.addEventListener('submit', function() {
            if (loadingSpinner) {
                loadingSpinner.classList.add('active');
            }
        });
    }
});
