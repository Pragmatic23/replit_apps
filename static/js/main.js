document.addEventListener('DOMContentLoaded', function() {
    // Debug helper function
    function debug(message) {
        console.debug(`[Odoo Form]: ${message}`);
    }

    // Get the form and validate we're on the right page
    const form = document.querySelector('form[action="/get_recommendations"]');
    if (!form) {
        debug('Not on recommendations form page - skipping form logic initialization');
        return;
    }

    // Get all required form elements
    const editionVersionContainer = document.getElementById('edition-version-container');
    const experienceRadios = form.querySelectorAll('input[name="has_odoo_experience"]');
    const editionInputs = form.querySelectorAll('input[name="preferred_edition"]');
    const versionSelect = document.getElementById('current_version');

    // Validate required elements exist
    if (!editionVersionContainer || !experienceRadios.length) {
        debug('Required form elements missing - check HTML structure');
        return;
    }

    debug('Form elements found - initializing conditional logic');

    // Function to safely update form fields with error handling
    function updateFormFields(showFields) {
        try {
            // Update container visibility with fade effect
            editionVersionContainer.style.opacity = '0';
            editionVersionContainer.style.display = showFields ? 'block' : 'none';
            setTimeout(() => {
                if (editionVersionContainer.style.display === 'block') {
                    editionVersionContainer.style.opacity = '1';
                }
            }, 50);

            // Update edition radio buttons
            editionInputs.forEach(input => {
                if (input) {
                    input.required = showFields;
                    if (!showFields) {
                        input.checked = false;
                    }
                }
            });

            // Update version select
            if (versionSelect) {
                versionSelect.required = showFields;
                if (!showFields) {
                    versionSelect.selectedIndex = 0;
                }
            }

            debug(`Form fields updated - Experience: ${showFields ? 'Yes' : 'No'}`);
        } catch (error) {
            console.error('[Odoo Form Error]:', error);
            // Ensure form is still usable even if there's an error
            if (editionVersionContainer) {
                editionVersionContainer.style.display = showFields ? 'block' : 'none';
            }
        }
    }

    // Add smooth transition for container
    editionVersionContainer.style.transition = 'opacity 0.3s ease-in-out';

    // Add event listeners to radio buttons
    experienceRadios.forEach(radio => {
        radio.addEventListener('change', function(event) {
            const hasExperience = event.target.value === 'yes';
            debug(`Experience changed to: ${hasExperience ? 'Yes' : 'No'}`);
            updateFormFields(hasExperience);
        });
    });

    // Set initial state based on current selection
    const selectedExperience = form.querySelector('input[name="has_odoo_experience"]:checked');
    if (selectedExperience) {
        const hasExperience = selectedExperience.value === 'yes';
        debug(`Initializing form with experience: ${hasExperience ? 'Yes' : 'No'}`);
        updateFormFields(hasExperience);
    } else {
        debug('No experience option selected initially');
        updateFormFields(false);
    }

    debug('Form initialization complete');
});
