document.addEventListener('DOMContentLoaded', function() {
    const experienceRadios = document.getElementsByName('has_odoo_experience');
    const editionVersionContainer = document.getElementById('edition-version-container');
    
    experienceRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.value === 'yes') {
                editionVersionContainer.style.display = 'block';
            } else {
                editionVersionContainer.style.display = 'none';
            }
        });
    });
});
