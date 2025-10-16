// =======================================================
// VARIABILI GLOBALI
// =======================================================
let mainMap, markers, osmLayer, topoLayer;
let selectedRouteLayer;
let userProfileUrlBase, routeDetailUrlBase, activityDetailUrlBase, profilePicsBaseUrl, mapDataApiUrl, userInitialCity;
let loadedRoutes = [];

// =======================================================
// INIZIALIZZAZIONE PRINCIPALE
// =======================================================
document.addEventListener('DOMContentLoaded', function() {

    // Registrazione Service Worker
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/js/sw.js')
            .then(() => console.log('Service Worker registrato'))
            .catch(err => console.log('Service Worker fallito:', err));
    }

    if (typeof is_homepage_js === 'undefined' || !is_homepage_js) return;

    // Inizializza variabili globali
    userProfileUrlBase = document.getElementById('user-profile-url-base')?.textContent || '';
    routeDetailUrlBase = document.getElementById('route-detail-url-base')?.textContent || '';
    activityDetailUrlBase = document.getElementById('activity-detail-url-base')?.textContent || '';
    mapDataApiUrl = document.getElementById('map-data-api-url')?.textContent || '';
    userInitialCity = document.getElementById('user-initial-city')?.textContent || '';
    profilePicsBaseUrl = document.getElementById('profile-pics-base-url')?.textContent || '';

    // Inizializza mappa
    initializeMap();

    // Setup ricerca città
    setupCitySearch();

    // Caricamento iniziale della città
    searchInitialCity();
});

function formatDuration(seconds) {
    if (!seconds && seconds !== 0) return 'N/D';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return (h ? h + 'h ' : '') + (m ? m + 'm ' : '') + (s ? s + 's' : '');
}

function formatDurationCompact(seconds) {
    if (!seconds && seconds !== 0) return 'N/D';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h) return `${h}h ${m}m`;
    if (m) return `${m}m ${s}s`;
    return `${s}s`;
}

// =======================================================
// FUNZIONI MAPPA
// =======================================================
function initializeMap() {
    if (!mainMap) {
        mainMap = L.map('mainMap', {
            center: [42.3498, 13.3995],
            zoom: 13,
            zoomControl: true,
            attributionControl: true,
            preferCanvas: true
        });

        // Layer di base
        osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(mainMap);
        topoLayer = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenTopoMap' });

        // Cluster marker
        markers = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 50 });
        mainMap.addLayer(markers);

        // Layer percorsi selezionati
        selectedRouteLayer = L.geoJSON(null, { style: { color: '#007bff', weight: 6 }, interactive: false }).addTo(mainMap);

        // Controllo layer
        L.control.layers({ "Stradale": osmLayer, "Topografica": topoLayer }, { "Percorsi": markers }).addTo(mainMap);

        // Click sulla mappa per deselezionare
        mainMap.on('click', hideRouteDetails);

        // Resize mappa
        setTimeout(() => mainMap.invalidateSize(), 100);
    }
}

// =======================================================
// RICERCA CITTÀ
// =======================================================
function setupCitySearch() {
    const cityInput = document.getElementById('citySearchInput');
    const cityButton = document.getElementById('searchCityButton');
    const citySpinner = document.getElementById('citySearchSpinner');

    if (!cityInput || !cityButton) return;

    async function searchCity(cityName) {
        if (!cityName) return;
        cityButton.disabled = true;
        citySpinner.style.display = 'inline-block';

        try {
            const res = await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(cityName)}&format=json&limit=5`);
            const data = await res.json();
            console.log('Local leaderboards:', data.local_leaderboards); // <--- qui funziona
            if (!data || data.length === 0) {
                alert('Città non trovata.');
                return;
            }

            const city = data[0].display_name.split(',')[0].trim();
            const lat = parseFloat(data[0].lat);
            const lon = parseFloat(data[0].lon);

            loadMapAndData(lat, lon, 13, city);
            loadClassicRoutes(city);

        } catch (err) {
            console.error('Errore ricerca città:', err);
            alert('Errore di rete durante la ricerca.');
        } finally {
            cityButton.disabled = false;
            citySpinner.style.display = 'none';
        }
    }

    cityInput.addEventListener('keypress', e => { if (e.key === 'Enter') searchCity(cityInput.value); });
    cityButton.addEventListener('click', () => searchCity(cityInput.value));
}

function searchInitialCity() {
    const city = userInitialCity ? userInitialCity.split(',')[0].trim() : "Italia";
    const cityInput = document.getElementById('citySearchInput');
    if (cityInput) cityInput.value = city;
    cityInput.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter' }));
}

// =======================================================
// CARICAMENTO DATI MAPPA
// =======================================================
async function loadMapAndData(lat, lon, zoom = 13, city = null) {
    if (!mainMap) return;
    mainMap.flyTo([lat, lon], zoom, { duration: 1.2 });

    // Pulisce vecchi marker e percorsi selezionati
    markers.clearLayers();
    selectedRouteLayer.clearLayers();

    // Marker città
    if (city) L.marker([lat, lon]).addTo(mainMap).bindPopup(`<b>${city}</b>`).openPopup();

    const activityType = document.querySelector('#activityTypeFilter .btn.active')?.dataset.type || 'all';
    
    try {
        // Chiamata API filtrata per città
        const apiUrl = `${mapDataApiUrl}?lat=${lat}&lon=${lon}&radius_km=50&activity_type=${activityType}&city=${encodeURIComponent(city || '')}`;
        const res = await fetch(apiUrl);
        const data = await res.json();
        loadedRoutes = data.routes || [];

        // Aggiungi marker dei percorsi
        loadedRoutes.forEach(r => addRouteMarker(r));
        if (markers.getLayers().length > 0) mainMap.fitBounds(markers.getBounds(), { padding: [50, 50], maxZoom: 15 });

        // Popola le varie liste
        populateAvailableRoutes(data.routes);
        populateRecentChallenges(data.challenges);
        populateRecentActivities(data.recent_activities);

        // AGGIORNAMENTO ERROI LOCALI per la città selezionata
        if (data.local_leaderboards) {
            populateLocalLeaderboards(data.local_leaderboards);
        } else {
            populateLocalLeaderboards({ distance: [], creators: [] });
        }

    } catch (err) {
        console.error('Errore caricamento dati:', err);
    }
}


// =======================================================
// AGGIUNGI MARKER PERCORSO
// =======================================================
function addRouteMarker(route) {
    if (!route.coordinates?.geometry?.coordinates?.[0]) return;
    const start = route.coordinates.geometry.coordinates[0];

    const icon = {
        'Corsa': '/static/icons/runner.png',
        'Bici': '/static/icons/bicycle.png',
        'Hike': '/static/icons/hiking.png'
    }[route.activity_type] || '/static/icons/default.png';

    const marker = L.marker([start[1], start[0]], { icon: L.icon({ iconUrl: icon, iconSize: [32,32], iconAnchor: [16,32] }) });
    marker.bindPopup(`<b>${route.name}</b><br>Distanza: ${route.distance_km?.toFixed(2) || 'N/D'} km`);

    marker.on('mouseover', () => selectedRouteLayer.clearLayers() || selectedRouteLayer.addData(route.coordinates));
    marker.on('mouseout', () => selectedRouteLayer.clearLayers());
    marker.on('click', () => displayRouteDetails(route));

    markers.addLayer(marker);
}

// =======================================================
// PERCORSI CLASSICI
// =======================================================
// =======================================================
// PERCORSI CLASSICI - VERSIONE REFACTOR
// =======================================================
async function loadClassicRoutes(city) {
    console.log('loadClassicRoutes chiamata per città:', city);

    const section = document.getElementById('classic-routes-section');
    const container = document.getElementById('classic-routes-container');
    const noRoutes = document.getElementById('no-classic-routes');
    const cityTitle = document.getElementById('classic-routes-city');

    if (!section || !container || !cityTitle) {
        console.error('Elementi HTML non trovati!');
        return;
    }

    if (!city || city.trim() === '') {
        section.style.display = 'none';
        return;
    }

    // Mostra sezione e titolo città
    section.style.display = 'block';
    cityTitle.textContent = city;

    // Mostra spinner di caricamento
    container.innerHTML = `
        <div class="col-12 text-center">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-2 text-muted">Caricamento percorsi classici...</p>
        </div>
    `;
    noRoutes.style.display = 'none';

    try {
        const response = await fetch(`/api/classic-routes/${encodeURIComponent(city)}?include_top_times=true`);
        if (!response.ok) throw new Error(`Errore di rete: ${response.status}`);

        let routes = await response.json();
        if (!Array.isArray(routes)) routes = [];

        if (routes.length === 0) {
            container.style.display = 'none';
            noRoutes.style.display = 'block';
            return;
        }

        container.style.display = 'flex';
        noRoutes.style.display = 'none';

        // Genera HTML dei percorsi
        container.innerHTML = routes.map(route => createClassicRouteCard(route)).join('');

    } catch (error) {
        console.error('Errore nel caricamento percorsi classici:', error);
        container.innerHTML = `
            <div class="col-12">
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Errore nel caricamento: ${error.message}
                </div>
            </div>
        `;
    }
}

// =======================================================
// FUNZIONE HELPER: CREA CARD PERCORSO CLASSICO
// =======================================================
function createClassicRouteCard(route) {
    const topTimesHtml = createTopTimesHtml(route.top_5_times);

    const featuredImageHtml = route.featured_image
        ? `<img src="/static/featured_routes/${route.featured_image}" 
                class="card-img-top route-card-img" alt="${route.name}">`
        : `<div class="card-img-top bg-secondary d-flex align-items-center justify-content-center text-white route-card-img-placeholder">
               <i class="bi bi-geo-alt-fill" style="font-size:3rem;"></i>
           </div>`;

    return `
    <div class="col-12 col-md-6 col-lg-4 mb-4">
        <div class="card h-100 route-card shadow-sm border-0 animate__animated animate__fadeIn">
            <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                <h5 class="card-title mb-0 text-truncate">${route.name}</h5>
                <div class="badge-container">
                    <span class="badge bg-light text-dark me-1" data-bs-toggle="tooltip" title="Attività: ${route.activity_type}">${route.activity_type}</span>
                    <span class="badge bg-warning text-dark" data-bs-toggle="tooltip" title="Difficoltà: ${route.difficulty}">${route.difficulty}</span>
                </div>
            </div>

            ${featuredImageHtml}

            <div class="card-body d-flex flex-column">
                <p class="card-text text-truncate-3">${route.description}</p>
                <div class="route-details mb-3">
                    ${createRouteDetailsHtml(route)}
                </div>

                <div class="row mt-auto g-3">
                    <div class="col-12 col-md-7">${topTimesHtml}</div>
                    <div class="col-12 col-md-5">
                        <div class="action-buttons h-100 d-flex flex-column justify-content-between">
                            <a href="/activities/record?route_id=${route.id}" class="btn btn-success btn-sm w-100 mb-2 action-btn">
                                <i class="bi bi-stopwatch me-1"></i>Registra Tempo
                            </a>
                            <a href="/challenges/new?route_id=${route.id}" class="btn btn-warning btn-sm w-100 action-btn">
                                <i class="bi bi-trophy me-1"></i>Sfida
                            </a>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card-footer bg-transparent d-flex justify-content-between align-items-center">
                <small class="text-muted">
                    <i class="bi bi-activity me-1"></i>${route.total_activities} attività
                </small>
                <a href="/route/${route.id}" class="btn btn-primary btn-sm action-btn">
                    <i class="bi bi-eye me-1"></i>Dettagli
                </a>
            </div>
        </div>
    </div>
    `;
}

// =======================================================
// FUNZIONE HELPER: CREA HTML DETTAGLI PERCORSO
// =======================================================
function createRouteDetailsHtml(route) {
    return `
        <div class="d-flex align-items-center mb-1">
            <i class="bi bi-geo-alt me-2 text-primary" style="font-size:0.8rem;"></i>
            <small><strong>Partenza:</strong> ${route.start_location}</small>
        </div>
        <div class="d-flex align-items-center mb-1">
            <i class="bi bi-flag me-2 text-success" style="font-size:0.8rem;"></i>
            <small><strong>Arrivo:</strong> ${route.end_location}</small>
        </div>
        <div class="d-flex align-items-center mb-1">
            <i class="bi bi-arrows-expand me-2 text-info" style="font-size:0.8rem;"></i>
            <small><strong>Distanza:</strong> ${route.distance_km.toFixed(1)} km</small>
        </div>
        <div class="d-flex align-items-center mb-1">
            <i class="bi bi-mountain me-2 text-warning" style="font-size:0.8rem;"></i>
            <small><strong>Dislivello:</strong> +${route.elevation_gain} m</small>
        </div>
        <div class="d-flex align-items-center">
            <i class="bi bi-clock me-2 text-secondary" style="font-size:0.8rem;"></i>
            <small><strong>Tempo:</strong> ${route.estimated_time}</small>
        </div>
    `;
}

// =======================================================
// FUNZIONE HELPER: CREA HTML TOP 5 TIMES
// =======================================================
function createTopTimesHtml(topTimes) {
    if (!topTimes || topTimes.length === 0) {
        return `
            <div class="top-times-section">
                <h6 class="border-bottom pb-1 mb-2 small text-muted">
                    <i class="bi bi-trophy me-1"></i>Top 5 Tempi
                </h6>
                <small class="text-muted">Nessun tempo registrato</small>
            </div>
        `;
    }

    return `
        <div class="top-times-section">
            <h6 class="border-bottom pb-1 mb-2 small">
                <i class="bi bi-trophy text-warning me-1"></i>Top 5 Tempi
            </h6>
            <div class="top-times-list">
                ${topTimes.slice(0, 5).map((time, index) => `
                    <div class="d-flex justify-content-between align-items-center py-1 border-bottom top-times-item">
                        <div class="d-flex align-items-center">
                            <span class="badge bg-secondary me-2" style="font-size:0.65rem; min-width:20px;">${index + 1}</span>
                            <img src="${time.profile_image}" class="rounded-circle me-2 profile-image-small" alt="Avatar" style="width:24px; height:24px;">
                            <small class="text-truncate" style="max-width:80px;">${time.username}</small>
                        </div>
                        <small class="text-muted">${formatDurationCompact(time.duration)}</small>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

// =======================================================
// DETTAGLI PERCORSO
// =======================================================
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

// =======================================================
// FUNZIONI PER POPOLARE LISTE
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

    // Distanza percorsa
    distanceList.innerHTML = '';
    if (leaderboards.distance && leaderboards.distance.length > 0) {
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

    // Percorsi creati
    creatorsList.innerHTML = '';
    if (leaderboards.creators && leaderboards.creators.length > 0) {
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
// LIKE ATTIVITÀ
// =======================================================
document.body.addEventListener('click', function(event) {
    const likeButton = event.target.closest('.like-activity-button');
    if (!likeButton) return;

    event.preventDefault();
    const activityId = likeButton.dataset.activityId;
    const likeCountSpan = likeButton.querySelector('.like-count');

    fetch(`/api/activity/${activityId}/like`, { method: 'POST', headers: {'Content-Type': 'application/json'} })
        .then(res => res.json())
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
        .catch(err => console.error('Errore like attività:', err));
});

console.log('🚀 Main.js completamente caricato!');
