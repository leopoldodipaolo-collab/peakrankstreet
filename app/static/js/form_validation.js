// static/js/form_validation.js

document.addEventListener('DOMContentLoaded', function() {
    // Funzione generica di validazione Bootstrap
    (function () {
        'use strict'
        var forms = document.querySelectorAll('.needs-validation')
        Array.prototype.slice.call(forms)
            .forEach(function (form) {
                form.addEventListener('submit', function (event) {
                    let customValidationPassed = true;

                    // Controlli specifici per alcuni form prima del checkValidity()
                    if (form.id === 'createRouteForm') {
                        if (typeof validateMapOrGpx === 'function') {
                            customValidationPassed = validateMapOrGpx(); 
                        }
                    } else if (form.id === 'createChallengeForm') {
                        if (typeof validateDates === 'function') {
                            customValidationPassed = validateDates();
                        }
                    } else if (form.id === 'recordActivityForm') {
                        if (typeof validateChallengeOrRoute === 'function') {
                            customValidationPassed = validateChallengeOrRoute();
                        }
                    }
                    
                    if (!form.checkValidity() || !customValidationPassed) {
                        event.preventDefault()
                        event.stopPropagation()
                        // Se la validazione fallisce, assicurati che i pulsanti/spinner siano nello stato corretto (visibile, abilitato)
                        if (form.id === 'saveRouteForm') {
                            document.getElementById('saveRouteButton').disabled = false;
                            document.getElementById('saveRouteSpinner').style.display = 'none';
                        } else if (form.id === 'recordActivityForm') {
                            document.getElementById('recordActivityButton').disabled = false;
                            document.getElementById('recordActivitySpinner').style.display = 'none';
                        }
                    }
                    form.classList.add('was-validated')
                }, false)
            })
    })();

    // Funzione di validazione specifica per new_route.html (percorso disegnato o GPX)
    window.validateMapOrGpx = function() {
        const coordinatesInput = document.getElementById('coordinates');
        const gpxFileInput = document.getElementById('gpx_file');
        
        if (!coordinatesInput || !gpxFileInput) return true;

        let isValid = true;
        if (coordinatesInput.value || gpxFileInput.files.length > 0) {
            coordinatesInput.setCustomValidity("");
            gpxFileInput.setCustomValidity("");
        } else {
            coordinatesInput.setCustomValidity("Devi disegnare un percorso o caricare un file GPX.");
            gpxFileInput.setCustomValidity("Devi disegnare un percorso o caricare un file GPX.");
            isValid = false;
        }
        return isValid;
    };

    // Funzione di validazione specifica per create_challenge.html (date)
    window.validateDates = function() {
        const startDateInput = document.getElementById('start_date');
        const endDateInput = document.getElementById('end_date');
        
        if (!startDateInput || !endDateInput) return true;

        const startDate = new Date(startDateInput.value);
        const endDate = new Date(endDateInput.value);
        let isValid = true;

        if (!startDateInput.value) {
            startDateInput.setCustomValidity("La data di inizio è obbligatoria.");
            isValid = false;
        } else {
            startDateInput.setCustomValidity("");
        }

        if (!endDateInput.value) {
            endDateInput.setCustomValidity("La data di fine è obbligatoria.");
            isValid = false;
        } else {
            endDateInput.setCustomValidity("");
        }

        if (startDateInput.value && endDateInput.value && startDate >= endDate) {
            endDateInput.setCustomValidity("La data di fine deve essere successiva alla data di inizio.");
            isValid = false;
        } else if (endDateInput.value) {
            endDateInput.setCustomValidity("");
        }
        return isValid;
    };

    // Funzione di validazione specifica per record_activity.html (sfida o percorso selezionato)
    window.validateChallengeOrRoute = function() {
        const challengeSelect = document.getElementById('challenge_id');
        const routeSelect = document.getElementById('route_id');

        if (!challengeSelect || !routeSelect) return true;

        let isValid = true;
        if (challengeSelect.value || routeSelect.value) {
            challengeSelect.setCustomValidity("");
            routeSelect.setCustomValidity("");
        } else {
            challengeSelect.setCustomValidity("Devi selezionare una sfida o un percorso.");
            routeSelect.setCustomValidity("Devi selezionare una sfida o un percorso.");
            isValid = false;
        }
        return isValid;
    };

    // Aggiungi listener per le date nel form di creazione sfida
    const createChallengeForm = document.getElementById('createChallengeForm');
    if (createChallengeForm) {
        const startDateInput = document.getElementById('start_date');
        const endDateInput = document.getElementById('end_date');
        startDateInput.addEventListener('change', window.validateDates);
        endDateInput.addEventListener('change', window.validateDates);
    }
});