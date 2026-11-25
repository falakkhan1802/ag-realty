(function () {
  var body = document.body;

  // Mobile navigation
  var toggle = document.querySelector('.nav-toggle'), nav = document.getElementById('nav');
  if (toggle && nav) toggle.addEventListener('click', function () {
    var open = nav.classList.toggle('open');
    toggle.setAttribute('aria-expanded', open);
  });

  // Favorites (hearts on cards, Save button on detail page)
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-fav]');
    if (!b) return;
    e.preventDefault();
    if (body.dataset.loggedIn !== '1') {
      location.href = body.dataset.loginUrl + '?next=' + encodeURIComponent(location.pathname + location.search);
      return;
    }
    fetch(b.dataset.url, { method: 'POST', headers: { 'X-CSRF-Token': body.dataset.csrf } })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (d) {
        b.classList.toggle('on', d.favorited);
        b.setAttribute('aria-pressed', d.favorited);
        if (b.hasAttribute('data-label')) b.textContent = d.favorited ? 'Saved' : 'Save';
      })
      .catch(function () { alert('Could not update favorites. Please refresh and try again.'); });
  });

  // Share (native share sheet, else copy link)
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-share]');
    if (!b) return;
    var url = b.dataset.url, title = b.dataset.title;
    if (navigator.share) { navigator.share({ title: title, url: url }).catch(function () {}); return; }
    var done = function () { var t = b.textContent; b.textContent = 'Link copied'; setTimeout(function () { b.textContent = t; }, 1800); };
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(done);
    else { var i = document.createElement('input'); i.value = url; document.body.appendChild(i); i.select(); document.execCommand('copy'); i.remove(); done(); }
  });

  // Budget options change with Buy / Rent
  var BUDGETS = {
    buy: [['', 'Any budget'], ['0-2500000', 'Under ₹25 L'], ['2500000-5000000', '₹25 L – ₹50 L'], ['5000000-10000000', '₹50 L – ₹1 Cr'], ['10000000-30000000', '₹1 Cr – ₹3 Cr'], ['30000000-', 'Above ₹3 Cr']],
    rent: [['', 'Any budget'], ['0-15000', 'Under ₹15,000'], ['15000-30000', '₹15,000 – ₹30,000'], ['30000-60000', '₹30,000 – ₹60,000'], ['60000-', 'Above ₹60,000']]
  };
  var bf = document.querySelector('[data-budget-form]');
  if (bf) {
    var sel = bf.querySelector('[data-budget]');
    bf.querySelectorAll('input[name=listing_type]').forEach(function (r) {
      r.addEventListener('change', function () {
        sel.innerHTML = '';
        BUDGETS[r.value].forEach(function (o) { var op = document.createElement('option'); op.value = o[0]; op.textContent = o[1]; sel.appendChild(op); });
      });
    });
  }

  // Hero 3D tilt (pointer devices only, respects reduced motion)
  var art = document.getElementById('iso');
  if (art && window.matchMedia('(hover:hover)').matches && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    var hero = art.closest('.hero');
    hero.addEventListener('mousemove', function (e) {
      var r = hero.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
      art.style.transform = 'perspective(900px) rotateY(' + (x * 10) + 'deg) rotateX(' + (-y * 8) + 'deg)';
    });
    hero.addEventListener('mouseleave', function () { art.style.transform = ''; });
  }

  // Lightbox gallery
  var items = [].slice.call(document.querySelectorAll('[data-full]'));
  if (items.length) {
    var box = document.createElement('div');
    box.className = 'lightbox'; box.hidden = true;
    box.innerHTML = '<button class="lb-close" aria-label="Close">×</button><button class="lb-prev" aria-label="Previous">‹</button><figure><img alt=""><figcaption></figcaption></figure><button class="lb-next" aria-label="Next">›</button>';
    document.body.appendChild(box);
    var idx = 0, img = box.querySelector('img'), cap = box.querySelector('figcaption');
    var show = function (i) { idx = (i + items.length) % items.length; img.src = items[idx].dataset.full; cap.textContent = items[idx].dataset.kind || ''; cap.hidden = !items[idx].dataset.kind; };
    var open = function (i) { show(i); box.hidden = false; document.body.style.overflow = 'hidden'; };
    var close = function () { box.hidden = true; document.body.style.overflow = ''; };
    items.forEach(function (it, i) { it.addEventListener('click', function (e) { e.preventDefault(); open(i); }); });
    var all = document.querySelector('[data-open-gallery]'); if (all) all.addEventListener('click', function () { open(0); });
    box.querySelector('.lb-close').onclick = close;
    box.querySelector('.lb-prev').onclick = function () { show(idx - 1); };
    box.querySelector('.lb-next').onclick = function () { show(idx + 1); };
    box.addEventListener('click', function (e) { if (e.target === box) close(); });
    document.addEventListener('keydown', function (e) {
      if (box.hidden) return;
      if (e.key === 'Escape') close(); if (e.key === 'ArrowLeft') show(idx - 1); if (e.key === 'ArrowRight') show(idx + 1);
    });
  }
})();
