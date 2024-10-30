document.addEventListener('DOMContentLoaded', function() {
    // Get form elements
    const editionVersionContainer = document.getElementById('edition-version-container');
    const experienceRadios = document.querySelectorAll('input[name="has_odoo_experience"]');
    
    // Check if we're on the form page
    if (!editionVersionContainer) {
        console.debug('Not on form page or container not found');
        return;
    }

    if (!experienceRadios || experienceRadios.length === 0) {
        console.debug('Experience radio buttons not found');
        return;
    }
    
    const editionInputs = document.querySelectorAll('input[name="preferred_edition"]');
    const versionSelect = document.getElementById('current_version');
    
    // Function to update form fields visibility and requirements
    function updateFormFields(showFields) {
        if (editionVersionContainer) {
            editionVersionContainer.style.display = showFields ? 'block' : 'none';
            
            // Update required attributes
            if (editionInputs) {
                editionInputs.forEach(input => {
                    if (input) {
                        input.required = showFields;
                    }
                });
            }
            
            if (versionSelect) {
                versionSelect.required = showFields;
            }
        }
    }
    
    // Handle experience radio changes
    experienceRadios.forEach(radio => {
        if (radio) {
            radio.addEventListener('change', function() {
                updateFormFields(this.value === 'yes');
            });
        }
    });

    // Set initial state
    const selectedExperience = document.querySelector('input[name="has_odoo_experience"]:checked');
    if (selectedExperience) {
        updateFormFields(selectedExperience.value === 'yes');
    } else {
        // If no option is selected, hide the fields by default
        updateFormFields(false);
    }
});
