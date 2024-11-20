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
            progress += Math.random() * 15;
            if (progress > 90) {
                progress = 90;  // Cap at 90% until complete
                clearInterval(progressInterval);
            }
            submitButton.querySelector('.progress-text').textContent = `${Math.round(progress)}%`;
            submitButton.querySelector('.progress-bar').style.width = `${progress}%`;
        }

        // Function to reset button progress
        function resetProgress() {
            progress = 0;
            clearInterval(progressInterval);
            submitButton.querySelector('.progress-text').textContent = '';
            submitButton.querySelector('.progress-bar').style.width = '0%';
            submitButton.querySelector('.button-content').style.opacity = '1';
            submitButton.disabled = false;
        }
        
        if (editionVersionContainer && experienceRadios.length) {
            debug('Form elements found - initializing conditional logic');
            
            const editionInputs = recommendationsForm.querySelectorAll('input[name="preferred_edition"]');
            const versionSelect = document.getElementById('current_version');

            // Function to safely update form fields with error handling
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
                            if (!showFields) {
                                input.checked = false;
                            }
                        }
                    });

                    if (versionSelect) {
                        versionSelect.required = showFields;
                        if (!showFields) {
                            versionSelect.selectedIndex = 0;
                        }
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
                    const hasExperience = event.target.value === 'yes';
                    debug(`Experience changed to: ${hasExperience ? 'Yes' : 'No'}`);
                    updateFormFields(hasExperience);
                });
            });

            const selectedExperience = recommendationsForm.querySelector('input[name="has_odoo_experience"]:checked');
            if (selectedExperience) {
                const hasExperience = selectedExperience.value === 'yes';
                debug(`Initializing form with experience: ${hasExperience ? 'Yes' : 'No'}`);
                updateFormFields(hasExperience);
            } else {
                debug('No experience option selected initially');
                updateFormFields(false);
            }
        }

        // Handle form submission and progress animation
        if (recommendationsForm && submitButton) {
            recommendationsForm.addEventListener('submit', function(event) {
                if (!this.checkValidity()) {
                    event.preventDefault();
                    return;
                }

                // Start progress animation
                submitButton.disabled = true;
                submitButton.querySelector('.button-content').style.opacity = '0.7';
                progress = 0;
                progressInterval = setInterval(updateProgress, 800);

                // Handle actual form submission
                submitButton.querySelector('.progress-text').textContent = '0%';
                debug('Form submission started - initializing progress tracking');
            });
        }
    } else {
        debug('Not on recommendations form page - checking for auth forms');
        
        // Handle auth forms if they exist
        if (authForm) {
            debug('Auth form found - initializing validation');

            // Password toggle functionality
            function setupPasswordToggle(inputId, toggleId) {
                const input = document.getElementById(inputId);
                const toggle = document.getElementById(toggleId);
                
                if (input && toggle) {
                    toggle.addEventListener('click', () => {
                        const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
                        input.setAttribute('type', type);
                        const icon = toggle.querySelector('i');
                        if (icon) {
                            icon.classList.toggle('fa-eye');
                            icon.classList.toggle('fa-eye-slash');
                        }
                    });
                }
            }

            setupPasswordToggle('password', 'togglePassword');
            setupPasswordToggle('confirm_password', 'toggleConfirmPassword');

            // Form validation
            authForm.addEventListener('submit', function(event) {
                if (!this.checkValidity()) {
                    event.preventDefault();
                    event.stopPropagation();
                }

                // Additional password match validation for signup form
                const password = document.getElementById('password');
                const confirmPassword = document.getElementById('confirm_password');
                if (password && confirmPassword && password.value !== confirmPassword.value) {
                    confirmPassword.setCustomValidity("Passwords don't match");
                    event.preventDefault();
                } else if (confirmPassword) {
                    confirmPassword.setCustomValidity('');
                }

                this.classList.add('was-validated');
            });

            // Clear custom validity on input
            const inputs = authForm.querySelectorAll('input');
            inputs.forEach(input => {
                if (input) {
                    input.addEventListener('input', () => {
                        input.setCustomValidity('');
                    });
                }
            });
        }
    }

    debug('Form initialization complete');
});
