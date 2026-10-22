/* Leaflet map, checkpoint timeline and the scheduled-journey animation.
 *
 * The server never pushes positions. It stores only journey start/end/state/paused_frac;
 * every viewer computes   fraction = (serverNow - start) / (end - start)
 * using a clock offset to the server, so all browsers show the parcel at the same spot.
 */
(function () {
  "use strict";

  const escH = (v) => (window.esc ? window.esc(v) : String(v == null ? "" : v));
  const fmt = (iso) => (window.fmtDate ? window.fmtDate(iso) : iso || "");
  const clamp01 = (x) => Math.max(0, Math.min(1, x));

  // ------------------------------------------------------------ timeline
  /** opts.limit: show only the latest N with a "Show full history" toggle */
  function renderTimeline(container, events, opts) {
    if (typeof container === "string") container = document.getElementById(container);
    if (!container) return;
    opts = opts || {};
    const list = (events || []).slice().reverse(); // latest first
    const next = container.nextElementSibling;
    if (next && next.classList.contains("tl-more")) next.remove();
    if (!list.length) {
      container.innerHTML = '<li class="muted small">No checkpoints yet.</li>';
      return;
    }
    const limit = opts.limit && list.length > opts.limit + 1 ? opts.limit : 0;
    const expanded = container.dataset.expanded === "1";
    const ago = window.timeAgo || (() => "");
    container.innerHTML = list
      .map((ev, i) => {
        const cls = (i === 0 ? "current" : "done") + (limit && !expanded && i >= limit ? " tl-hidden" : "");
        const rel = ago(ev.timestamp);
        return (
          '<li class="tl-item ' + cls + '">' +
          '<span class="tl-dot"></span>' +
          '<div class="tl-head"><span class="tl-status">' + escH(ev.status) + "</span>" +
          (rel ? '<span class="tl-ago">' + escH(rel) + "</span>" : "") + "</div>" +
          (ev.location_name ? '<div class="tl-loc">📍 ' + escH(ev.location_name) + "</div>" : "") +
          '<div class="tl-time">' + escH(fmt(ev.timestamp)) + "</div>" +
          (ev.notes ? '<div class="tl-notes">' + escH(ev.notes) + "</div>" : "") +
          "</li>"
        );
      })
      .join("");
    if (limit) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tl-more";
      const hiddenCount = list.length - limit;
      btn.textContent = expanded ? "Show less" : "Show full history (" + hiddenCount + " more)";
      btn.setAttribute("aria-expanded", expanded ? "true" : "false");
      btn.addEventListener("click", () => {
        container.dataset.expanded = expanded ? "0" : "1";
        renderTimeline(container, events, opts);
      });
      container.after(btn);
    }
  }

  // ------------------------------------------------------------ geometry
  function _segLen(a, b) {
    const toRad = Math.PI / 180;
    const midLat = ((a[0] + b[0]) / 2) * toRad;
    const dx = (b[1] - a[1]) * Math.cos(midLat);
    const dy = b[0] - a[0];
    return Math.sqrt(dx * dx + dy * dy);
  }

  function _cumulative(path) {
    const cum = [0];
    for (let i = 1; i < path.length; i++) cum.push(cum[i - 1] + _segLen(path[i - 1], path[i]));
    return cum;
  }

  function pointAtFraction(path, cum, frac) {
    frac = clamp01(frac);
    const total = cum[cum.length - 1];
    if (!path.length) return { point: null, traveled: [], remaining: [] };
    if (path.length === 1 || total === 0) return { point: path[0], traveled: [path[0]], remaining: path.slice() };
    const target = total * frac;
    // binary search the segment containing target
    let lo = 0, hi = cum.length - 1;
    while (lo < hi - 1) {
      const mid = (lo + hi) >> 1;
      if (cum[mid] <= target) lo = mid; else hi = mid;
    }
    const segLen = cum[hi] - cum[lo];
    const t = segLen > 0 ? (target - cum[lo]) / segLen : 0;
    const a = path[lo], b = path[hi];
    const point = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    return {
      point,
      traveled: path.slice(0, lo + 1).concat([point]),
      remaining: [point].concat(path.slice(hi)),
    };
  }

  // ------------------------------------------------------------ icons
  const RIDER_SVG =
    '<svg class="rider-body" viewBox="0 0 64 64" aria-hidden="true">' +
    // parcel box
    '<rect x="6" y="20" width="18" height="16" rx="2.5" fill="#f59e0b"/>' +
    '<path d="M6 26h18M15 20v16" stroke="#b45309" stroke-width="1.6"/>' +
    // scooter body
    '<path d="M10 40h24l6-10h8" fill="none" stroke="#0f766e" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<path d="M44 30l4 12" stroke="#062925" stroke-width="3.5" stroke-linecap="round"/>' +
    '<path d="M40 26h8" stroke="#062925" stroke-width="3.5" stroke-linecap="round"/>' +
    // rider
    '<circle cx="32" cy="12" r="5.5" fill="#062925"/>' +
    '<path d="M30 18l-3 12h9l6 6" fill="none" stroke="#062925" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<path d="M31 21l9 6" stroke="#062925" stroke-width="3.5" stroke-linecap="round"/>' +
    // wheels
    '<circle cx="14" cy="46" r="6" fill="#fff" stroke="#062925" stroke-width="3.5"/>' +
    '<circle cx="48" cy="46" r="6" fill="#fff" stroke="#062925" stroke-width="3.5"/>' +
    "</svg>";

  function riderIcon(state) {
    return L.divIcon({
      className: "",
      html: '<div class="rider-wrap ' + escH(state || "") + '"><span class="rider-ping"></span><div class="rider-badge">' + RIDER_SVG + "</div></div>",
      iconSize: [56, 56],
      iconAnchor: [28, 28],
      popupAnchor: [0, -26],
    });
  }
  const cpIcon = (latest) => L.divIcon({ className: "", html: '<div class="cp-marker' + (latest ? " latest" : "") + '"></div>', iconSize: [14, 14], iconAnchor: [7, 7] });
  const pinIcon = () =>
    L.divIcon({ className: "", html: '<div class="loc-pin"><span class="pin-pulse"></span><span class="pin-shape"></span></div>', iconSize: [34, 44], iconAnchor: [17, 42], popupAnchor: [0, -38] });
  const startIcon = () => L.divIcon({ className: "", html: '<div class="route-end start"></div>', iconSize: [16, 16], iconAnchor: [8, 8] });
  const finishIcon = () => L.divIcon({ className: "", html: '<div class="route-end finish">🏁</div>', iconSize: [34, 34], iconAnchor: [17, 17] });

  function popupHtml(title, lines) {
    return '<div class="map-popup"><strong>' + escH(title) + "</strong>" + lines.filter(Boolean).map((l) => "<span>" + escH(l) + "</span>").join("") + "</div>";
  }

  // ------------------------------------------------------------ map
  function initTrackingMap(elId, opts) {
    const el = typeof elId === "string" ? document.getElementById(elId) : elId;
    if (!el || !window.L) return null;
    opts = opts || {};

    const map = L.map(el, { scrollWheelZoom: false, zoomControl: true, attributionControl: true, worldCopyJump: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    map.on("focus", () => map.scrollWheelZoom.enable());
    map.on("blur", () => map.scrollWheelZoom.disable());

    const reduced = !!window.PREFERS_REDUCED_MOTION;
    const layers = { route: L.layerGroup().addTo(map), checkpoints: L.layerGroup().addTo(map), current: L.layerGroup().addTo(map) };
    let glowLine = null, traveledLine = null, remainingLine = null, parcel = null;
    let rafId = null, lastTick = 0, flipped = false;
    let routeKey = "";

    const st = { events: [], current: null, route: null, cum: null, journey: {}, serverOffset: 0, label: opts.label || "Your parcel" };

    function setPayload(p) {
      st.events = Array.isArray(p.events) ? p.events : [];
      st.current = p.current || null;
      st.route = Array.isArray(p.route_path) && p.route_path.length >= 2 ? p.route_path : null;
      st.cum = st.route ? _cumulative(st.route) : null;
      st.journey = p.journey || {};
      if (p.server_now) {
        const s = Date.parse(p.server_now);
        if (!isNaN(s)) st.serverOffset = s - Date.now();
      }
    }

    function journeyActive() {
      return !!st.route && ["moving", "paused", "arrived"].indexOf(st.journey.state) !== -1;
    }

    function currentFraction() {
      const j = st.journey || {};
      if (!st.route) return 0;
      if (j.state === "arrived") return 1;
      if (j.state === "paused") return clamp01(j.paused_frac || 0);
      if (j.state === "moving") {
        const s = Date.parse(j.start), e = Date.parse(j.end);
        if (isNaN(s) || isNaN(e) || e <= s) return 0;
        return clamp01((Date.now() + st.serverOffset - s) / (e - s));
      }
      return 0;
    }

    function drawRoute() {
      layers.route.clearLayers();
      glowLine = traveledLine = remainingLine = parcel = null;
      if (!st.route) return;
      remainingLine = L.polyline(st.route, { color: "#7c8f93", weight: 4, opacity: 0.85, dashArray: "1 9", lineCap: "round" }).addTo(layers.route);
      glowLine = L.polyline([], { color: "#0f766e", weight: 11, opacity: 0.16, lineCap: "round", lineJoin: "round" }).addTo(layers.route);
      traveledLine = L.polyline([], { color: "#0f766e", weight: 5, opacity: 1, lineCap: "round", lineJoin: "round" }).addTo(layers.route);
      L.marker(st.route[0], { icon: startIcon(), keyboard: false }).bindPopup(popupHtml("Departure", ["Start of scheduled route"])).addTo(layers.route);
      L.marker(st.route[st.route.length - 1], { icon: finishIcon(), keyboard: false }).bindPopup(popupHtml("Destination", ["End of scheduled route"])).addTo(layers.route);
      if (journeyActive()) {
        parcel = L.marker(st.route[0], { icon: riderIcon(st.journey.state), zIndexOffset: 1000, keyboard: false })
          .bindPopup(popupHtml(st.label, ["Scheduled position — not a live GPS fix"]))
          .addTo(layers.route);
        flipped = false;
      }
      updateParcel(true);
    }

    function drawCheckpoints() {
      layers.checkpoints.clearLayers();
      const pts = st.events.filter((e) => e.lat != null && e.lng != null);
      pts.forEach((ev, i) => {
        L.marker([ev.lat, ev.lng], { icon: cpIcon(i === pts.length - 1), keyboard: false })
          .bindPopup(popupHtml(ev.status, [ev.location_name, fmt(ev.timestamp), ev.notes]))
          .addTo(layers.checkpoints);
      });
      if (!st.route && pts.length > 1) {
        L.polyline(pts.map((e) => [e.lat, e.lng]), { color: "#0f766e", weight: 3, opacity: 0.7, dashArray: "8 8" }).addTo(layers.checkpoints);
      }
    }

    function drawCurrentMarker() {
      layers.current.clearLayers();
      if (journeyActive()) return;
      const c = st.current;
      if (c && c.lat != null && c.lng != null) {
        L.marker([c.lat, c.lng], { icon: pinIcon(), zIndexOffset: 900, keyboard: false })
          .bindPopup(popupHtml(c.status || "Current location", ["Last reported checkpoint"]))
          .addTo(layers.current);
      }
    }

    function updateParcel(force) {
      if (!st.route || !st.cum) return;
      const frac = journeyActive() ? currentFraction() : 0;
      const res = pointAtFraction(st.route, st.cum, frac);
      if (traveledLine) traveledLine.setLatLngs(frac > 0 ? res.traveled : []);
      if (glowLine) glowLine.setLatLngs(frac > 0 ? res.traveled : []);
      if (remainingLine) remainingLine.setLatLngs(res.remaining);
      if (parcel && res.point) {
        parcel.setLatLng(res.point);
        const behind = pointAtFraction(st.route, st.cum, frac - 0.004).point;
        const ahead = pointAtFraction(st.route, st.cum, frac + 0.004).point;
        const west = ahead && behind ? ahead[1] < behind[1] - 1e-9 : false;
        if (force || west !== flipped) {
          flipped = west;
          const body = parcel.getElement() && parcel.getElement().querySelector(".rider-body");
          if (body) body.classList.toggle("flip", west);
        }
      }
    }

    function loop(now) {
      rafId = null;
      if (st.journey.state !== "moving") return;
      // the parcel moves slowly (hours/days) — repaint a few times per second, not every frame
      const interval = reduced ? 5000 : 200;
      if (now - lastTick >= interval) {
        lastTick = now;
        updateParcel(false);
      }
      rafId = requestAnimationFrame(loop);
    }

    function startLoop() {
      if (rafId) cancelAnimationFrame(rafId);
      rafId = null;
      if (st.journey.state === "moving" && st.route) rafId = requestAnimationFrame(loop);
    }

    function fit() {
      const pts = [];
      if (st.route) st.route.forEach((p) => pts.push(p));
      st.events.forEach((e) => { if (e.lat != null && e.lng != null) pts.push([e.lat, e.lng]); });
      if (st.current && st.current.lat != null && st.current.lng != null) pts.push([st.current.lat, st.current.lng]);
      if (!pts.length) map.setView([20, 0], 2);
      else if (pts.length === 1 || L.latLngBounds(pts).getNorthEast().equals(L.latLngBounds(pts).getSouthWest())) map.setView(pts[0], 9);
      else map.fitBounds(L.latLngBounds(pts).pad(0.15));
    }

    function render(refit) {
      drawRoute();
      drawCheckpoints();
      drawCurrentMarker();
      if (refit) fit();
      startLoop();
    }

    function keyOf() {
      const r = st.route;
      const evs = st.events.filter((e) => e.lat != null).length;
      return (r ? r.length + ":" + r[0].join(",") + ":" + r[r.length - 1].join(",") : "none") + "|" + evs;
    }

    setPayload(opts);
    routeKey = keyOf();
    render(true);

    if ("ResizeObserver" in window) {
      let t = null;
      new ResizeObserver(() => { clearTimeout(t); t = setTimeout(() => map.invalidateSize(), 120); }).observe(el);
    }
    document.addEventListener("visibilitychange", () => { if (!document.hidden) { updateParcel(true); startLoop(); } });

    return {
      map,
      update(payload) {
        setPayload(Object.assign({}, payload));
        const k = keyOf();
        render(k !== routeKey); // only re-fit when the geometry changed, so a visitor's zoom is kept
        routeKey = k;
      },
      fit,
      getFraction: currentFraction,
    };
  }

  Object.assign(window, { renderTimeline, initTrackingMap, pointAtFraction, _segLen, _cumulative });
})();
