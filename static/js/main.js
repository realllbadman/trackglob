/* Shared UI helpers — vanilla JS, no framework. */
(function () {
  "use strict";

  const REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.PREFERS_REDUCED_MOTION = REDUCED;

  // ------------------------------------------------------------ escaping
  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      try { window.lucide.createIcons(); } catch (e) { /* ignore */ }
    }
  }

  // ------------------------------------------------------------ toast
  function toast(msg, type) {
    let wrap = document.querySelector(".toast-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "toast-wrap";
      wrap.setAttribute("aria-live", "polite");
      document.body.appendChild(wrap);
    }
    const el = document.createElement("div");
    el.className = "toast" + (type ? " " + type : "");
    const icon = type === "success" ? "check-circle-2" : type === "error" ? "alert-circle" : "info";
    el.innerHTML = '<i data-lucide="' + icon + '"></i><span>' + esc(msg) + "</span>";
    wrap.appendChild(el);
    refreshIcons();
    requestAnimationFrame(() => el.classList.add("show"));
    setTimeout(() => {
      el.classList.remove("show");
      setTimeout(() => el.remove(), 400);
    }, 3200);
  }

  // ------------------------------------------------------------ status helpers
  function statusClass(status) {
    const s = String(status || "").toLowerCase();
    if (s.includes("deliver") && !s.includes("out for")) return "delivered";
    if (s.includes("out for")) return "outfor";
    if (/delay|hold|custom|exception/.test(s)) return "delayed";
    if (/transit|departed|arrived|picked|moving/.test(s)) return "transit";
    return "pending";
  }

  function statusBadge(status, pulse) {
    const cls = statusClass(status);
    const doPulse = pulse && cls !== "delivered";
    return '<span class="badge ' + cls + '"><span class="dot' + (doPulse ? " pulse" : "") + '"></span>' + esc(status || "Pending") + "</span>";
  }

  /** 0 Picked Up · 1 In Transit · 2 Out for Delivery · 3 Delivered; -1 = not yet picked up */
  function progressIndex(status) {
    const s = String(status || "").toLowerCase();
    if (s.includes("deliver") && !s.includes("out for")) return 3;
    if (s.includes("out for")) return 2;
    if (/transit|hub|departed|arrived|custom|hold|delay|exception/.test(s)) return 1;
    if (s.includes("picked")) return 0;
    return -1;
  }

  const STATUS_COPY = {
    pending: { icon: "clipboard-list", text: "Shipment registered — awaiting pickup." },
    transit: { icon: "truck", text: "Your parcel is moving through our network." },
    outfor: { icon: "map-pin", text: "Your parcel is on its final leg to the receiver." },
    delivered: { icon: "package-check", text: "Your parcel has been delivered." },
    delayed: { icon: "alert-triangle", text: "Your parcel is temporarily held. We'll update you as soon as it moves." },
  };

  function renderStatusBanner(el, status, sub) {
    if (!el) return;
    const cls = statusClass(status);
    const copy = STATUS_COPY[cls];
    el.className = "status-banner " + cls;
    el.innerHTML =
      '<div class="sb-icon"><i data-lucide="' + copy.icon + '"></i></div>' +
      "<div><h2>" + esc(status) + "</h2><p>" + esc(copy.text) + "</p></div>" +
      (sub ? '<div class="sb-right">' + sub + "</div>" : "");
    refreshIcons();
  }

  function renderProgressSteps(el, status) {
    if (!el) return;
    const idx = progressIndex(status);
    const cls = statusClass(status);
    const steps = [
      { label: "Picked Up", sub: "Collected", icon: "package" },
      { label: "In Transit", sub: "On the way", icon: "truck" },
      { label: "Out for Delivery", sub: "Final leg", icon: "map-pin" },
      { label: "Delivered", sub: "Completed", icon: "home" },
    ];
    el.classList.toggle("is-delivered", idx === 3);
    el.classList.toggle("is-delayed", cls === "delayed");
    el.innerHTML = steps
      .map((st, i) => {
        const state = i < idx ? "done" : i === idx ? "current" : "";
        const icon = state === "done" || (state === "current" && idx === 3) ? "check" : st.icon;
        return (
          '<div class="step ' + state + '"' + (state === "current" ? ' aria-current="step"' : "") + ">" +
          '<div class="node"><i data-lucide="' + icon + '"></i></div>' +
          '<div class="s-text"><div class="s-label">' + esc(st.label) + '</div><div class="s-sub">' + esc(st.sub) + "</div></div></div>"
        );
      })
      .join("");
    refreshIcons();
  }

  // ------------------------------------------------------------ formatting
  function fmtDate(iso, withTime) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d)) return String(iso);
    const opts = { year: "numeric", month: "short", day: "numeric" };
    if (withTime !== false) { opts.hour = "2-digit"; opts.minute = "2-digit"; }
    return d.toLocaleString(undefined, opts);
  }

  /** "5 min ago", "3 h ago", "2 days ago" */
  function timeAgo(iso) {
    const t = Date.parse(iso);
    if (isNaN(t)) return "";
    const s = Math.round((Date.now() - t) / 1000);
    if (s < 0) return "just now";
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + " min ago";
    if (s < 86400) return Math.floor(s / 3600) + " h ago";
    const d = Math.floor(s / 86400);
    return d === 1 ? "yesterday" : d + " days ago";
  }

  /** Time remaining until an ISO date: "2 d 4 h", "5 h 12 min", "8 min". Null if past/invalid. */
  function timeLeft(iso, nowMs) {
    const t = Date.parse(iso);
    if (isNaN(t)) return null;
    let s = Math.round((t - (nowMs || Date.now())) / 1000);
    if (s <= 0) return null;
    const d = Math.floor(s / 86400); s -= d * 86400;
    const h = Math.floor(s / 3600); s -= h * 3600;
    const m = Math.floor(s / 60);
    if (d) return d + " d " + h + " h";
    if (h) return h + " h " + m + " min";
    return Math.max(1, m) + " min";
  }

  // ------------------------------------------------------------ recent searches (per-browser convenience only)
  const RECENT_KEY = "recentTracking";
  function getRecent() {
    try { const v = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); return Array.isArray(v) ? v.slice(0, 5) : []; }
    catch (e) { return []; }
  }
  function rememberTracking(tn) {
    if (!/^[A-Z0-9-]{4,32}$/.test(tn)) return;
    try { localStorage.setItem(RECENT_KEY, JSON.stringify([tn].concat(getRecent().filter((x) => x !== tn)).slice(0, 5))); }
    catch (e) { /* storage unavailable */ }
  }
  function clearRecent() {
    try { localStorage.removeItem(RECENT_KEY); } catch (e) { /* ignore */ }
    initRecent();
  }
  function initRecent() {
    document.querySelectorAll("[data-recent]").forEach((box) => {
      const list = getRecent();
      if (!list.length) { box.hidden = true; box.innerHTML = ""; return; }
      box.hidden = false;
      box.innerHTML = '<span class="rc-label"><i data-lucide="history"></i> Recent</span>' +
        list.map((tn) => '<a class="rc-chip mono" href="/track/' + encodeURIComponent(tn) + '">' + esc(tn) + "</a>").join("") +
        '<button type="button" class="rc-clear" onclick="clearRecent()" aria-label="Clear recent tracking numbers">Clear</button>';
    });
    refreshIcons();
  }

  async function shareTracking(tn) {
    const url = window.location.origin + "/track/" + encodeURIComponent(tn);
    if (navigator.share) {
      try { await navigator.share({ title: "Shipment " + tn, url }); return; } catch (e) { if (e && e.name === "AbortError") return; }
    }
    copyText(url);
  }

  // ------------------------------------------------------------ actions
  /** Split pasted text into unique, upper-cased tracking numbers. */
  function parseTrackingList(text) {
    const seen = new Set();
    return String(text || "").toUpperCase().split(/[\s,;]+/).map((t) => t.replace(/[^A-Z0-9-]/g, ""))
      .filter((t) => t && !seen.has(t) && seen.add(t));
  }

  function shakeForm(form, input) {
    if (input) input.focus();
    form.classList.remove("shake"); void form.offsetWidth; form.classList.add("shake");
  }

  function navigateTracking(list) {
    if (list.length === 1) window.location.href = "/track/" + encodeURIComponent(list[0]);
    else window.location.href = "/track?tn=" + encodeURIComponent(list.join(","));
  }

  function goTrack(e, form) {
    if (e) e.preventDefault();
    const input = form.querySelector("input[name=tn]");
    const list = parseTrackingList(input ? input.value : "");
    if (!list.length) {
      toast("Please enter a tracking number", "error");
      shakeForm(form, input);
      return false;
    }
    navigateTracking(list.slice(0, 10));
    return false;
  }

  function goTrackMulti(e, form) {
    if (e) e.preventDefault();
    const ta = form.querySelector("textarea");
    const list = parseTrackingList(ta.value);
    if (!list.length) { toast("Enter at least one tracking number", "error"); shakeForm(form, ta); return false; }
    if (list.length > 10) { toast("You can track up to 10 numbers at once", "error"); shakeForm(form, ta); return false; }
    navigateTracking(list);
    return false;
  }

  async function newsletterSubmit(e, form) {
    e.preventDefault();
    const input = form.querySelector("input[type=email]");
    const email = (input.value || "").trim();
    if (!email) return toast("Please enter your email", "error");
    const btn = form.querySelector("button");
    if (btn) btn.disabled = true;
    try {
      const res = await fetch("/api/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) throw new Error("bad");
      input.value = "";
      toast("Thanks — you're subscribed!", "success");
    } catch (err) {
      toast("Please enter a valid email address", "error");
    } finally {
      if (btn) btn.disabled = false;
    }
    return false;
  }

  async function logout() {
    try { await fetch("/api/customer/logout", { method: "POST" }); } catch (e) { /* ignore */ }
    window.location.href = "/";
  }

  async function copyText(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch (err) { /* ignore */ }
      ta.remove();
    }
    toast("Copied " + text, "success");
    if (btn) {
      btn.classList.add("copied");
      setTimeout(() => btn.classList.remove("copied"), 1200);
    }
  }

  async function apiJSON(url, opts) {
    opts = opts || {};
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    if (opts.body && typeof opts.body !== "string") {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(url, Object.assign({}, opts, { headers, credentials: "same-origin" }));
    let data = null;
    try { data = await res.json(); } catch (e) { /* empty */ }
    if (!res.ok) {
      let detail = data && data.detail;
      if (Array.isArray(detail)) {
        detail = detail.map((d) => {
          const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "";
          return (field ? String(field).replace(/_/g, " ") + ": " : "") + (d.msg || "invalid");
        }).join("; ");
      }
      const err = new Error(detail || "Request failed (" + res.status + ")");
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  // ------------------------------------------------------------ motion
  function initReveal() {
    const els = document.querySelectorAll(".reveal, .stagger");
    document.querySelectorAll(".stagger").forEach((group) => {
      Array.from(group.children).forEach((child, i) => {
        child.style.transitionDelay = i * 80 + "ms";
      });
    });
    if (REDUCED || !("IntersectionObserver" in window)) {
      els.forEach((el) => el.classList.add("in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    els.forEach((el) => io.observe(el));
  }

  function animateCount(el) {
    const target = parseFloat(el.dataset.count);
    const decimals = parseInt(el.dataset.decimals || "0", 10);
    const suffix = el.dataset.suffix || "";
    const prefix = el.dataset.prefix || "";
    const fmt = (v) => prefix + v.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + suffix;
    if (REDUCED || isNaN(target)) {
      el.textContent = fmt(isNaN(target) ? 0 : target);
      return;
    }
    const dur = 1400;
    const t0 = performance.now();
    function frame(now) {
      const p = Math.min(1, (now - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(target * eased);
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function initCountUp() {
    const els = document.querySelectorAll("[data-count]");
    if (!els.length) return;
    if (!("IntersectionObserver" in window)) return els.forEach(animateCount);
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            animateCount(entry.target);
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.4 }
    );
    els.forEach((el) => io.observe(el));
  }

  function initHeroRotator() {
    const slides = document.querySelectorAll(".hero-slide");
    const texts = document.querySelectorAll(".hero-text");
    const dots = document.querySelectorAll(".hero-dots button");
    if (slides.length < 2) return;
    let idx = 0;
    let timer = null;
    function show(i) {
      idx = (i + slides.length) % slides.length;
      slides.forEach((s, n) => {
        s.classList.toggle("active", n === idx);
        // restart Ken-Burns on the incoming slide
        const bg = s.querySelector(".hero-slide-bg");
        if (bg && n === idx) { bg.style.animation = "none"; void bg.offsetWidth; bg.style.animation = ""; }
      });
      texts.forEach((t, n) => t.classList.toggle("active", n === idx));
      dots.forEach((d, n) => {
        d.classList.toggle("active", n === idx);
        d.setAttribute("aria-selected", n === idx ? "true" : "false");
      });
      // carry the typed tracking number over to the newly visible slide
      const typed = Array.from(document.querySelectorAll(".hero-text input[name=tn]")).map((x) => x.value).find(Boolean);
      if (typed) texts.forEach((t) => { const inp = t.querySelector("input[name=tn]"); if (inp) inp.value = typed; });
    }
    function start() {
      if (REDUCED) return;
      stop();
      timer = setInterval(() => {
        // don't rotate away while the visitor is typing a tracking number
        const active = document.activeElement;
        if (active && active.name === "tn" && active.closest(".hero")) return;
        show(idx + 1);
      }, 6000);
    }
    function stop() { if (timer) clearInterval(timer); timer = null; }
    dots.forEach((d, n) => d.addEventListener("click", () => { show(n); start(); }));
    document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
    start();
  }

  function initProgressBar() {
    const bar = document.getElementById("progress-bar");
    if (!bar) return;
    let ticking = false;
    function update() {
      const h = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.width = (h > 0 ? (window.scrollY / h) * 100 : 0) + "%";
      ticking = false;
    }
    window.addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
    update();
  }

  function initPreloader() {
    const pl = document.getElementById("preloader");
    if (!pl) return;
    let seen = false;
    try { seen = sessionStorage.getItem("preloaderSeen") === "1"; } catch (e) { /* ignore */ }
    const hide = () => {
      pl.classList.add("done");
      setTimeout(() => pl.remove(), 600);
      try { sessionStorage.setItem("preloaderSeen", "1"); } catch (e) { /* ignore */ }
    };
    if (seen || REDUCED) { pl.remove(); return; }
    if (document.readyState === "complete") setTimeout(hide, 250);
    else window.addEventListener("load", () => setTimeout(hide, 250));
    setTimeout(hide, 2500); // failsafe
  }

  function initNavHide() {
    const nav = document.querySelector(".nav");
    if (!nav) return;
    let last = window.scrollY;
    let ticking = false;
    function update() {
      const y = window.scrollY;
      nav.classList.toggle("scrolled", y > 8);
      const menuOpen = document.querySelector(".mobile-menu.open");
      if (!menuOpen && y > 240 && y > last + 4) nav.classList.add("nav-hidden");
      else if (y < last - 4 || y < 240) nav.classList.remove("nav-hidden");
      last = y;
      ticking = false;
    }
    window.addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
    nav.addEventListener("focusin", () => nav.classList.remove("nav-hidden"));
  }

  function initMobileMenu() {
    const btn = document.querySelector(".hamburger");
    const menu = document.querySelector(".mobile-menu");
    const backdrop = document.querySelector(".menu-backdrop");
    if (!btn || !menu) return;
    function setOpen(open) {
      menu.classList.toggle("open", open);
      btn.classList.toggle("open", open);
      if (backdrop) backdrop.classList.toggle("open", open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      menu.setAttribute("aria-hidden", open ? "false" : "true");
      document.body.style.overflow = open ? "hidden" : "";
    }
    btn.addEventListener("click", () => setOpen(!menu.classList.contains("open")));
    if (backdrop) backdrop.addEventListener("click", () => setOpen(false));
    menu.querySelectorAll("[data-close-menu], a").forEach((el) => el.addEventListener("click", () => setOpen(false)));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
  }

  function initPasswordToggles() {
    document.querySelectorAll(".toggle-pw").forEach((btn) => {
      btn.addEventListener("click", () => {
        const input = btn.parentElement.querySelector("input");
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
        btn.innerHTML = '<i data-lucide="' + (show ? "eye-off" : "eye") + '"></i>';
        refreshIcons();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const y = document.getElementById("year");
    if (y) y.textContent = new Date().getFullYear();
    refreshIcons();
    initReveal();
    initCountUp();
    initHeroRotator();
    initProgressBar();
    initPreloader();
    initNavHide();
    initMobileMenu();
    initPasswordToggles();
    initRecent();
  });

  Object.assign(window, {
    esc,
    refreshIcons,
    toast,
    statusClass,
    statusBadge,
    progressIndex,
    renderStatusBanner,
    renderProgressSteps,
    fmtDate,
    timeAgo,
    timeLeft,
    rememberTracking,
    clearRecent,
    shareTracking,
    parseTrackingList,
    goTrack,
    goTrackMulti,
    newsletterSubmit,
    logout,
    copyText,
    apiJSON,
  });
})();
