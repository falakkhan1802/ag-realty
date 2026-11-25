(function () {
  var M = window.PROPERTY_MAP, el = document.getElementById('map');
  if (!M || !el || !window.L) return;

  var CATS = {
    school: ['Schools', '#3b6ea5'], hospital: ['Hospitals', '#c0392b'], supermarket: ['Supermarkets', '#2e8b57'],
    restaurant: ['Restaurants', '#d98324'], bank: ['Banks', '#6b4fa0'], gym: ['Gyms', '#16808d'],
    bus_stop: ['Bus stops', '#7a8794'], metro: ['Metro stations', '#b0306a'], other: ['Other useful places', '#8a6d2f']
  };
  var map = L.map(el, { scrollWheelZoom: false }).setView([M.lat, M.lng], 15);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
  map.on('focus', function () { map.scrollWheelZoom.enable(); });
  map.on('blur', function () { map.scrollWheelZoom.disable(); });

  var home = L.marker([M.lat, M.lng], { title: M.title }).addTo(map).bindPopup('<b>' + esc(M.title) + '</b><br>' + (M.exact ? 'Property location' : 'Approximate area'));
  if (!M.exact) L.circle([M.lat, M.lng], { radius: 450, color: '#B8924A', weight: 2, fillOpacity: .12 }).addTo(map);

  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function dist(a, b, c, d) {
    var R = 6371000, r = Math.PI / 180, dLa = (c - a) * r, dLo = (d - b) * r;
    var x = Math.sin(dLa / 2) * Math.sin(dLa / 2) + Math.cos(a * r) * Math.cos(c * r) * Math.sin(dLo / 2) * Math.sin(dLo / 2);
    return Math.round(2 * R * Math.asin(Math.sqrt(x)));
  }
  function fmt(m) { return m == null ? '' : (m >= 1000 ? (m / 1000).toFixed(1) + ' km' : m + ' m'); }

  var places = {}; Object.keys(CATS).forEach(function (k) { places[k] = []; });
  (window.STORED_FACILITIES || []).forEach(function (f) {
    var c = places[f.category] ? f.category : 'other';
    var d = f.distance_m != null ? f.distance_m : (f.lat != null ? dist(M.lat, M.lng, f.lat, f.lng) : null);
    places[c].push({ name: f.name, lat: f.lat, lng: f.lng, d: d });
  });

  function classify(t) {
    if (t.amenity === 'school' || t.amenity === 'college' || t.amenity === 'kindergarten') return 'school';
    if (t.amenity === 'hospital' || t.amenity === 'clinic') return 'hospital';
    if (t.shop === 'supermarket' || t.shop === 'mall') return 'supermarket';
    if (t.amenity === 'restaurant' || t.amenity === 'cafe') return 'restaurant';
    if (t.amenity === 'bank') return 'bank';
    if (t.leisure === 'fitness_centre' || t.amenity === 'gym') return 'gym';
    if (t.highway === 'bus_stop' || t.amenity === 'bus_station') return 'bus_stop';
    if (t.station === 'subway' || t.railway === 'station' || t.railway === 'subway_entrance') return 'metro';
    return 'other';
  }
  var q = '[out:json][timeout:25];(' + [
    '[amenity~"^(school|college|hospital|clinic|restaurant|cafe|bank|pharmacy|bus_station)$"]', '[shop~"^(supermarket|mall)$"]',
    '[leisure=fitness_centre]', '[highway=bus_stop]', '[railway~"^(station|subway_entrance)$"]', '[leisure=park]'
  ].map(function (f) { return 'nwr(around:1500,' + M.lat + ',' + M.lng + ')' + f + ';'; }).join('') + ');out center 200;';

  var layers = {}, active = {};
  function render() {
    var panel = document.getElementById('nearby'), tools = document.getElementById('map-filters'), html = '', chips = '', any = false;
    Object.keys(layers).forEach(function (k) { map.removeLayer(layers[k]); });
    Object.keys(CATS).forEach(function (k) {
      var list = places[k].filter(function (p) { return p.name; });
      list.sort(function (a, b) { return (a.d == null ? 1e9 : a.d) - (b.d == null ? 1e9 : b.d); });
      places[k] = list.slice(0, 8);
      if (!places[k].length) return;
      any = true;
      if (!(k in active)) active[k] = true;
      var g = L.layerGroup();
      places[k].forEach(function (p) {
        if (p.lat == null) return;
        L.circleMarker([p.lat, p.lng], { radius: 7, color: '#fff', weight: 2, fillColor: CATS[k][1], fillOpacity: 1 }).addTo(g)
          .bindPopup('<b>' + esc(p.name) + '</b><br>' + CATS[k][0] + (p.d != null ? ' · ' + fmt(p.d) : '') +
            '<br><a target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=' + p.lat + ',' + p.lng + '">Directions</a>');
      });
      layers[k] = g; if (active[k]) g.addTo(map);
      chips += '<label class="chip-t"><input type="checkbox" data-cat="' + k + '"' + (active[k] ? ' checked' : '') + '><i style="background:' + CATS[k][1] + '"></i>' + CATS[k][0] + '</label>';
      html += '<div class="n-cat"><h4><i style="background:' + CATS[k][1] + '"></i>' + CATS[k][0] + '</h4><ul>' +
        places[k].slice(0, 5).map(function (p, i) {
          return '<li><button type="button" data-cat="' + k + '" data-i="' + i + '">' + esc(p.name) + '</button><span>' + fmt(p.d) + '</span></li>';
        }).join('') + '</ul></div>';
    });
    tools.innerHTML = chips;
    panel.innerHTML = any ? html : '<p class="note">No nearby places were found for this spot. The admin can add them manually.</p>';
  }
  document.getElementById('map-filters').addEventListener('change', function (e) {
    var k = e.target.dataset.cat; if (!k) return; active[k] = e.target.checked;
    if (layers[k]) { if (e.target.checked) layers[k].addTo(map); else map.removeLayer(layers[k]); }
  });
  document.getElementById('nearby').addEventListener('click', function (e) {
    var b = e.target.closest('button[data-cat]'); if (!b) return;
    var p = places[b.dataset.cat][+b.dataset.i]; if (p && p.lat != null) { map.flyTo([p.lat, p.lng], 17); el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
  });
  render();

  fetch('https://overpass-api.de/api/interpreter', { method: 'POST', body: 'data=' + encodeURIComponent(q), headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var seen = {};
      (j.elements || []).forEach(function (n) {
        var t = n.tags || {}, lat = n.lat || (n.center && n.center.lat), lng = n.lon || (n.center && n.center.lon);
        if (!lat || !t.name) return;
        var c = classify(t), key = c + t.name;
        if (seen[key]) return; seen[key] = 1;
        places[c].push({ name: t.name, lat: lat, lng: lng, d: dist(M.lat, M.lng, lat, lng) });
      });
      render();
    })
    .catch(function () {
      var p = document.getElementById('nearby');
      if (!p.querySelector('.n-cat')) p.innerHTML = '<p class="note">Nearby places could not be loaded right now. Zoom the map or try again later.</p>';
    });
})();
