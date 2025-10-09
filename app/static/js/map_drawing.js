// static/js/map_drawing.js

document.addEventListener('DOMContentLoaded', function() {
    const mapDrawingElement = document.getElementById('map_drawing');
    if (mapDrawingElement) {
        var mapDrawing = L.map('map_drawing').setView([45.4642, 9.1900], 13);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(mapDrawing);

        var drawnItems = new L.FeatureGroup();
        mapDrawing.addLayer(drawnItems);

        var drawControl = new L.Control.Draw({
            edit: {
                featureGroup: drawnItems,
                poly: { allowIntersection: false }
            },
            draw: {
                polygon: { allowIntersection: false, showArea: true },
                marker: false, circlemarker: false, rectangle: false, circle: false,
            }
        });
        mapDrawing.addControl(drawControl);

        function updateCoordinatesInput(layer) {
            if (layer) {
                document.getElementById('coordinates').value = JSON.stringify(layer.toGeoJSON());
            } else {
                document.getElementById('coordinates').value = '';
            }
            if (typeof validateMapOrGpx === 'function') {
                validateMapOrGpx();
            }
        }

        mapDrawing.on(L.Draw.Event.CREATED, function (event) {
            var layer = event.layer;
            if (layer instanceof L.Polyline) {
                drawnItems.clearLayers();
                drawnItems.addLayer(layer);
                updateCoordinatesInput(layer);
                document.getElementById('gpx_file').value = '';
            }
        });

        mapDrawing.on(L.Draw.Event.EDITED, function (event) {
            var layers = event.layers;
            layers.eachLayer(function (layer) {
                if (layer instanceof L.Polyline) {
                    updateCoordinatesInput(layer);
                }
            });
        });

        mapDrawing.on(L.Draw.Event.DELETED, function (event) {
            updateCoordinatesInput(null);
        });

        document.getElementById('gpx_file').addEventListener('change', function() {
            if (this.files.length > 0) {
                document.getElementById('coordinates').value = '';
                drawnItems.clearLayers();
            }
            if (typeof validateMapOrGpx === 'function') {
                validateMapOrGpx();
            }
        });
    }
});