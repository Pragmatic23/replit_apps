document.addEventListener('DOMContentLoaded', function() {
    // Handle Odoo experience field visibility
    const experienceInputs = document.querySelectorAll('input[name="has_odoo_experience"]');
    const versionField = document.querySelector('#current_version').closest('.mb-3');
    const editionField = document.querySelector('.preferred-edition-section');

    // Initially hide fields
    if (versionField && editionField) {
        versionField.style.display = 'none';
        editionField.style.display = 'none';

        experienceInputs.forEach(input => {
            input.addEventListener('change', function() {
                const showFields = this.value === 'yes';
                versionField.style.display = showFields ? 'block' : 'none';
                editionField.style.display = showFields ? 'block' : 'none';
            });
        });
    }
});
