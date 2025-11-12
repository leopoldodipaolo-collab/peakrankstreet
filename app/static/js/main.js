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
            const url = `/api/search_city?q=${encodeURIComponent(cityName)}`;
            const res = await fetch(url);

            if (!res.ok) throw new Error(`HTTP error ${res.status}`);
            const data = await res.json();

            if (!Array.isArray(data) || data.length === 0) {
                alert('Città non trovata.');
                return;
            }

            const city = data[0].display_name.split(',')[0].trim();
            const lat = parseFloat(data[0].lat);
            const lon = parseFloat(data[0].lon);

            console.log(`✅ Città trovata: ${city} (${lat}, ${lon})`);
            loadMapAndData(lat, lon, 13, city);
            loadClassicRoutes(city);

        } catch (err) {
            console.warn('⚠️ Servizio Nominatim non disponibile o errore di rete:', err);

            // Mostra un messaggio discreto nel campo o accanto
            const msgBox = document.getElementById("citySearchMessage");
            if (msgBox) {
                msgBox.textContent = "⚠️ Servizio temporaneamente non disponibile. Riprova più tardi.";
                msgBox.style.display = "block";
            }

            // Non bloccare l’utente con un alert
        } finally {
            cityButton.disabled = false;
            citySpinner.style.display = 'none';
        }

    }

    cityInput.addEventListener('keypress', e => { 
        if (e.key === 'Enter') searchCity(cityInput.value.trim());
    });
    cityButton.addEventListener('click', () => searchCity(cityInput.value.trim()));
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

    // Evidenzia al mouseover **solo se non è già selezionato**
    marker.on('mouseover', () => {
        if (!marker.isClicked) {
            selectedRouteLayer.clearLayers();
            selectedRouteLayer.addData(route.coordinates);
        }
    });

    // Rimuove evidenziazione al mouseout solo se non è cliccato
    marker.on('mouseout', () => {
        if (!marker.isClicked) {
            selectedRouteLayer.clearLayers();
        }
    });

    // Al click, mantiene evidenziato
    marker.on('click', () => {
        // Pulisce tutti gli altri marker “cliccati”
        markers.getLayers().forEach(m => m.isClicked = false);

        marker.isClicked = true; // questo marker resta evidenziato
        selectedRouteLayer.clearLayers();
        selectedRouteLayer.addData(route.coordinates);
        displayRouteDetails(route);
    });

    markers.addLayer(marker);
}


// =======================================================
// FILTRO PER TIPO DI ATTIVITÀ
// =======================================================
document.querySelectorAll('#activityTypeFilter .btn').forEach(btn => {
    btn.addEventListener('click', () => {
        // Rimuove classe active da tutti i bottoni
        document.querySelectorAll('#activityTypeFilter .btn').forEach(b => b.classList.remove('active'));
        // Aggiunge classe active al bottone cliccato
        btn.classList.add('active');

        // Aggiorna i marker sulla mappa usando i dati già caricati
        const selectedType = btn.dataset.type;

        if (!loadedRoutes || loadedRoutes.length === 0) return;

        // Pulisce i marker esistenti
        markers.clearLayers();
        selectedRouteLayer.clearLayers();

        // Filtra i percorsi per tipo di attività
        const filteredRoutes = selectedType === 'all'
            ? loadedRoutes
            : loadedRoutes.filter(r => r.activity_type === selectedType);

        // Aggiunge i marker filtrati
        filteredRoutes.forEach(r => addRouteMarker(r));

        // Aggiorna bounds della mappa
        if (markers.getLayers().length > 0) {
            mainMap.fitBounds(markers.getBounds(), { padding: [50, 50], maxZoom: 15 });
        }
    });
});
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
    // Limita la lunghezza della descrizione (in caratteri)
    const maxLength = 180;
    const shortDescription = route.description && route.description.length > maxLength
        ? route.description.substring(0, maxLength).trim() + "..."
        : route.description || "";

    // Top 5 tempi
    const topTimes = (route.top_5_times || route.top_5_activities || []).map(t => ({
        username: t.username,
        profile_image: t.profile_image,
        duration: t.duration
    }));
    const topTimesHtml = createTopTimesHtml(topTimes);

    // Immagine di copertina
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
                <h5 class="card-title mb-0">${route.name}</h5>

                <div class="badge-container">
                    <span class="badge bg-light text-dark me-1" title="Attività: ${route.activity_type}">${route.activity_type}</span>
                    <span class="badge bg-warning text-dark" title="Difficoltà: ${route.difficulty}">${route.difficulty}</span>
                </div>
            </div>

            ${featuredImageHtml}

            <div class="card-body d-flex flex-column">
                <!-- 🔹 Mostra solo una descrizione breve -->
                <p class="card-text">${shortDescription}</p>
                <div class="route-details mb-3">
                    ${createRouteDetailsHtml(route)}
                </div>

                ${topTimesHtml}

                <div class="row mt-auto g-3">
                    <div class="col-12 col-md-7"></div>
                    <div class="col-12 col-md-5">
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

            <div class="card-footer bg-transparent d-flex justify-content-between align-items-center">
                <small class="text-muted">
                    <i class="bi bi-activity me-1"></i>${route.total_activities} attività
                </small>
                <a href="/route/${route.id}" class="btn btn-primary btn-sm">
                    <i class="bi bi-eye me-1"></i>Dettagli
                </a>
            </div>
        </div>
    </div>`;
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
                            <img src="/static/profile_pics/${time.profile_image || 'default.png'}" class="rounded-circle me-2 profile-image-small" alt="Avatar" style="width:24px; height:24px;">
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
    if (!detailsCard) return;

    // Popola nome percorso sia header che body
    document.getElementById('detail-route-name-header').textContent = routeProps.name;
    document.getElementById('detail-route-name-body').textContent = routeProps.name;

    document.getElementById('detail-route-description').textContent = routeProps.description || 'Nessuna descrizione.';

    let createdByHtml = `Creato il: ${routeProps.created_at} da <a href="${userProfileUrlBase.replace('12345', routeProps.created_by_id)}">${routeProps.created_by_username}</a>`;
    document.getElementById('detail-route-meta').innerHTML = `${createdByHtml}<br>Distanza: ${routeProps.distance_km ? routeProps.distance_km.toFixed(2) + ' km' : 'N/D'}`;

    document.getElementById('detail-route-link').href = routeDetailUrlBase.replace('12345', routeProps.id);
    document.getElementById('record-activity-link').href = `/activities/record?route_id=${routeProps.id}`;
    document.getElementById('create-challenge-link').href = `/challenges/new?route_id=${routeProps.id}`;

    // King/Queen
    if (routeProps.king_queen && routeProps.king_queen.username) {
        document.getElementById('kq-username').innerHTML = `<a href="${userProfileUrlBase.replace('12345', routeProps.king_queen.user_id)}" class="user-link text-dark">${routeProps.king_queen.username}</a>`;
        document.getElementById('kq-duration').textContent = formatDuration(routeProps.king_queen.duration);
        document.getElementById('kq-activity-link').href = activityDetailUrlBase.replace('12345', routeProps.king_queen.activity_id);
        document.getElementById('kq-created-at').textContent = `Registrato il: ${routeProps.king_queen.created_at}`;
        document.getElementById('detail-king-queen').style.display = 'block';
    } else {
        document.getElementById('detail-king-queen').style.display = 'none';
    }

    // Top 5 tempi
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

    detailsCard.style.display = 'block';

    // Nascondi istruzioni mappa e evidenzia percorso
    const mapInstructions = document.getElementById('map-instructions');
    if (mapInstructions) mapInstructions.style.display = 'none';
    if (routeProps.coordinates?.geometry?.coordinates?.length > 0 && selectedRouteLayer) {
        selectedRouteLayer.clearLayers();
        selectedRouteLayer.addData(routeProps.coordinates);
    }

    setTimeout(() => detailsCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100);
}

function hideRouteDetails() {
    const detailsCard = document.getElementById('selected-route-details');
    if (detailsCard) detailsCard.style.display = 'none';
    if (selectedRouteLayer) selectedRouteLayer.clearLayers();
    const mapInstructions = document.getElementById('map-instructions');
    if (mapInstructions) mapInstructions.style.display = 'block';
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
/**
 * 🚀 POPOLA LE CLASSIFICHE LOCALI CON EFFETTI NEXT-LEVEL
 * @param {Object} leaderboards - Dati delle classifiche
 */
function populateLocalLeaderboards(leaderboards) {
    const distanceList = document.getElementById('top-distance-list');
    const creatorsList = document.getElementById('top-creators-list');
    
    if (!distanceList || !creatorsList) return;

    // Animazione di entrata
    gsap.fromTo([distanceList, creatorsList], 
        { opacity: 0, y: 50 },
        { opacity: 1, y: 0, duration: 0.8, stagger: 0.2 }
    );

    // Popola con effetti sequenziali
    renderLeaderboardWithFlair(distanceList, leaderboards.distance, 'distance');
    renderLeaderboardWithFlair(creatorsList, leaderboards.creators, 'creators');
}

/**
 * 💫 RENDER CON EFFETTI SPECIALI
 */
function renderLeaderboardWithFlair(container, data, type) {
    container.innerHTML = '';

    if (!data || data.length === 0) {
        container.innerHTML = createEpicEmptyState();
        return;
    }

    // Prepara container per animazioni
    container.style.opacity = '0';
    
    setTimeout(() => {
        container.innerHTML = data.map((entry, index) => 
            createEpicLeaderboardItem(entry, index, type)
        ).join('');
        
        // ANIMAZIONE ENTRATA ITEMS
        gsap.fromTo(container.children,
            {
                opacity: 0,
                x: -100,
                rotationY: 90
            },
            {
                opacity: 1,
                x: 0,
                rotationY: 0,
                duration: 0.6,
                stagger: 0.1,
                ease: "back.out(1.7)",
                onComplete: () => addHoverEffects(container)
            }
        );
        
        container.style.opacity = '1';
    }, 300);
}

/**
 * 🏆 CREA ITEM CON DESIGN PREMIUM
 */
function createEpicLeaderboardItem(entry, index, type) {
    const rankInfo = getEpicRankInfo(index);
    
    return `
        <li class="list-group-item epic-leaderboard-item" data-rank="${index + 1}">
            <div class="item-content">
                <!-- RANK BADGE CON EFFETTO SPECIALE -->
                <div class="rank-container">
                    <div class="rank-badge ${rankInfo.class}">
                        <div class="rank-shine"></div>
                        <span class="rank-number">${index + 1}</span>
                        ${index < 3 ? `<div class="rank-crown">${rankInfo.icon}</div>` : ''}
                    </div>
                </div>

                <!-- USER INFO CON AVATAR E DETTAGLI -->
                <div class="user-info">
                    <div class="avatar-container">
                        <div class="avatar-wrapper">
                            <div class="avatar-background-glow"></div>
                            <div class="avatar-border-animation"></div>
                            <img src="${profilePicsBaseUrl}${entry.profile_image}" 
                                class="user-avatar epic-avatar"
                                alt="${entry.username}"
                                loading="lazy"
                                onerror="this.src='/img/LogoX_SS.png'">
                            <div class="avatar-glow-effect"></div>
                            <div class="floating-particles">
                                <div class="particle p1"></div>
                                <div class="particle p2"></div>
                            </div>
                            ${index < 3 ? `
                            <div class="premium-rank-badge ${rankInfo.class}">
                                <div class="badge-inner">
                                    <span class="badge-icon">${rankInfo.icon}</span>
                                </div>
                            </div>
                            ` : ''}
                        </div>
                    </div>
                    
                    <!-- NOME E VALORE VERTICALI -->
                    <div class="user-details">
                        <a href="${userProfileUrlBase.replace('12345', entry.id)}" 
                           class="username-link">
                            <span class="username-text">${entry.username}</span>
                        </a>
                        <div class="achievement-value">
                            <span class="value-display">
                                <i class="fas ${type === 'distance' ? 'fa-route' : 'fa-map-marked-alt'} pulse-icon"></i>
                                ${type === 'distance' 
                                    ? `${entry.total_distance.toFixed(2)} km`
                                    : `${entry.total_routes_created} percorsi`
                                }
                            </span>
                            <div class="progress-sparkle"></div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- BACKGROUND EFFETTI -->
            <div class="item-background">
                <div class="liquid-shape"></div>
                <div class="particle-field"></div>
            </div>
        </li>
    `;
}

/**
 * 👑 INFO RANK CON ICONE PERSONALIZZATE
 */
function getEpicRankInfo(index) {
    const ranks = [
        { 
            class: 'rank-1', 
            icon: '👑', 
            badge: '🏆 TOP 1',
            color: 'linear-gradient(135deg, #FFD700, #FF6B00)'
        },
        { 
            class: 'rank-2', 
            icon: '⭐', 
            badge: '🥈 TOP 2',
            color: 'linear-gradient(135deg, #C0C0C0, #E8E8E8)'
        },
        { 
            class: 'rank-3', 
            icon: '🔥', 
            badge: '🥉 TOP 3',
            color: 'linear-gradient(135deg, #CD7F32, #FFA500)'
        },
        { 
            class: 'rank-other', 
            icon: '⚡', 
            badge: '🚀',
            color: 'linear-gradient(135deg, #667eea, #764ba2)'
        }
    ];
    
    return index < 3 ? ranks[index] : ranks[3];
}

/**
 * 🌌 STATO VUOTO EPICO
 */
function createEpicEmptyState() {
    return `
        <li class="list-group-item epic-empty-state">
            <div class="empty-content">
                <div class="floating-astronaut">👨‍🚀</div>
                <div class="empty-glow"></div>
                <h4 class="empty-title">Nessun dato cosmico trovato!</h4>
                <p class="empty-text">Sii il primo a esplorare questa area</p>
                <button class="btn btn-galaxy start-exploring-btn">
                    <span class="btn-glow"></span>
                    🚀 Inizia l'esplorazione
                </button>
            </div>
        </li>
    `;
}

/**
 * ✨ AGGIUNGI EFFETTI HOVER
 */
function addHoverEffects(container) {
    const items = container.querySelectorAll('.epic-leaderboard-item');
    
    items.forEach(item => {
        item.addEventListener('mouseenter', function() {
            gsap.to(this, {
                y: -5,
                scale: 1.02,
                duration: 0.3,
                ease: "power2.out"
            });
            
            // Effetto particelle
            const particles = this.querySelector('.particle-field');
            animateParticles(particles);
        });
        
        item.addEventListener('mouseleave', function() {
            gsap.to(this, {
                y: 0,
                scale: 1,
                duration: 0.3,
                ease: "power2.out"
            });
        });
    });
}

/**
 * 🌟 ANIMAZIONE PARTICELLE
 */
function animateParticles(container) {
    const particles = Array.from({length: 8}, (_, i) => {
        const particle = document.createElement('div');
        particle.className = 'particle';
        particle.style.setProperty('--i', i);
        container.appendChild(particle);
        return particle;
    });

    gsap.to(particles, {
        x: () => gsap.utils.random(-50, 50),
        y: () => gsap.utils.random(-50, 50),
        opacity: 0,
        scale: 0,
        duration: 1,
        stagger: 0.1,
        onComplete: () => {
            particles.forEach(p => p.remove());
        }
    });
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

document.addEventListener("click", async (e) => {
    const replyBtn = e.target.closest(".reply-btn");
    if (!replyBtn) return;

    e.preventDefault();

    const commentId = replyBtn.dataset.commentId;
    const postId = replyBtn.dataset.postId;
    const container = document.getElementById(`reply-form-for-${commentId}`);

    // Se il form è già visibile, chiudilo
    if (container.style.display === "block") {
        container.innerHTML = "";
        container.style.display = "none";
        return;
    }

    // Altrimenti, mostra il form
    container.innerHTML = `
        <form method="POST" action="/api/post/${postId}/comment/${commentId}/reply" class="reply-form mt-2">
            <input type="hidden" name="csrf_token" value="${document.querySelector('input[name="csrf_token"]').value}">
            <div class="d-flex">
                <img src="/static/profile_pics/${window.currentUserProfileImage}" class="rounded-circle me-2" style="width:30px; height:30px; object-fit:cover;">
                <textarea name="content" rows="1" class="form-control me-2" placeholder="Rispondi..." required></textarea>
                <button type="submit" class="btn btn-sm btn-outline-primary">
                    <i class="bi bi-send"></i>
                </button>
            </div>
        </form>
    `;
    container.style.display = "block";
});

// Gestione invio del form di risposta via AJAX
document.addEventListener("submit", async (e) => {
    const form = e.target.closest(".reply-form");
    if (!form) return;

    e.preventDefault();
    const formData = new FormData(form);
    const url = form.action;

    const response = await fetch(url, {
        method: "POST",
        body: formData
    });

    const data = await response.json();
    if (data.status === "success") {
        const repliesContainer = form.closest(".reply-form-container").previousElementSibling;
        repliesContainer.insertAdjacentHTML("beforeend", data.comment_html);
        form.remove();
    }
});

// FUNZIONE PER MOSTRARE IL CAVALIERE
function showKnightHighlight(routeData, kingQueenData) {
    const knightElement = document.getElementById('detail-king-queen');
    
    if (!kingQueenData || !kingQueenData.username) {
        knightElement.style.display = 'none';
        return;
    }
    
    // Prendi il nome dal percorso selezionato
    const routeName = routeData.name || "Questo Percorso";
    
    // Popola i dati
    document.getElementById('royal-full-title').innerHTML = 
        `Cavaliere di <span class="activity-name">${routeName}</span>`;
    
    document.getElementById('kq-activity-name').textContent = routeName;
    document.getElementById('kq-username').textContent = kingQueenData.username;
    document.getElementById('kq-duration').textContent = kingQueenData.duration;
    document.getElementById('kq-created-at').textContent = kingQueenData.created_at;
    document.getElementById('kq-avatar').src = kingQueenData.avatar_url;
    
    // Imposta il link all'attività
    const activityUrlBase = document.getElementById('activity-detail-url-base').textContent;
    document.getElementById('kq-activity-link').href = 
        activityUrlBase.replace('12345', kingQueenData.activity_id);
    
    // Mostra l'elemento
    knightElement.style.display = 'block';
    
    // Animazione entrata
    gsap.fromTo(knightElement, 
        { opacity: 0, y: 30, scale: 0.9 },
        { opacity: 1, y: 0, scale: 1, duration: 0.6, ease: "back.out(1.7)" }
    );
}

// ESEMPIO DI UTILIZZO QUANDO SI SELEZIONA UN PERCORSO
function onRouteSelected(route) {
    // Mostra dettagli percorso
    document.getElementById('detail-route-name').textContent = route.name;
    document.getElementById('detail-route-description').textContent = route.description;
    
    // Recupera dati del cavaliere per questo percorso
    fetch(`/api/route/${route.id}/king`)
        .then(response => response.json())
        .then(kingData => {
            showKnightHighlight(route, kingData);
        })
        .catch(() => {
            // Nascondi se non ci sono dati
            document.getElementById('detail-king-queen').style.display = 'none';
        });
}

function createRoyalParticles() {
    const container = document.querySelector('.royal-particles');
    if (!container) return;
    
    // Crea particelle dinamiche
    for (let i = 0; i < 8; i++) {
        const particle = document.createElement('div');
        particle.className = 'royal-particle';
        particle.style.left = Math.random() * 100 + '%';
        particle.style.top = Math.random() * 100 + '%';
        particle.style.animationDelay = Math.random() * 6 + 's';
        container.appendChild(particle);
    }
}

// Inizializza quando mostra il componente
function showKingQueenHighlight(data) {
    const element = document.getElementById('detail-king-queen');
    element.style.display = 'block';
    
    // Popola dati
    document.getElementById('kq-username').textContent = data.username;
    document.getElementById('kq-duration').textContent = data.duration;
    document.getElementById('kq-created-at').textContent = data.createdAt;
    document.getElementById('kq-avatar').src = data.avatarUrl;
    
    // Avvia effetti
    createRoyalParticles();
    
    // Animazione entrata
    gsap.fromTo(element, 
        { opacity: 0, y: 50, scale: 0.8 },
        { opacity: 1, y: 0, scale: 1, duration: 0.8, ease: "back.out(1.7)" }
    );
}

console.log('🚀 Main.js completamente caricato!');
