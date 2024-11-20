document.addEventListener('DOMContentLoaded', function() {
    // Debug helper function
    function debug(message) {
        console.debug(`[Odoo Form]: ${message}`);
    }

    // Get the form elements
    const recommendationsForm = document.querySelector('form[action="/get_recommendations"]');
    const authForm = document.querySelector('form.needs-validation');

    // Handle recommendations form if it exists
    if (recommendationsForm) {
        debug('Recommendations form found - initializing');
        
        const editionVersionContainer = document.getElementById('edition-version-container');
        const experienceRadios = recommendationsForm.querySelectorAll('input[name="has_odoo_experience"]');
        const submitButton = recommendationsForm.querySelector('button[type="submit"]');
        
        // Progress tracking variables
        let progress = 0;
        let progressInterval;
        
        // Function to update button progress
        function updateProgress() {
            progress += Math.random() * 5; // Smoother increment
            if (progress > 90) {
                progress = 90;  // Cap at 90% until complete
                clearInterval(progressInterval);
            }
            const progressText = submitButton.querySelector('.progress-text');
            const progressBar = submitButton.querySelector('.progress-bar');
            if (progressText && progressBar) {
                progressText.textContent = `${Math.round(progress)}%`;
                progressBar.style.width = `${progress}%`;
            }
        }

        // Function to reset button progress
        function resetProgress() {
            progress = 0;
            clearInterval(progressInterval);
            submitButton.classList.remove('submitting');
            const progressText = submitButton.querySelector('.progress-text');
            const progressBar = submitButton.querySelector('.progress-bar');
            const buttonContent = submitButton.querySelector('.button-content');
            if (progressText) progressText.textContent = '';
            if (progressBar) progressBar.style.width = '0%';
            if (buttonContent) buttonContent.style.opacity = '1';
            submitButton.disabled = false;
        }

        // Handle form submission and progress animation
        if (recommendationsForm && submitButton) {
            recommendationsForm.addEventListener('submit', function(event) {
                if (!this.checkValidity()) {
                    event.preventDefault();
                    return;
                }

                submitButton.classList.add('submitting');
                submitButton.disabled = true;
                const buttonContent = submitButton.querySelector('.button-content');
                const progressText = submitButton.querySelector('.progress-text');
                const progressBar = submitButton.querySelector('.progress-bar');
                
                if (buttonContent) buttonContent.style.opacity = '0.7';
                if (progressText) progressText.textContent = '0%';
                if (progressBar) progressBar.style.width = '0%';
                
                progress = 0;
                progressInterval = setInterval(updateProgress, 100);
            });
        }

        // Handle Odoo experience form logic
        if (editionVersionContainer && experienceRadios.length) {
            debug('Form elements found - initializing conditional logic');
            
            const editionInputs = recommendationsForm.querySelectorAll('input[name="preferred_edition"]');
            const versionSelect = document.getElementById('current_version');

            function updateFormFields(showFields) {
                try {
                    if (editionVersionContainer) {
                        editionVersionContainer.style.opacity = '0';
                        editionVersionContainer.style.display = showFields ? 'block' : 'none';
                        setTimeout(() => {
                            if (editionVersionContainer.style.display === 'block') {
                                editionVersionContainer.style.opacity = '1';
                            }
                        }, 50);
                    }

                    editionInputs.forEach(input => {
                        if (input) {
                            input.required = showFields;
                            if (!showFields) input.checked = false;
                        }
                    });

                    if (versionSelect) {
                        versionSelect.required = showFields;
                        if (!showFields) versionSelect.selectedIndex = 0;
                    }

                    debug(`Form fields updated - Experience: ${showFields ? 'Yes' : 'No'}`);
                } catch (error) {
                    console.error('[Odoo Form Error]:', error);
                }
            }

            if (editionVersionContainer) {
                editionVersionContainer.style.transition = 'opacity 0.3s ease-in-out';
            }

            experienceRadios.forEach(radio => {
                radio.addEventListener('change', function(event) {
                    updateFormFields(event.target.value === 'yes');
                });
            });

            const selectedExperience = recommendationsForm.querySelector('input[name="has_odoo_experience"]:checked');
            if (selectedExperience) {
                updateFormFields(selectedExperience.value === 'yes');
            } else {
                updateFormFields(false);
            }
        }
    } else {
        debug('Not on recommendations form page - checking for auth forms');
        
        // Handle auth forms if they exist
        if (authForm) {
            debug('Auth form found - initializing validation');
            authForm.addEventListener('submit', function(event) {
                if (!this.checkValidity()) {
                    event.preventDefault();
                    event.stopPropagation();
                }
                this.classList.add('was-validated');
            });
        }
    }

    debug('Form initialization complete');
});