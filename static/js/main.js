document.addEventListener('DOMContentLoaded', function() {
    // Debug helper function
    function debug(message) {
        console.debug(`[Odoo Form]: ${message}`);
    }

    // Get the form and validate we're on the right page
    const form = document.querySelector('form[action="/get_recommendations"]');
    if (form) {
        // Recommendations form logic
        const editionVersionContainer = document.getElementById('edition-version-container');
        const experienceRadios = form.querySelectorAll('input[name="has_odoo_experience"]');
        const editionInputs = form.querySelectorAll('input[name="preferred_edition"]');
        const versionSelect = document.getElementById('current_version');

        if (editionVersionContainer && experienceRadios.length) {
            debug('Form elements found - initializing conditional logic');

            // Function to safely update form fields with error handling
            function updateFormFields(showFields) {
                try {
                    editionVersionContainer.style.opacity = '0';
                    editionVersionContainer.style.display = showFields ? 'block' : 'none';
                    setTimeout(() => {
                        if (editionVersionContainer.style.display === 'block') {
                            editionVersionContainer.style.opacity = '1';
                        }
                    }, 50);

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
                    if (editionVersionContainer) {
                        editionVersionContainer.style.display = showFields ? 'block' : 'none';
                    }
                }
            }

            editionVersionContainer.style.transition = 'opacity 0.3s ease-in-out';

            experienceRadios.forEach(radio => {
                radio.addEventListener('change', function(event) {
                    const hasExperience = event.target.value === 'yes';
                    debug(`Experience changed to: ${hasExperience ? 'Yes' : 'No'}`);
                    updateFormFields(hasExperience);
                });
            });

            const selectedExperience = form.querySelector('input[name="has_odoo_experience"]:checked');
            if (selectedExperience) {
                const hasExperience = selectedExperience.value === 'yes';
                debug(`Initializing form with experience: ${hasExperience ? 'Yes' : 'No'}`);
                updateFormFields(hasExperience);
            } else {
                debug('No experience option selected initially');
                updateFormFields(false);
            }
        }
    } else {
        debug('Not on recommendations form page - checking for auth forms');
        
        // Auth forms validation and enhancement
        const authForm = document.querySelector('form.needs-validation');
        if (authForm) {
            debug('Auth form found - initializing validation');

            // Password toggle functionality
            const setupPasswordToggle = (inputId, toggleId) => {
                const input = document.getElementById(inputId);
                const toggle = document.getElementById(toggleId);
                if (input && toggle) {
                    toggle.addEventListener('click', () => {
                        const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
                        input.setAttribute('type', type);
                        toggle.querySelector('i').classList.toggle('fa-eye');
                        toggle.querySelector('i').classList.toggle('fa-eye-slash');
                    });
                }
            };

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
                input.addEventListener('input', () => {
                    input.setCustomValidity('');
                });
            });
        }
    }

    debug('Form initialization complete');
});
