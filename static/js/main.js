document.addEventListener('DOMContentLoaded', function() {
    const form = document.querySelector('form[action="/get_recommendations"]');
    
    // Only proceed if we're on the form page
    if (!form) {
        console.debug('Not on recommendations form page');
        return;
    }
    
    const editionVersionContainer = document.getElementById('edition-version-container');
    const experienceRadios = form.querySelectorAll('input[name="has_odoo_experience"]');
    const editionInputs = form.querySelectorAll('input[name="preferred_edition"]');
    const versionSelect = document.getElementById('current_version');
    
    // Function to safely update form fields
    function updateFormFields(showFields) {
        try {
            if (editionVersionContainer) {
                editionVersionContainer.style.display = showFields ? 'block' : 'none';
            }
            
            if (editionInputs) {
                editionInputs.forEach(input => {
                    if (input) {
                        input.required = showFields;
                        if (!showFields) {
                            input.checked = false;
                        }
                    }
                });
            }
            
            if (versionSelect) {
                versionSelect.required = showFields;
                if (!showFields) {
                    versionSelect.selectedIndex = 0;
                }
            }
        } catch (error) {
            console.error('Error updating form fields:', error);
        }
    }
    
    // Only add event listeners if elements exist
    if (experienceRadios) {
        experienceRadios.forEach(radio => {
            if (radio) {
                radio.addEventListener('change', function() {
                    updateFormFields(this.value === 'yes');
                });
            }
        });
    }
    
    // Set initial state if elements exist
    const selectedExperience = form.querySelector('input[name="has_odoo_experience"]:checked');
    if (selectedExperience) {
        updateFormFields(selectedExperience.value === 'yes');
    }
});
