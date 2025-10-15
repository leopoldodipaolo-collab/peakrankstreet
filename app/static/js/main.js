// =======================================================
// FUNZIONI GLOBALI
// =======================================================

// Funzione per visualizzare i dettagli del percorso SOTTO LA MAPPA
function displayRouteDetails(routeProps) { 
    console.log('Display details for:', routeProps.name);
    
    const detailsCard = document.getElementById('selected-route-details');
    if (!detailsCard) {
        console.error('Details card not found!');
        return;
    }
    
    // Popola i dettagli
    document.getElementById('detail-route-name').textContent = routeProps.name;
    document.getElementById('detail-route-description').textContent = routeProps.description || 'Nessuna descrizione.';
    
    let createdByHtml = `Creato il: ${routeProps.created_at} da <a href="${userProfileUrlBase.replace('12345', routeProps.created_by_id)}">${routeProps.created_by_username}</a>`;
    document.getElementById('detail-route-meta').innerHTML = `${createdByHtml}<br>Distanza: ${routeProps.distance_km ? routeProps.distance_km.toFixed(2) + ' km' : 'N/D'}`;
    
    // Link ai dettagli completi
    document.getElementById('detail-route-link').href = routeDetailUrlBase.replace('12345', routeProps.id);
    document.getElementById('record-activity-link').href = `/activities/record?route_id=${routeProps.id}`;
    document.getElementById('create-challenge-link').href = `/challenges/new?route_id=${routeProps.id}`;

    // Gestione King/Queen
    if (routeProps.king_queen && routeProps.king_queen.username) {
        document.getElementById('kq-username').innerHTML = `<a href="${userProfileUrlBase.replace('12345', routeProps.king_queen.user_id)}" class="user-link text-dark">${routeProps.king_queen.username}</a>`;
        document.getElementById('kq-duration').textContent = formatDuration(routeProps.king_queen.duration);
        document.getElementById('kq-activity-link').href = activityDetailUrlBase.replace('12345', routeProps.king_queen.activity_id);
        document.getElementById('kq-created-at').textContent = `Registrato il: ${routeProps.king_queen.created_at}`;
        document.getElementById('detail-king-queen').style.display = 'block';
    } else {
        document.getElementById('detail-king-queen').style.display = 'none';
    }

    // Gestione Top 5 Times
    const top5List = document.getElementById('top-5-list');
    top5List.innerHTML = '';
    if (routeProps.top_5_activities && routeProps.top_5_activities.length > 0) {
        routeProps.top_5_activities.forEach((activity, index) => {
            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center py-2';
            li.innerHTML = `
                <span class="badge bg-primary rounded-pill me-2">${index + 1}</span>
                <img src="${profilePicsBaseUrl}${activity.profile_image}" class="rounded-circle me-2 profile-image-small" alt="Avatar" style="width: 24px; height: 24px;">
                <a href="${userProfileUrlBase.replace('12345', activity.user_id)}" class="user-link text-primary flex-grow-1" style="font-size: 0.9em;">${activity.username}</a>
                <span class="badge bg-info rounded-pill">${formatDuration(activity.duration)}</span>
                <a href="${activityDetailUrlBase.replace('12345', activity.activity_id)}" class="btn btn-sm btn-link p-0 ms-2" style="font-size:0.7em;">(Dettagli)</a>`;
            top5List.appendChild(li);
        });
        document.getElementById('detail-top-5-times').style.display = 'block';
    } else {
        document.getElementById('detail-top-5-times').style.display = 'none';
    }

    // Mostra la card dei dettagli
    detailsCard.style.display = 'block';
    
    // Nascondi le istruzioni della mappa
    const mapInstructions = document.getElementById('map-instructions');
    if (mapInstructions) {
        mapInstructions.style.display = 'none';
    }
    
    // Scroll smooth ai dettagli
    setTimeout(() => {
        detailsCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 100);
}

// Funzione per nascondere i dettagli
function hideRouteDetails() {
    const detailsCard = document.getElementById('selected-route-details');
    if (detailsCard) {
        detailsCard.style.display = 'none';
    }
    
    // Pulisci il percorso dalla mappa
    if (selectedRouteLayer) {
        selectedRouteLayer.clearLayers();
    }
    
    // Mostra di nuovo le istruzioni
    const mapInstructions = document.getElementById('map-instructions');
    if (mapInstructions) {
        mapInstructions.style.display = 'block';
    }
}

// Funzione globale per mostrare i dettagli dal popup del marker
window.showRouteDetailsFromMarker = function(routeId) {
    console.log('Mostra dettagli per route:', routeId);
    
    try {
        // Chiudi tutti i popup aperti
        if (typeof mainMap !== 'undefined' && mainMap && typeof mainMap.closePopup === 'function') {
            mainMap.closePopup();
        }
        
        // CERCA IL PERCORSO NEI DATI GIA' CARICATI
        let foundRoute = null;
        
        if (window.loadedRoutes && Array.isArray(window.loadedRoutes)) {
            foundRoute = window.loadedRoutes.find(route => route.id == routeId);
        }
        
        if (foundRoute) {
            console.log('Percorso trovato in cache:', foundRoute.name);
            
            // Mostra il percorso sulla mappa
            if (selectedRouteLayer) {
                selectedRouteLayer.clearLayers();
                selectedRouteLayer.addData(foundRoute.coordinates);
            }
            
            // Mostra i dettagli SOTTO LA MAPPA
            displayRouteDetails(foundRoute);
        } else {
            console.error('Percorso non trovato nei dati caricati:', routeId);
        }
        
    } catch (error) {
        console.error('Errore in showRouteDetailsFromMarker:', error);
    }
};

// Funzione helper per formattare la durata da secondi a HH:MM:SS
function formatDuration(seconds) {
    if (typeof seconds !== 'number' || isNaN(seconds)) return 'N/D';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return [h, m, s]
        .map(v => String(v).padStart(2, '0'))
        .join(":");
}

// Funzione helper per formattare la durata in modo compatto
function formatDurationCompact(seconds) {
    if (!seconds) return 'N/A';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return hours > 0 ? `${hours}h${minutes}m` : `${minutes}m`;
}

// =======================================================
// VARIABILI GLOBALI
// =======================================================

let mainMap, markers, osmLayer, topoLayer;
let userProfileUrlBase, routeDetailUrlBase, activityDetailUrlBase, profilePicsBaseUrl, mapDataApiUrl, userInitialCity;
let selectedRouteLayer;

// =======================================================
// DEFINIZIONE ICONE PERSONALIZZATE
// =======================================================

const L_Icon = L.Icon.extend({
    options: {
        iconSize:     [32, 32],
        iconAnchor:   [16, 32],
        popupAnchor:  [0, -32]
    }
});

const runIcon = new L_Icon({iconUrl: '/static/icons/runner.png'});
const bikeIcon = new L_Icon({iconUrl: '/static/icons/bicycle.png'});
const hikeIcon = new L_Icon({iconUrl: '/static/icons/hiking.png'});
const defaultIcon = new L_Icon({iconUrl: '/static/icons/default.png'});

const activityIcons = {
    'Corsa': runIcon,
    'Bici': bikeIcon,
    'Hike': hikeIcon
};

// =======================================================
// FUNZIONI PRINCIPALI
// =======================================================

// Funzione di inizializzazione mappa
function initializeMap() {
    console.log('Inizializzazione mappa...');
    
    if (!mainMap) {
        mainMap = L.map('mainMap', {
            center: [42.3498, 13.3995],
            zoom: 13,
            zoomControl: true,
            attributionControl: true,
            preferCanvas: true,
            fadeAnimation: false,
            markerZoomAnimation: false
        });

        // Aggiungi layer base
        osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { 
            attribution: '&copy; OpenStreetMap' 
        }).addTo(mainMap);
        
        topoLayer = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', { 
            attribution: '&copy; OpenTopoMap' 
        });

        // Inizializza cluster marker
        markers = L.markerClusterGroup({
            chunkedLoading: true,
            maxClusterRadius: 50,
            showCoverageOnHover: false,
            zoomToBoundsOnClick: false
        });
        mainMap.addLayer(markers);

        // Layer per il percorso selezionato
        selectedRouteLayer = L.geoJSON(null, { 
            style: { color: '#007bff', weight: 6, opacity: 1 },
            interactive: false
        }).addTo(mainMap);

        // Controllo layer
        L.control.layers(
            { "Stradale": osmLayer, "Topografica": topoLayer }, 
            { "Percorsi": markers }
        ).addTo(mainMap);

        // Gestione click sulla mappa (per deselezionare)
        mainMap.on('click', function(e) {
            console.log('Mappa cliccata - deseleziona');
            mainMap.closePopup();
            
            // Nascondi i dettagli del percorso
            hideRouteDetails();
        });

        setTimeout(() => {
            if (mainMap) {
                mainMap.invalidateSize();
            }
        }, 100);
    }
    
    return mainMap;
}

// Funzione principale di caricamento dati
// Funzione principale di caricamento dati
window.loadMapAndData = function(lat, lon, zoom = 13, city = null) {
    console.log('Caricamento mappa per:', lat, lon, city);
    
    // Assicurati che la mappa sia inizializzata
    if (!mainMap) {
        console.error('Mappa non inizializzata!');
        return;
    }
    
    mainMap.setView([lat, lon], zoom);
    
    // Pulisci i marker esistenti in modo sicuro
    mainMap.eachLayer(layer => { 
        if (layer.options && layer.options.isCitySearchMarker) {
            mainMap.removeLayer(layer);
        }
    });
    
    // Aggiungi marker della città se specificata
    if (city) {
        L.marker([lat, lon], { isCitySearchMarker: true })
            .addTo(mainMap)
            .bindPopup(`<b>${city}</b>`)
            .openPopup();
    }

    // Mostra stati di caricamento
    const loadingMsg = `<p class="text-center text-muted p-3">Caricamento...</p>`;
    const leaderboardLoadingMsg = `<li class="list-group-item text-center text-muted">Caricamento...</li>`;
    
    const availableRoutesListDiv = document.getElementById('available-routes-list');
    const recentChallengesListDiv = document.getElementById('recent-challenges-list');
    const recentActivitiesListDiv = document.getElementById('recent-activities-list');
    
    if (availableRoutesListDiv) availableRoutesListDiv.innerHTML = loadingMsg;
    if (recentChallengesListDiv) recentChallengesListDiv.innerHTML = loadingMsg;
    if (recentActivitiesListDiv) recentActivitiesListDiv.innerHTML = loadingMsg;
    
    const distanceList = document.querySelector('#top-distance-list');
    const creatorsList = document.querySelector('#top-creators-list');
    if (distanceList) distanceList.innerHTML = leaderboardLoadingMsg;
    if (creatorsList) creatorsList.innerHTML = leaderboardLoadingMsg;

    const activityTypeFilter = document.querySelector('#activityTypeFilter .btn.active');
    const activityType = activityTypeFilter ? activityTypeFilter.dataset.type : 'all';

    // URL dell'API con parametri
    const apiUrl = `${mapDataApiUrl}?lat=${lat}&lon=${lon}&radius_km=50&activity_type=${activityType}`;
    console.log('Chiamando API:', apiUrl);

    fetch(apiUrl)
        .then(response => {
            // Controlla se la risposta è JSON
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                throw new Error('La risposta non è JSON. Probabilmente un errore del server.');
            }
            
            if (!response.ok) {
                throw new Error(`Errore HTTP: ${response.status} ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Dati ricevuti:', data.routes ? data.routes.length : 0, 'percorsi');
            
            // SALVA I PERCORSI IN VARIABILE GLOBALE PER RIUTILIZZO
            window.loadedRoutes = data.routes || [];
            
            // PULISCI I MARKER IN MODO SICURO
            if (markers) {
                markers.clearLayers();
            }
            
            // Aggiungi i nuovi marker
            if (data.routes && Array.isArray(data.routes)) {
                data.routes.forEach(r => {
                    if (!r.coordinates || !r.coordinates.geometry || !r.coordinates.geometry.coordinates[0]) {
                        console.warn('Percorso senza coordinate valide:', r.id);
                        return;
                    }
                    
                    const startPoint = r.coordinates.geometry.coordinates[0];
                    const selectedIcon = activityIcons[r.activity_type] || defaultIcon;

                    // CREA UN SOLO MARKER
                    const marker = L.marker([startPoint[1], startPoint[0]], { 
                        icon: selectedIcon,
                        title: r.name
                    });
                    
                    // Contenuto del popup SEMPLICE
                    let popupContent = `
                        <div style="min-width: 200px; text-align: center;">
                            <h6 style="margin-bottom: 8px; font-weight: bold;">${r.name}</h6>
                            <p style="margin-bottom: 8px; font-size: 0.9em;">Distanza: ${r.distance_km ? r.distance_km.toFixed(2) + ' km' : 'N/D'}</p>
                            ${r.king_queen ? `<span class="badge bg-warning text-dark" style="font-size: 0.8em;"><i class="bi bi-trophy-fill"></i> ${r.king_queen.username}</span><br><br>` : ''}
                            <button class="btn btn-sm btn-success" onclick="window.showRouteDetailsFromMarker(${r.id})" style="width: 100%;">
                                <i class="bi bi-info-circle"></i> Vedi Dettagli
                            </button>
                        </div>
                    `;
                    
                    marker.bindPopup(popupContent, {
                        maxWidth: 300,
                        className: 'route-popup'
                    });

                    // GESTIONE CLICK DIRETTO SUL MARKER
                    marker.on('click', function(e) {
                        console.log('Marker cliccato direttamente:', r.name);
                        
                        // IMPORTANTE: Ferma la propagazione per evitare conflitti
                        L.DomEvent.stopPropagation(e);
                        
                        // Chiudi il popup se aperto
                        this.closePopup();
                        
                        // Aspetta un millisecondo per evitare conflitti
                        setTimeout(() => {
                            // Mostra il percorso sulla mappa
                            if (selectedRouteLayer) {
                                selectedRouteLayer.clearLayers();
                                selectedRouteLayer.addData(r.coordinates);
                            }
                            
                            // Mostra i dettagli SOTTO LA MAPPA
                            displayRouteDetails(r);
                        }, 10);
                    });

                    // AGGIUNGI IL MARKER UNA VOLTA SOLA
                    markers.addLayer(marker);
                });
            }

            // Adatta la vista della mappa
            if (markers.getLayers().length > 0) {
                setTimeout(() => {
                    mainMap.fitBounds(markers.getBounds(), { 
                        padding: [50, 50],
                        maxZoom: 15 
                    });
                }, 100);
            }

            // Popola le liste
            if (data.routes) populateAvailableRoutes(data.routes);
            if (data.challenges) populateRecentChallenges(data.challenges);
            if (data.recent_activities) populateRecentActivities(data.recent_activities);
            if (data.local_leaderboards) populateLocalLeaderboards(data.local_leaderboards);

        })
        .catch(error => {
            console.error('Errore nel caricamento dati:', error);
            const errorMsg = `
                <div class="text-center p-4">
                    <i class="bi bi-exclamation-triangle text-danger" style="font-size: 2rem;"></i>
                    <h5 class="text-danger mt-2">Errore di caricamento</h5>
                    <p class="text-muted">${error.message}</p>
                    <small class="text-muted">Controlla la connessione e riprova.</small>
                </div>
            `;
            
            const availableRoutesListDiv = document.getElementById('available-routes-list');
            const recentChallengesListDiv = document.getElementById('recent-challenges-list');
            const recentActivitiesListDiv = document.getElementById('recent-activities-list');
            
            if (availableRoutesListDiv) availableRoutesListDiv.innerHTML = errorMsg;
            if (recentChallengesListDiv) recentChallengesListDiv.innerHTML = errorMsg;
            if (recentActivitiesListDiv) recentActivitiesListDiv.innerHTML = errorMsg;
            
            // Mostra anche nelle classifiche
            const distanceList = document.querySelector('#top-distance-list');
            const creatorsList = document.querySelector('#top-creators-list');
            if (distanceList) distanceList.innerHTML = '<li class="list-group-item text-center text-muted">Errore di caricamento</li>';
            if (creatorsList) creatorsList.innerHTML = '<li class="list-group-item text-center text-muted">Errore di caricamento</li>';
        })
        .finally(() => {
            // Riabilita il pulsante di ricerca
            const searchButton = document.getElementById('searchCityButton');
            const searchSpinner = document.getElementById('citySearchSpinner');
            if (searchButton) searchButton.disabled = false;
            if (searchSpinner) searchSpinner.style.display = 'none';
        });

    // Carica percorsi classici solo se l'elemento esiste
    const userInitialCityElement = document.getElementById('user-initial-city');
    if (userInitialCityElement) {
        setTimeout(() => {
            const userCity = userInitialCityElement.textContent;
            const defaultCity = "L'Aquila";
            loadClassicRoutes(userCity || defaultCity);
        }, 1500);
    }
};

// =======================================================
// FUNZIONI PER POPOLARE LE LISTE
// =======================================================

function populateAvailableRoutes(routes) {
    const availableRoutesListDiv = document.getElementById('available-routes-list');
    if (!availableRoutesListDiv) return;
    
    availableRoutesListDiv.innerHTML = '';
    if (routes && routes.length > 0) {
        routes.forEach(route => {
            const routeHtml = `
                <a href="${routeDetailUrlBase.replace('12345', route.id)}" class="list-group-item list-group-item-action">
                    <div class="d-flex w-100 justify-content-between align-items-center">
                        <h5 class="mb-1 text-success">${route.name}</h5>
                        <small class="text-muted">ID: ${route.id}</small>
                        ${route.king_queen ? `<span class="badge bg-warning ms-2"><i class="bi bi-trophy-fill"></i> K/Q</span>` : ''}
                    </div>
                    <p class="mb-1">${route.description || "Nessuna descrizione."}</p>
                    <small class="text-muted">Creato da: <a href="${userProfileUrlBase.replace('12345', route.created_by_id)}" class="user-link">${route.created_by_username}</a> il ${route.created_at}</small><br>
                    ${route.distance_km ? `<small class="text-muted">Distanza: ${route.distance_km.toFixed(2)} km</small>` : ''}
                    <div class="route-actions mt-2">
                        <a href="${routeDetailUrlBase.replace('12345', route.id)}" class="btn btn-sm btn-outline-success">Dettagli</a>
                    </div>
                </a>
            `;
            availableRoutesListDiv.innerHTML += routeHtml;
        });
    } else {
        availableRoutesListDiv.innerHTML = `<p class="text-center text-muted p-3">Nessun percorso disponibile in quest'area. <a href="/routes/new">Creane uno!</a></p>`;
    }
}

function populateRecentChallenges(challenges) {
    const recentChallengesListDiv = document.getElementById('recent-challenges-list');
    if (!recentChallengesListDiv) return;
    
    recentChallengesListDiv.innerHTML = '';
    if (challenges && challenges.length > 0) {
        challenges.forEach(challenge => {
            const participateUrl = `/activities/record?challenge_id=${challenge.id}`;
            const leaderboardUrl = `/challenges/${challenge.id}/leaderboard`;
            recentChallengesListDiv.innerHTML += `
                <div class="list-group-item d-flex flex-column flex-md-row justify-content-between align-items-start align-items-md-center">
                    <div class="flex-grow-1 mb-2 mb-md-0">
                        <h5>${challenge.name}</h5>
                        <p class="mb-1">Su: <a href="${routeDetailUrlBase.replace('12345', challenge.route_id)}" class="text-success">${challenge.route_name}</a></p>
                        <small class="text-muted">Dal ${challenge.start_date} al ${challenge.end_date}</small>
                    </div>
                    <div class="ms-md-auto text-end">
                        ${challenge.is_active ? `<a href="${participateUrl}" class="btn btn-primary btn-sm me-2">Partecipa</a>` : ''}
                        <a href="${leaderboardUrl}" class="btn btn-success btn-sm">Classifica</a>
                    </div>
                </div>`;
        });
    } else {
        recentChallengesListDiv.innerHTML = `<p class="text-center text-muted p-3">Nessuna sfida attiva trovata. <a href="/challenges/new">Lancia la prima!</a></p>`;
    }
}

function populateRecentActivities(activities) {
    const recentActivitiesListDiv = document.getElementById('recent-activities-list');
    if (!recentActivitiesListDiv) return;
    
    recentActivitiesListDiv.innerHTML = '';
    if (activities && activities.length > 0) {
        activities.forEach(activity => {
            const likeButtonClass = activity.user_has_liked ? 'btn-danger' : 'btn-outline-danger';
            const isAuthenticated = document.querySelector('#navbarDropdownMenuLink') !== null;
            const disabledAttribute = isAuthenticated ? '' : 'disabled';
            
            const activityHtml = `
                <div class="list-group-item list-group-item-action activity-feed-item">
                    <p class="mb-1">
                        <img src="${profilePicsBaseUrl}${activity.user_profile_image}" class="rounded-circle me-2 profile-image-small" alt="Avatar">
                        <a href="${userProfileUrlBase.replace('12345', activity.user_id)}" class="user-link">${activity.username}</a>
                        ha completato
                        <strong><a href="${routeDetailUrlBase.replace('12345', activity.route_id)}" class="text-decoration-none text-success">${activity.route_name}</a></strong>.
                    </p>
                    <p class="small text-muted mb-1">
                        Distanza: <strong>${activity.distance.toFixed(2)} km</strong> |
                        Tempo: <strong>${formatDuration(activity.duration)}</strong>
                    </p>
                    
                    <div class="d-flex justify-content-between align-items-center mt-2">
                        <a href="${activityDetailUrlBase.replace('12345', activity.id)}" class="btn btn-sm btn-outline-primary">Dettagli</a>
                        
                        <button class="btn btn-sm like-activity-button ${likeButtonClass}" data-activity-id="${activity.id}" ${disabledAttribute}>
                            <i class="bi bi-heart-fill"></i>
                            <span class="like-count ms-1">${activity.like_count}</span>
                        </button>
                    </div>

                    <small class="text-muted d-block text-end mt-2">${activity.created_at}</small>
                </div>
            `;
            recentActivitiesListDiv.innerHTML += activityHtml;
        });
    } else {
        recentActivitiesListDiv.innerHTML = `<p class="text-center text-muted p-3">Nessuna attività recente in quest'area. <a href="/activities/record">Registra la tua!</a></p>`;
    }
}

function populateLocalLeaderboards(leaderboards) {
    const distanceList = document.querySelector('#top-distance-list');
    const creatorsList = document.querySelector('#top-creators-list');
    if (!distanceList || !creatorsList) return;

    distanceList.innerHTML = '';
    if (leaderboards && leaderboards.distance && leaderboards.distance.length > 0) {
        leaderboards.distance.forEach((entry, index) => {
            distanceList.innerHTML += `
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    <span>
                        <span class="badge bg-secondary rounded-pill me-2">${index + 1}</span>
                        <img src="${profilePicsBaseUrl}${entry.profile_image}" class="rounded-circle me-2 profile-image-small" alt="Avatar">
                        <a href="${userProfileUrlBase.replace('12345', entry.id)}">${entry.username}</a>
                    </span>
                    <span class="badge bg-success rounded-pill">${entry.total_distance.toFixed(2)} km</span>
                </li>`;
        });
    } else {
        distanceList.innerHTML = '<li class="list-group-item text-center text-muted">Nessun dato per l\'area.</li>';
    }

    creatorsList.innerHTML = '';
    if (leaderboards && leaderboards.creators && leaderboards.creators.length > 0) {
        leaderboards.creators.forEach((entry, index) => {
            creatorsList.innerHTML += `
                <li class="list-group-item d-flex justify-content-between align-items-center">
                     <span>
                        <span class="badge bg-secondary rounded-pill me-2">${index + 1}</span>
                        <img src="${profilePicsBaseUrl}${entry.profile_image}" class="rounded-circle me-2 profile-image-small" alt="Avatar">
                        <a href="${userProfileUrlBase.replace('12345', entry.id)}">${entry.username}</a>
                    </span>
                    <span class="badge bg-success rounded-pill">${entry.total_routes_created} percorsi</span>
                </li>`;
        });
    } else {
        creatorsList.innerHTML = '<li class="list-group-item text-center text-muted">Nessun dato per l\'area.</li>';
    }
}

// =======================================================
// PERCORSI CLASSICI
// =======================================================

// Funzione per caricare e visualizzare i percorsi classici
function loadClassicRoutes(city) {
    console.log('loadClassicRoutes chiamata per città:', city);
    
    if (!city || city.trim() === '') {
        const section = document.getElementById('classic-routes-section');
        if (section) section.style.display = 'none';
        return;
    }

    const section = document.getElementById('classic-routes-section');
    const container = document.getElementById('classic-routes-container');
    const noRoutes = document.getElementById('no-classic-routes');
    
    if (!section || !container) {
        console.error('Elementi HTML non trovati!');
        return;
    }
    
    // Rendi visibile la sezione
    section.style.display = 'block';
    
    // Aggiorna il titolo della città
    const cityTitle = document.getElementById('classic-routes-city');
    if (cityTitle) {
        cityTitle.textContent = city;
    }
    
    // Mostra loading
    container.innerHTML = '<div class="col-12 text-center"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Caricamento...</span></div><p class="mt-2 text-muted">Caricamento percorsi classici...</p></div>';

    fetch(`/api/classic-routes/${encodeURIComponent(city)}?include_top_times=true`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Errore di rete: ' + response.status);
            }
            return response.json();
        })
        .then(routes => {
            if (!Array.isArray(routes)) {
                routes = [];
            }

            if (routes.length === 0) {
                container.style.display = 'none';
                if (noRoutes) noRoutes.style.display = 'block';
                return;
            }

            if (noRoutes) noRoutes.style.display = 'none';
            container.style.display = 'flex';
            
            let htmlContent = '';
            routes.forEach(route => {
                // Sezione Top 5 Tempi compatta
                const topTimesHtml = route.top_5_times && route.top_5_times.length > 0 ? `
                    <div class="top-times-section">
                        <h6 class="border-bottom pb-1 mb-2 small">
                            <i class="bi bi-trophy text-warning me-1"></i>Top 5 Tempi
                        </h6>
                        <div class="top-times-list">
                            ${route.top_5_times.slice(0, 5).map((time, index) => `
                                <div class="d-flex justify-content-between align-items-center py-1 border-bottom">
                                    <div class="d-flex align-items-center">
                                        <span class="badge bg-secondary me-2" style="font-size: 0.6rem; min-width: 20px;">${index + 1}</span>
                                        <small class="text-truncate" style="max-width: 80px;">${time.username}</small>
                                    </div>
                                    <small class="text-muted">${formatDurationCompact(time.duration)}</small>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : `
                    <div class="top-times-section">
                        <h6 class="border-bottom pb-1 mb-2 small text-muted">
                            <i class="bi bi-trophy me-1"></i>Top 5 Tempi
                        </h6>
                        <small class="text-muted">Nessun tempo registrato</small>
                    </div>
                `;

                htmlContent += `
                <div class="col-md-6 col-lg-4 mb-4">
                    <div class="card h-100 route-card shadow-sm border-0">
                        <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                            <h5 class="card-title mb-0" style="font-size: 1.1rem;">${route.name}</h5>
                            <div class="badge-container">
                                <span class="badge bg-light text-dark me-1">${route.activity_type}</span>
                                <span class="badge bg-warning text-dark">${route.difficulty}</span>
                            </div>
                        </div>
                        
                        ${route.featured_image ? `
                            <img src="/static/featured_routes/${route.featured_image}" 
                                 class="card-img-top" alt="${route.name}" 
                                 style="height: 180px; object-fit: cover;">
                        ` : `
                            <div class="card-img-top bg-secondary d-flex align-items-center justify-content-center text-white" 
                                 style="height: 180px;">
                                <i class="bi bi-geo-alt-fill" style="font-size: 3rem;"></i>
                            </div>
                        `}
                        
                        <div class="card-body">
                            <p class="card-text" style="font-size: 0.9rem;">${route.description}</p>
                            
                            <div class="route-details" style="font-size: 0.8rem;">
                                <div class="d-flex align-items-center mb-1">
                                    <i class="bi bi-geo-alt me-2 text-primary" style="font-size: 0.8rem;"></i>
                                    <small><strong>Partenza:</strong> ${route.start_location}</small>
                                </div>
                                <div class="d-flex align-items-center mb-1">
                                    <i class="bi bi-flag me-2 text-success" style="font-size: 0.8rem;"></i>
                                    <small><strong>Arrivo:</strong> ${route.end_location}</small>
                                </div>
                                <div class="d-flex align-items-center mb-1">
                                    <i class="bi bi-arrows-expand me-2 text-info" style="font-size: 0.8rem;"></i>
                                    <small><strong>Distanza:</strong> ${route.distance_km.toFixed(1)} km</small>
                                </div>
                                <div class="d-flex align-items-center mb-1">
                                    <i class="bi bi-mountain me-2 text-warning" style="font-size: 0.8rem;"></i>
                                    <small><strong>Dislivello:</strong> +${route.elevation_gain} m</small>
                                </div>
                                <div class="d-flex align-items-center">
                                    <i class="bi bi-clock me-2 text-secondary" style="font-size: 0.8rem;"></i>
                                    <small><strong>Tempo:</strong> ${route.estimated_time}</small>
                                </div>
                            </div>
                            
                            <!-- Layout a due colonne per Top Times e Pulsanti -->
                            <div class="row mt-3 g-2">
                                <!-- Colonna Top Times -->
                                <div class="col-7">
                                    ${topTimesHtml}
                                </div>
                                
                                <!-- Colonna Pulsanti -->
                                <div class="col-5">
                                    <div class="action-buttons h-100 d-flex flex-column justify-content-between">
                                        <a href="/activities/record?route_id=${route.id}" class="btn btn-success btn-sm w-100 mb-2">
                                            <i class="bi bi-stopwatch me-1"></i>Registra Tempo
                                        </a>
                                        <a href="/challenges/new?route_id=${route.id}" class="btn btn-warning btn-sm w-100">
                                            <i class="bi bi-trophy me-1"></i>Sfida
                                        </a>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="card-footer bg-transparent">
                            <div class="d-flex justify-content-between align-items-center">
                                <small class="text-muted">
                                    <i class="bi bi-activity me-1"></i>
                                    ${route.total_activities} attività
                                </small>
                                <a href="/route/${route.id}" class="btn btn-primary btn-sm">
                                    <i class="bi bi-eye me-1"></i>Dettagli
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
                `;
            });
            
            container.innerHTML = htmlContent;
        })
        .catch(error => {
            console.error('Errore nel caricamento percorsi classici:', error);
            container.innerHTML = `
                <div class="col-12">
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        Errore nel caricamento: ${error.message}
                    </div>
                </div>
            `;
        });
}

// =======================================================
// GESTIONE LIKE ATTIVITÀ
// =======================================================

document.addEventListener('DOMContentLoaded', function() {
    // Gestione dei like sulle attività
    document.body.addEventListener('click', function(event) {
        const likeButton = event.target.closest('.like-activity-button');
        
        if (likeButton) {
            event.preventDefault();
            
            const activityId = likeButton.dataset.activityId;
            const likeCountSpan = likeButton.querySelector('.like-count');
            
            fetch(`/api/activity/${activityId}/like`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.status === 'success') {
                    likeCountSpan.textContent = data.new_like_count;
                    
                    if (data.action === 'liked') {
                        likeButton.classList.remove('btn-outline-danger');
                        likeButton.classList.add('btn-danger');
                    } else {
                        likeButton.classList.remove('btn-danger');
                        likeButton.classList.add('btn-outline-danger');
                    }
                }
            })
            .catch(error => {
                console.error('Errore durante l-operazione di like:', error);
                if (error.response && error.response.status === 401) {
                    window.location.href = '/login'; 
                }
            });
        }
    });
});

// =======================================================
// INIZIALIZZAZIONE PRINCIPALE
// =======================================================

document.addEventListener('DOMContentLoaded', function() {
    // Service Worker registration
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/js/sw.js')
            .then(function(registration) {
                console.log('Service Worker registrato');
            })
            .catch(function(error) {
                console.log('Service Worker fallito:', error);
            });
    }

    if (typeof is_homepage_js === 'undefined' || !is_homepage_js) return;

    // INIZIALIZZA LE VARIABILI PRIMA
    userProfileUrlBase = document.getElementById('user-profile-url-base')?.textContent || '';
    routeDetailUrlBase = document.getElementById('route-detail-url-base')?.textContent || '';
    activityDetailUrlBase = document.getElementById('activity-detail-url-base')?.textContent || '';
    mapDataApiUrl = document.getElementById('map-data-api-url')?.textContent || '';
    userInitialCity = document.getElementById('user-initial-city')?.textContent || '';
    profilePicsBaseUrl = document.getElementById('profile-pics-base-url')?.textContent || '';

    // INIZIALIZZA LA MAPPA
    initializeMap();

    // GESTORI EVENTI
    const citySearchInput = document.getElementById('citySearchInput');
    const citySearchButton = document.getElementById('searchCityButton');
    const citySearchSpinner = document.getElementById('citySearchSpinner');

    function searchCity(cityName) {
        if (!cityName) return;
        if (citySearchButton) citySearchButton.disabled = true;
        if (citySearchSpinner) citySearchSpinner.style.display = 'inline-block';
        
        fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(cityName)}&format=json&limit=1`)
            .then(response => response.json())
            .then(data => {
                if (data && data.length > 0) {
                    loadMapAndData(parseFloat(data[0].lat), parseFloat(data[0].lon), 13, data[0].display_name);
                } else {
                    alert('Città non trovata.');
                    if (citySearchButton) citySearchButton.disabled = false;
                    if (citySearchSpinner) citySearchSpinner.style.display = 'none';
                }
            }).catch(err => {
                console.error('Errore ricerca città:', err);
                alert('Errore di rete durante la ricerca.');
                if (citySearchButton) citySearchButton.disabled = false;
                if (citySearchSpinner) citySearchSpinner.style.display = 'none';
            });
    }

    if (citySearchInput) {
        citySearchInput.addEventListener('keypress', e => { 
            if (e.key === 'Enter') searchCity(citySearchInput.value); 
        });
    }
    
    if (citySearchButton) {
        citySearchButton.addEventListener('click', () => searchCity(citySearchInput?.value || ''));
    }
    
    // Filtri attività
    document.querySelectorAll('#activityTypeFilter .btn').forEach(button => {
        button.addEventListener('click', function() {
            document.querySelector('#activityTypeFilter .btn.active').classList.remove('active');
            this.classList.add('active');
            const center = mainMap.getCenter();
            loadMapAndData(center.lat, center.lng, mainMap.getZoom());
        });
    });

    // CARICAMENTO INIZIALE
    setTimeout(() => {
        searchCity(userInitialCity || "Italia");
    }, 500);
});

console.log('🚀 Main.js completamente caricato!');