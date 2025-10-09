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

// Variabili globali
let mainMap, markers, osmLayer, topoLayer;
let userProfileUrlBase, routeDetailUrlBase, activityDetailUrlBase, profilePicsBaseUrl, mapDataApiUrl, userInitialCity;
let selectedRouteDetailsDiv, detailRouteName, detailRouteDescription, detailRouteMeta, detailRouteLink, mapInstructions;
let detailKingQueenDiv, kqUsername, kqDuration, kqActivityLink, kqCreatedAt;
let detailTop5TimesDiv, top5List;
let availableRoutesListDiv, recentChallengesListDiv, recentActivitiesListDiv;


// =======================================================
// NUOVO: Definizione delle icone personalizzate per la mappa
// =======================================================
const L_Icon = L.Icon.extend({
    options: {
        iconSize:     [32, 32], // Dimensioni dell'icona
        iconAnchor:   [16, 32], // Punto dell'icona che corrisponderà alla posizione del marker
        popupAnchor:  [0, -32]  // Punto da cui si aprirà il popup rispetto all'icona
    }
});

const runIcon = new L_Icon({iconUrl: '/static/icons/runner.png'});
const bikeIcon = new L_Icon({iconUrl: '/static/icons/bicycle.png'});
const hikeIcon = new L_Icon({iconUrl: '/static/icons/hiking.png'});
const defaultIcon = new L_Icon({iconUrl: '/static/icons/default.png'});

// Un oggetto per mappare facilmente il tipo di attività all'icona corrispondente
const activityIcons = {
    'Corsa': runIcon,
    'Bici': bikeIcon,
    'Hike': hikeIcon
};
// =======================================================


// Funzione per visualizzare i dettagli del percorso sotto la mappa
function displayRouteDetails(routeProps) { 
    selectedRouteDetailsDiv.style.display = 'block';
    mapInstructions.style.display = 'none';
    detailRouteName.textContent = routeProps.name;
    detailRouteDescription.textContent = routeProps.description || 'Nessuna descrizione.';
    let createdByHtml = `Creato il: ${routeProps.created_at} da <a href="${userProfileUrlBase.replace('12345', routeProps.created_by_id)}">${routeProps.created_by_username}</a>`;
    detailRouteMeta.innerHTML = `${createdByHtml}<br>Distanza: ${routeProps.distance_km ? routeProps.distance_km.toFixed(2) + ' km' : 'N/D'}`;
    detailRouteLink.href = routeDetailUrlBase.replace('12345', routeProps.id);

    if (routeProps.king_queen && routeProps.king_queen.username) {
        kqUsername.innerHTML = `<a href="${userProfileUrlBase.replace('12345', routeProps.king_queen.user_id)}" class="user-link text-dark">${routeProps.king_queen.username}</a>`;
        kqDuration.textContent = formatDuration(routeProps.king_queen.duration);
        kqActivityLink.href = activityDetailUrlBase.replace('12345', routeProps.king_queen.activity_id);
        kqCreatedAt.textContent = `Registrato il: ${routeProps.king_queen.created_at}`;
        detailKingQueenDiv.style.display = 'block';
    } else {
        detailKingQueenDiv.style.display = 'none';
    }

    top5List.innerHTML = '';
    if (routeProps.top_5_activities && routeProps.top_5_activities.length > 0) {
        routeProps.top_5_activities.forEach((activity, index) => {
            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center';
            li.innerHTML = `
                <span class="badge bg-primary rounded-pill me-2">${index + 1}</span>
                <img src="${profilePicsBaseUrl}${activity.profile_image}" class="rounded-circle me-2 profile-image-small" alt="Avatar">
                <a href="${userProfileUrlBase.replace('12345', activity.user_id)}" class="user-link text-primary flex-grow-1">${activity.username}</a>
                <span class="badge bg-info rounded-pill">${formatDuration(activity.duration)}</span>
                <a href="${activityDetailUrlBase.replace('12345', activity.activity_id)}" class="btn btn-sm btn-link p-0 ms-2" style="font-size:0.8em; vertical-align: baseline;">(Dettagli)</a>`;
            top5List.appendChild(li);
        });
        detailTop5TimesDiv.style.display = 'block';
    } else {
        detailTop5TimesDiv.style.display = 'none';
    }
}

// Funzioni per popolare le liste
function populateAvailableRoutes(routes) {
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
    recentChallengesListDiv.innerHTML = '';
    if (challenges && challenges.length > 0) {
        challenges.forEach(challenge => {
            // CORREZIONE: Link corretto alla pagina per registrare l'attività e alla classifica
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
    recentActivitiesListDiv.innerHTML = '';
    if (activities && activities.length > 0) {
        activities.forEach(activity => {
            // CORREZIONE: Link corretto all'attività
            // --- NUOVA LOGICA PER IL PULSANTE LIKE ---
            const likeButtonClass = activity.user_has_liked ? 'btn-danger' : 'btn-outline-danger';
            // L'attributo 'disabled' verrà aggiunto se l'utente non è loggato
            const isAuthenticated = document.querySelector('#navbarDropdownMenuLink') !== null;
            const disabledAttribute = isAuthenticated ? '' : 'disabled';
            // --- FINE NUOVA LOGICA ---
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
                    
                    <!-- NUOVO BLOCCO: PULSANTI E LIKE -->
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


document.addEventListener('DOMContentLoaded', function() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/js/sw.js')
            .then(function(registration) {
                //console.log('Service Worker registrato con successo:', registration);
            })
            .catch(function(error) {
                console.log('Registrazione Service Worker fallita:', error);
            });
    }

    if (typeof is_homepage_js === 'undefined' || !is_homepage_js) return;

    mainMap = L.map('mainMap');
    osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(mainMap);
    topoLayer = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenTopoMap' });
    
    // Inizializzazione variabili globali
    userProfileUrlBase = document.getElementById('user-profile-url-base').textContent;
    routeDetailUrlBase = document.getElementById('route-detail-url-base').textContent;
    activityDetailUrlBase = document.getElementById('activity-detail-url-base').textContent;
    mapDataApiUrl = document.getElementById('map-data-api-url').textContent;
    userInitialCity = document.getElementById('user-initial-city').textContent;
    profilePicsBaseUrl = document.getElementById('profile-pics-base-url').textContent;
    selectedRouteDetailsDiv = document.getElementById('selected-route-details');
    detailRouteName = document.getElementById('detail-route-name');
    detailRouteDescription = document.getElementById('detail-route-description');
    detailRouteMeta = document.getElementById('detail-route-meta');
    detailRouteLink = document.getElementById('detail-route-link');
    mapInstructions = document.getElementById('map-instructions');
    detailKingQueenDiv = document.getElementById('detail-king-queen');
    kqUsername = document.getElementById('kq-username');
    kqDuration = document.getElementById('kq-duration');
    kqActivityLink = document.getElementById('kq-activity-link');
    kqCreatedAt = document.getElementById('kq-created-at');
    detailTop5TimesDiv = document.getElementById('detail-top-5-times');
    top5List = document.getElementById('top-5-list');
    availableRoutesListDiv = document.getElementById('available-routes-list');
    recentChallengesListDiv = document.getElementById('recent-challenges-list');
    recentActivitiesListDiv = document.getElementById('recent-activities-list');
    
    markers = L.markerClusterGroup();
    mainMap.addLayer(markers);
    let selectedRouteLayer = L.geoJSON(null, { style: { color: '#007bff', weight: 6, opacity: 1 } }).addTo(mainMap);
    L.control.layers({ "Stradale": osmLayer, "Topografica": topoLayer }, { "Percorsi": markers }).addTo(mainMap);

    // Funzione principale di caricamento dati
    window.loadMapAndData = function(lat, lon, zoom = 13, city = null) {
        mainMap.setView([lat, lon], zoom);
        mainMap.eachLayer(layer => { if (layer.options.isCitySearchMarker) mainMap.removeLayer(layer); });
        if (city) L.marker([lat, lon], { isCitySearchMarker: true }).addTo(mainMap).bindPopup(`<b>${city}</b>`).openPopup();

        const loadingMsg = `<p class="text-center text-muted p-3">Caricamento...</p>`;
        const leaderboardLoadingMsg = `<li class="list-group-item text-center text-muted">Caricamento...</li>`;
        availableRoutesListDiv.innerHTML = loadingMsg;
        recentChallengesListDiv.innerHTML = loadingMsg;
        recentActivitiesListDiv.innerHTML = loadingMsg;
        document.querySelector('#top-distance-list').innerHTML = leaderboardLoadingMsg;
        document.querySelector('#top-creators-list').innerHTML = leaderboardLoadingMsg;

        const activityTypeFilter = document.querySelector('#activityTypeFilter .btn.active').dataset.type;

        fetch(`${mapDataApiUrl}?lat=${lat}&lon=${lon}&radius_km=50&activity_type=${activityTypeFilter}`)
            .then(response => response.ok ? response.json() : Promise.reject('Network response was not ok'))
            .then(data => {
                markers.clearLayers();
                data.routes.forEach(r => {
                    if (!r.coordinates.geometry.coordinates[0]) return;
                    // Per ogni percorso, aggiungi un MARKER (punto) al cluster
                    if (!r.coordinates.geometry.coordinates[0]) return; // Sicurezza
                    
                    const startPoint = r.coordinates.geometry.coordinates[0];

                    // NUOVO: Scegli l'icona giusta in base all'activity_type
                    // Se il tipo non è nella nostra mappa `activityIcons`, usa quella di default
                    const selectedIcon = activityIcons[r.activity_type] || defaultIcon;

                    // MODIFICATO: Passa l'opzione {icon: ...} quando crei il marker
                    const marker = L.marker([startPoint[1], startPoint[0]], { icon: selectedIcon });
                    
                    // Il resto del codice (popup, evento on click) rimane identico
                    let popupContent = `<b>${r.name}</b><br>Distanza: ${r.distance_km ? r.distance_km.toFixed(2) + ' km' : 'N/D'}`;
                    if (r.king_queen) {
                        popupContent += `<br><span class="badge bg-warning text-dark"><i class="bi bi-trophy-fill"></i> ${r.king_queen.username}</span>`;
                    }
                    marker.bindPopup(popupContent);

                    marker.on('click', function() {
                        selectedRouteLayer.clearLayers().addData(r.coordinates);
                        displayRouteDetails(r);
                    });

                    markers.addLayer(marker);
                    marker.bindPopup(`<b>${r.name}</b><br>${r.distance_km ? r.distance_km.toFixed(2) + ' km' : ''}`);
                    marker.on('click', () => {
                        selectedRouteLayer.clearLayers().addData(r.coordinates);
                        displayRouteDetails(r);
                    });
                    markers.addLayer(marker);
                });

                // =======================================================
                // !! ECCO LA LOGICA RIPRISTINATA !!
                // Se ci sono percorsi, adatta lo zoom. Altrimenti, usa lo zoom di default.
                if (data.routes && data.routes.length > 0) {
                    mainMap.fitBounds(markers.getBounds(), { padding: [50, 50] });
                } else {
                    mainMap.setView([lat, lon], zoom);
                }
                // =======================================================

                populateAvailableRoutes(data.routes);
                populateRecentChallenges(data.challenges);
                populateRecentActivities(data.recent_activities);
                populateLocalLeaderboards(data.local_leaderboards);

                document.getElementById('searchCityButton').disabled = false;
                document.getElementById('citySearchSpinner').style.display = 'none';
            })
            .catch(error => {
                console.error('Errore nel caricamento dati:', error);
                const errorMsg = `<p class="text-center text-danger p-3">Errore nel caricamento.</p>`;
                availableRoutesListDiv.innerHTML = errorMsg;
                recentChallengesListDiv.innerHTML = errorMsg;
                recentActivitiesListDiv.innerHTML = errorMsg;
            });

            // ===== CARICAMENTO AUTOMATICO PERCORSI CLASSICI =====
            setTimeout(() => {
                // Usa la città dell'utente o L'Aquila come default
                const userCity = document.getElementById('user-initial-city').textContent;
                const defaultCity = "L'Aquila";
                
                if (userCity && userCity.trim() !== '') {
                    loadClassicRoutes(userCity);
                } else {
                    loadClassicRoutes(defaultCity);
                }
            }, 1500); // Aspetta 1.5 secondi dopo il caricamento della pagina
    }

    // Gestori di eventi
    const citySearchInput = document.getElementById('citySearchInput');
    const citySearchButton = document.getElementById('searchCityButton');
    const citySearchSpinner = document.getElementById('citySearchSpinner');

    function searchCity(cityName) {
        if (!cityName) return;
        citySearchButton.disabled = true;
        citySearchSpinner.style.display = 'inline-block';
        fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(cityName)}&format=json&limit=1`)
            .then(response => response.json())
            .then(data => {
                if (data && data.length > 0) {
                    loadMapAndData(parseFloat(data[0].lat), parseFloat(data[0].lon), 13, data[0].display_name);
                } else {
                    alert('Città non trovata.');
                    citySearchButton.disabled = false;
                    citySearchSpinner.style.display = 'none';
                }
            }).catch(err => {
                alert('Errore di rete durante la ricerca.');
                citySearchButton.disabled = false;
                citySearchSpinner.style.display = 'none';
            });
    }

    citySearchInput.addEventListener('keypress', e => { if (e.key === 'Enter') searchCity(citySearchInput.value); });
    citySearchButton.addEventListener('click', () => searchCity(citySearchInput.value));
    
    document.querySelectorAll('#activityTypeFilter .btn').forEach(button => {
        button.addEventListener('click', function() {
            document.querySelector('#activityTypeFilter .btn.active').classList.remove('active');
            this.classList.add('active');
            const center = mainMap.getCenter();
            loadMapAndData(center.lat, center.lng, mainMap.getZoom());
        });
    });

    // Caricamento iniziale
    searchCity(userInitialCity || "Italia");
});



// In app/static/js/main.js

// Aggiungi questo blocco alla fine del file.

document.addEventListener('DOMContentLoaded', function() {
    // ... (tutto il tuo codice esistente per la mappa, etc., rimane qui) ...

    // =======================================================
    // NUOVO: GESTIONE DINAMICA DEI LIKE SULLE ATTIVITÀ
    // =======================================================
    
    // Usiamo la delegazione degli eventi per gestire i click su pulsanti
    // che potrebbero essere aggiunti dinamicamente alla pagina.
    document.body.addEventListener('click', function(event) {
        
        // Controlla se l'elemento cliccato (o un suo genitore) è un pulsante 'like'
        const likeButton = event.target.closest('.like-activity-button');
        
        if (likeButton) {
            event.preventDefault(); // Previene qualsiasi comportamento di default
            
            const activityId = likeButton.dataset.activityId;
            const likeCountSpan = likeButton.querySelector('.like-count');
            
            // Chiama la nostra API in background
            fetch(`/api/activity/${activityId}/like`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    // In futuro, per la protezione CSRF, aggiungeresti un header qui
                }
            })
            .then(response => {
                if (!response.ok) {
                    // Se la risposta non è 200 OK (es. utente non loggato, errore server)
                    // lancia un errore per essere catturato dal .catch()
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.status === 'success') {
                    // 1. Aggiorna il contatore dei like
                    likeCountSpan.textContent = data.new_like_count;
                    
                    // 2. Cambia lo stile del pulsante in base all'azione
                    if (data.action === 'liked') {
                        likeButton.classList.remove('btn-outline-danger');
                        likeButton.classList.add('btn-danger');
                    } else { // 'unliked'
                        likeButton.classList.remove('btn-danger');
                        likeButton.classList.add('btn-outline-danger');
                    }
                }
            })
            .catch(error => {
                console.error('Errore durante l-operazione di like:', error);
                // Potresti mostrare un messaggio di errore all'utente qui
                // Ad esempio, reindirizzandolo alla pagina di login se l'errore è 401 Unauthorized
                if (error.response && error.response.status === 401) {
                    window.location.href = '/login'; 
                }
            });
        }
    });
});

// ===== PERCORSI CLASSICI =====

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
                            
                            <!-- NUOVA SEZIONE: Layout a due colonne per Top Times e Pulsanti -->
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

// Funzione helper per formattare la durata in modo compatto
function formatDurationCompact(seconds) {
    if (!seconds) return 'N/A';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return hours > 0 ? `${hours}h${minutes}m` : `${minutes}m`;
}
// Funzioni helper
function getActivityColor(activityType) {
    const colors = {
        'Corsa': 'primary',
        'Ciclismo': 'success', 
        'Escursionismo': 'warning',
        'Mountain Bike': 'danger'
    };
    return colors[activityType] || 'secondary';
}

function getDifficultyColor(difficulty) {
    const colors = {
        'Easy': 'success',
        'Medium': 'warning',
        'Hard': 'danger'
    };
    return colors[difficulty] || 'secondary';
}

function formatDuration(seconds) {
    if (!seconds) return 'N/A';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}
// ===== INIZIALIZZAZIONE =====

// ESEMPIO DI CORREZIONE:
document.addEventListener('DOMContentLoaded', function() {
    // CERCA LA RIGA 591 E AGGIUNGI CONTROLLI NULL:
    const element = document.getElementById('some-element');
    if (element) {  // ← IMPORTANTE!
        //console.log(element.textContent);
    }
    
    // Service Worker registration...
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/js/sw.js')
            .then(function(registration) {
                //console.log('SW registrato:', registration);
            })
            .catch(function(error) {
                //console.log('SW registrazione fallita:', error);
            });
    }
});

// ==============================================
// ANIMAZIONI E INTERAZIONI AVANZATE PER SCOMMESSE
// ==============================================

document.addEventListener('DOMContentLoaded', function() {
    // Inizializza le animazioni solo se siamo in una pagina con scommesse
    if (document.querySelector('.bet-card') || document.querySelector('.stats-card')) {
        initBetAnimations();
        initStatsAnimations();
    }
    
    // Inizializza animazioni notifiche se siamo in quella pagina
    if (document.querySelector('.notification-item')) {
        initNotificationAnimations();
    }
});

function initBetAnimations() {
    console.log('🎯 Inizializzando animazioni scommesse...');
    
    // Animazione per pagamento scommessa
    const payButtons = document.querySelectorAll('form[action*="mark_bet_paid"] button');
    payButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            // Aggiungi effetto loading
            const originalText = this.innerHTML;
            this.innerHTML = '<span class="loading-spinner me-2"></span> Elaborazione...';
            this.disabled = true;
            this.classList.add('btn-bet-action');
            
            // Aggiungi classe di transizione
            const betCard = this.closest('.bet-card');
            if (betCard) {
                betCard.classList.add('status-transition', 'pending-to-paid');
            }
            
            // Il form si invierà automaticamente
            console.log('🔄 Pagamento scommessa in elaborazione...');
        });
    });
    
    // Effetto hover avanzato per card
    const betCards = document.querySelectorAll('.bet-card');
    betCards.forEach((card, index) => {
        // Ritardo progressivo per animazioni
        card.style.animationDelay = (index * 0.1) + 's';
        
        card.addEventListener('mouseenter', function() {
            this.style.zIndex = '10';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.zIndex = '1';
        });
    });
    
    // Animazione per click su card (se non ha già link)
    betCards.forEach(card => {
        if (!card.querySelector('a') && !card.querySelector('button')) {
            card.style.cursor = 'pointer';
            card.addEventListener('click', function(e) {
                this.style.transform = 'scale(0.98)';
                setTimeout(() => {
                    this.style.transform = '';
                }, 150);
            });
        }
    });
}

function initStatsAnimations() {
    console.log('📊 Inizializzando animazioni statistiche...');
    
    // Animazione counter per statistiche
    const statsNumbers = document.querySelectorAll('.stats-number');
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const target = entry.target;
                const finalValue = parseInt(target.textContent.replace(/,/g, ''));
                if (!target.classList.contains('animated')) {
                    target.classList.add('animated');
                    animateCounter(target, 0, finalValue, 2000);
                }
                observer.unobserve(target);
            }
        });
    }, { threshold: 0.3 });
    
    statsNumbers.forEach(number => observer.observe(number));
}

function initNotificationAnimations() {
    console.log('🔔 Inizializzando animazioni notifiche...');
    
    // Animazione per nuove notifiche
    const newNotifications = document.querySelectorAll('.notification-unread');
    newNotifications.forEach((notification, index) => {
        notification.style.animationDelay = (index * 0.2) + 's';
    });
}

// Funzione per animare counter
function animateCounter(element, start, end, duration) {
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        const value = Math.floor(progress * (end - start) + start);
        element.textContent = value.toLocaleString();
        
        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };
    window.requestAnimationFrame(step);
}

// Funzione per toast notifications (globale)
function showBetToast(message, type = 'success') {
    // Crea il toast solo se non esiste già
    if (document.querySelector('.bet-toast')) return;
    
    const toast = document.createElement('div');
    toast.className = `bet-toast alert alert-${type} alert-dismissible fade show position-fixed`;
    toast.style.cssText = `
        top: 20px;
        right: 20px;
        z-index: 9999;
        min-width: 300px;
        animation: slideInRight 0.5s ease-out;
    `;
    
    toast.innerHTML = `
        <div class="d-flex align-items-center">
            <span class="me-2">${type === 'success' ? '✅' : '❌'}</span>
            <span>${message}</span>
            <button type="button" class="btn-close ms-auto" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    document.body.appendChild(toast);
    
    // Auto-rimuovi dopo 5 secondi
    setTimeout(() => {
        if (toast.parentNode) {
            toast.remove();
        }
    }, 5000);
}

// Utility per debounce (per performance)
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Resize handler ottimizzato
const handleResize = debounce(() => {
    // Ricalcola animazioni su resize
    if (document.querySelector('.bet-card')) {
        document.querySelectorAll('.bet-card').forEach(card => {
            card.style.animation = 'none';
            setTimeout(() => {
                card.style.animation = '';
            }, 10);
        });
    }
}, 250);

window.addEventListener('resize', handleResize);

// Debug helper
window.betAnimations = {
    initBetAnimations,
    initStatsAnimations,
    initNotificationAnimations,
    showBetToast,
    animateCounter
};

console.log('🚀 Animazioni scommesse caricate!');


// TEST FINALE - esegui questo
function finalTest() {
    console.log('=== TEST FINALE ===');
    
    const section = document.getElementById('classic-routes-section');
    const container = document.getElementById('classic-routes-container');
    
    // Pulisci e mostra una card semplice ma visibile
    container.innerHTML = `
        <div class="col-12">
            <div class="card border-primary shadow">
                <div class="card-header bg-primary text-white">
                    <h4 class="mb-0">✅ TEST FUNZIONANTE</h4>
                </div>
                <div class="card-body">
                    <p class="card-text">Questa è una card di test che dovrebbe essere VISIBILE.</p>
                    <p class="card-text">Se la vedi, allora il problema è nel modo in cui generiamo le card dai dati.</p>
                </div>
                <div class="card-footer">
                    <button class="btn btn-success" onclick="loadClassicRoutes('L\\'Aquila')">
                        Carica percorsi reali
                    </button>
                </div>
            </div>
        </div>
    `;
    
    section.style.display = 'block';
    console.log('✅ Card di test creata. Dovresti vederla sopra la mappa.');
}

// Esegui:
// finalTest();