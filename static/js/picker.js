(function () {
  var el = document.getElementById('pick-map'), lat = document.getElementById('lat'), lng = document.getElementById('lng');
  if (!el || !window.L) return;
  var start = [parseFloat(lat.value), parseFloat(lng.value)], has = !isNaN(start[0]) && !isNaN(start[1]);
  var map = L.map(el).setView(has ? start : [14.28, 74.44], has ? 15 : 7); // default: coastal Karnataka
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
  var m = has ? L.marker(start).addTo(map) : null;
  function put(a, b) {
    if (m) m.setLatLng([a, b]); else m = L.marker([a, b]).addTo(map);
    lat.value = a.toFixed(6); lng.value = b.toFixed(6);
  }
  map.on('click', function (e) { put(e.latlng.lat, e.latlng.lng); });
  [lat, lng].forEach(function (i) { i.addEventListener('change', function () {
    var a = parseFloat(lat.value), b = parseFloat(lng.value);
    if (!isNaN(a) && !isNaN(b)) { put(a, b); map.setView([a, b], 15); }
  }); });
  var s = document.getElementById('place-search'), go = document.getElementById('place-go');
  function search() {
    if (!s.value.trim()) return;
    fetch('https://nominatim.openstreetmap.org/search?format=json&limit=1&q=' + encodeURIComponent(s.value))
      .then(function (r) { return r.json(); })
      .then(function (r) { if (r[0]) map.setView([+r[0].lat, +r[0].lon], 15); else alert('Place not found. Try a nearby town name.'); })
      .catch(function () { alert('Search is unavailable right now. Click the map instead.'); });
  }
  go.addEventListener('click', search);
  s.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); search(); } });
})();
