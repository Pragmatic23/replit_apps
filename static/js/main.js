document.addEventListener('DOMContentLoaded', function() {
    const editionVersionContainer = document.getElementById('edition-version-container');
    const experienceRadios = document.querySelectorAll('input[name="has_odoo_experience"]');
    
    // Only proceed if all required elements exist
    if (!editionVersionContainer || experienceRadios.length === 0) {
        console.log('Required form elements not found');
        return;
    }
    
    const editionInputs = document.querySelectorAll('input[name="preferred_edition"]');
    const versionSelect = document.getElementById('current_version');
    
    // Handle experience radio changes
    experienceRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            // Ensure container still exists when handling change
            if (editionVersionContainer) {
                editionVersionContainer.style.display = this.value === 'yes' ? 'block' : 'none';
                
                // Update required attributes
                const isRequired = this.value === 'yes';
                editionInputs.forEach(input => {
                    if (input) input.required = isRequired;
                });
                if (versionSelect) versionSelect.required = isRequired;
            }
        });
    });

    // Set initial state
    const selectedExperience = document.querySelector('input[name="has_odoo_experience"]:checked');
    if (selectedExperience && editionVersionContainer) {
        editionVersionContainer.style.display = selectedExperience.value === 'yes' ? 'block' : 'none';
        if (selectedExperience.value === 'yes') {
            editionInputs.forEach(input => {
                if (input) input.required = true;
            });
            if (versionSelect) versionSelect.required = true;
        }
    }
});
