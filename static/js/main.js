document.addEventListener('DOMContentLoaded', function() {
    // Debug helper function
    function debug(message, type = 'info') {
        const timestamp = new Date().toISOString();
        const prefix = `[Odoo Form ${timestamp}]:`;
        switch(type) {
            case 'error':
                console.error(prefix, message);
                break;
            case 'warn':
                console.warn(prefix, message);
                break;
            default:
                console.debug(prefix, message);
        }
    }

    // Progress tracking state
    const state = {
        loadedModules: 0,
        totalModules: 0,
        progressBar: null,
        progressContainer: null,
        currentProgress: null,
        totalModulesElement: null
    };

    // Initialize progress tracking
    function initializeProgress() {
        state.progressContainer = document.querySelector('.progress-container');
        state.progressBar = document.querySelector('.progress-bar');
        state.currentProgress = document.querySelector('.current-progress');
        state.totalModulesElement = document.querySelector('.total-modules');
        state.totalModules = document.querySelectorAll('.module-image.lazy').length;

        if (state.totalModules > 0 && state.progressContainer) {
            state.progressContainer.style.display = 'block';
            state.totalModulesElement.textContent = state.totalModules;
            updateProgress(0);
        }
    }

    // Update progress indicators
    function updateProgress(loadedCount) {
        if (!state.progressBar || !state.currentProgress) return;

        state.loadedModules = loadedCount;
        const percentage = (loadedCount / state.totalModules) * 100;
        
        state.progressBar.style.width = `${percentage}%`;
        state.progressBar.setAttribute('aria-valuenow', percentage);
        state.currentProgress.textContent = loadedCount;

        debug(`Progress updated: ${loadedCount}/${state.totalModules} (${percentage}%)`);

        if (loadedCount === state.totalModules) {
            setTimeout(() => {
                state.progressContainer.style.opacity = '0';
                setTimeout(() => {
                    state.progressContainer.style.display = 'none';
                }, 300);
            }, 500);
        }
    }

    // Handle recommendations form if it exists
    const recommendationsForm = document.querySelector('form[action="/get_recommendations"]');
    if (recommendationsForm) {
        debug('Recommendations form found - initializing');
        
        const editionVersionContainer = document.getElementById('edition-version-container');
        const experienceRadios = recommendationsForm.querySelectorAll('input[name="has_odoo_experience"]');
        
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

    // Handle module image loading
    const recommendationsContainer = document.getElementById('recommendations-container');
    if (recommendationsContainer) {
        debug('Initializing module loading tracking');
        initializeProgress();

        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    const moduleName = img.dataset.moduleName;
                    const spinner = img.closest('.module-image-container').querySelector('.module-loading-spinner');

                    if (!img.classList.contains('loaded')) {
                        debug(`Loading image for module: ${moduleName}`);
                        spinner.classList.add('active');

                        img.src = img.dataset.src;
                        img.onload = () => {
                            debug(`Successfully loaded image for: ${moduleName}`);
                            img.classList.add('loaded');
                            spinner.classList.remove('active');
                            updateProgress(state.loadedModules + 1);
                        };

                        img.onerror = () => {
                            debug(`Failed to load image for: ${moduleName}`, 'error');
                            handleImageError(img);
                            spinner.classList.remove('active');
                            updateProgress(state.loadedModules + 1);
                        };

                        observer.unobserve(img);
                    }
                }
            });
        });

        document.querySelectorAll('.module-image.lazy').forEach(img => {
            debug(`Setting up lazy loading for module: ${img.dataset.moduleName}`);
            imageObserver.observe(img);
        });
    }

    // Existing image error handling
    function handleImageError(img) {
        const moduleName = img.dataset.moduleName;
        const expectedPath = img.dataset.expectedPath;
        const currentPath = img.src;
        
        debug(`Image load failed for module: ${moduleName}`, 'error');
        debug(`Expected path: ${expectedPath}`, 'error');
        debug(`Current path: ${currentPath}`, 'error');
        
        if (currentPath !== '/static/images/default_module_icon.svg') {
            debug(`Falling back to default icon for: ${moduleName}`, 'warn');
            img.src = '/static/images/default_module_icon.svg';
            img.classList.add('loaded');
            
            const container = img.closest('.module-image-container');
            if (container) {
                container.classList.add('fallback-icon');
            }
        }
    }
    window.handleImageError = handleImageError;

    debug('Module loading initialization complete');
});