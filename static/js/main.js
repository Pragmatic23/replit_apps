document.addEventListener('DOMContentLoaded', function() {
    // Only execute if we're on the form page
    const editionVersionContainer = document.getElementById('edition-version-container');
    const experienceRadios = document.getElementsByName('has_odoo_experience');
    
    // Only proceed if we're on the page with the form
    if (editionVersionContainer && experienceRadios.length > 0) {
        // Add required attribute to edition fields when experience is 'yes'
        const editionInputs = document.querySelectorAll('input[name="preferred_edition"]');
        const versionSelect = document.getElementById('current_version');
        
        experienceRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                if (this.value === 'yes') {
                    editionVersionContainer.style.display = 'block';
                    // Make edition and version required when user has experience
                    editionInputs.forEach(input => input.required = true);
                    if (versionSelect) versionSelect.required = true;
                } else {
                    editionVersionContainer.style.display = 'none';
                    // Remove required attribute when user has no experience
                    editionInputs.forEach(input => input.required = false);
                    if (versionSelect) versionSelect.required = false;
                }
            });
        });

        // Check initial state on page load
        const selectedExperience = document.querySelector('input[name="has_odoo_experience"]:checked');
        if (selectedExperience && selectedExperience.value === 'yes') {
            editionVersionContainer.style.display = 'block';
            editionInputs.forEach(input => input.required = true);
            if (versionSelect) versionSelect.required = true;
        }
    }
});
