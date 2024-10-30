document.addEventListener('DOMContentLoaded', function() {
    // Get form elements with proper null checks
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
    
    // Validate required elements exist
    if (!editionVersionContainer || !experienceRadios.length) {
        console.debug('Required form elements not found');
        return;
    }
    
    // Function to safely toggle form field visibility and requirements
    function updateFormFields(showFields) {
        try {
            // Update container visibility
            editionVersionContainer.style.display = showFields ? 'block' : 'none';
            
            // Update edition inputs
            editionInputs.forEach(input => {
                if (input) {
                    input.required = showFields;
                }
            });
            
            // Update version select
            if (versionSelect) {
                versionSelect.required = showFields;
                // Reset selection when hiding
                if (!showFields) {
                    versionSelect.selectedIndex = 0;
                }
            }
        } catch (error) {
            console.error('Error updating form fields:', error);
        }
    }
    
    // Handle experience radio changes
    experienceRadios.forEach(radio => {
        if (radio) {
            radio.addEventListener('change', function(event) {
                updateFormFields(event.target.value === 'yes');
            });
        }
    });
    
    // Set initial state based on current selection
    const selectedExperience = form.querySelector('input[name="has_odoo_experience"]:checked');
    updateFormFields(selectedExperience && selectedExperience.value === 'yes');
});
