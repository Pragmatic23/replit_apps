document.addEventListener('DOMContentLoaded', function() {
    // Handle Odoo experience field visibility
    const experienceInputs = document.querySelectorAll('input[name="has_odoo_experience"]');
    const versionField = document.getElementById('current_version')?.closest('.mb-3');
    const editionSection = document.querySelector('.preferred-edition-section');
    
    // Only proceed if all elements exist
    if (experienceInputs.length && versionField && editionSection) {
        // Initially hide fields
        versionField.style.display = 'none';
        editionSection.style.display = 'none';

        experienceInputs.forEach(input => {
            input.addEventListener('change', function() {
                const showFields = this.value === 'yes';
                versionField.style.display = showFields ? 'block' : 'none';
                editionSection.style.display = showFields ? 'block' : 'none';
            });
        });
    }
});
