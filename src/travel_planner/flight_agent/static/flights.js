// flights.js — the Flights view: search form, results, popular destinations.
// Loaded after the page shell's script, which provides $, esc, ICONS, svg and showView().

document.addEventListener("viewchange", () => closePop());   // switching tabs closes any open picker

// ================= flight search =================
const UI = {
  chev: '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
  swap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h15l-4-4M20 16H5l4 4"/></svg>',
};

// Shown before the user types, and usable even without the Duffel token.
const POPULAR = [
  { code: "BLR", city: "Bengaluru", name: "Kempegowda International Airport", type: "airport", country: "IN" },
  { code: "DEL", city: "New Delhi", name: "Indira Gandhi International Airport", type: "airport", country: "IN" },
  { code: "BOM", city: "Mumbai", name: "Chhatrapati Shivaji Maharaj International Airport", type: "airport", country: "IN" },
  { code: "MAA", city: "Chennai", name: "Chennai International Airport", type: "airport", country: "IN" },
  { code: "HYD", city: "Hyderabad", name: "Rajiv Gandhi International Airport", type: "airport", country: "IN" },
  { code: "CCU", city: "Kolkata", name: "Netaji Subhas Chandra Bose International Airport", type: "airport", country: "IN" },
  { code: "GOI", city: "Goa", name: "Dabolim Airport", type: "airport", country: "IN" },
  { code: "DXB", city: "Dubai", name: "Dubai International Airport", type: "airport", country: "AE" },
  { code: "SIN", city: "Singapore", name: "Changi Airport", type: "airport", country: "SG" },
  { code: "LHR", city: "London", name: "Heathrow Airport", type: "airport", country: "GB" },
];
const CABIN = { economy: "Economy", premium_economy: "Premium Economy", business: "Business", first: "First" };

// ---- dates are plain "YYYY-MM-DD" strings, always in local time ----
const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parse = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const addDays = (s, n) => { const d = parse(s); d.setDate(d.getDate() + n); return iso(d); };
const TODAY = iso(new Date());
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dayName = s => parse(s).toLocaleDateString("en-US", { weekday: "long" });
const shortDate = s => parse(s).toLocaleDateString("en-US", { weekday: "short", day: "numeric", month: "short" });

// ---- the whole form lives in one state object; renderRows() draws it ----
// From/To start empty: the traveller picks both cities.
const freshState = () => ({
  trip: "oneway",                       // oneway | round | multi
  legs: [{ from: null, to: null, date: addDays(TODAY, 7) }],
  ret: null,                            // return date (round trip only)
  adults: 1, children: 0, infants: 0,
  cabin: "economy",
});
const S = freshState();

const paxTotal = () => S.adults + S.children + S.infants;
function paxText() {
  const p = [];
  p.push(`${S.adults} Adult${S.adults > 1 ? "s" : ""}`);
  if (S.children) p.push(`${S.children} Child${S.children > 1 ? "ren" : ""}`);
  if (S.infants) p.push(`${S.infants} Infant${S.infants > 1 ? "s" : ""}`);
  return p.join(", ");
}

function placeCell(i, end) {
  const p = S.legs[i][end];
  const swap = end === "to"
    ? `<button type="button" class="swap" data-act="swap" data-leg="${i}" aria-label="Swap From and To">${UI.swap}</button>` : "";
  const body = p
    ? `<div class="val">${esc(p.city)}</div><div class="hint">${esc(p.code)}, ${esc(p.name)}</div>`
    : `<div class="val" style="color:var(--muted)">Select city</div><div class="hint">Airport or city</div>`;
  return `<div class="cell" role="button" tabindex="0" data-act="place" data-leg="${i}" data-end="${end}">
    ${swap}<div class="lbl">${end === "from" ? "From" : "To"}</div>${body}</div>`;
}

function dateCell(i) {
  const d = S.legs[i].date, min = i ? S.legs[i - 1].date : TODAY;
  const [, m, day] = d.split("-");
  return `<div class="cell" role="button" tabindex="0" data-act="date">
    <div class="lbl">Departure ${UI.chev}</div>
    <div class="val">${+day} <small>${MON[+m - 1]}'${d.slice(2, 4)}</small></div>
    <div class="hint">${dayName(d)}</div>
    <input type="date" class="date-input" data-leg="${i}" value="${d}" min="${min}" tabindex="-1" aria-label="Departure date" /></div>`;
}

function returnCell() {
  const r = S.ret, min = S.legs[0].date;
  const body = r
    ? (() => { const [, m, day] = r.split("-");
        return `<button type="button" class="clear-ret" data-act="clear-ret" aria-label="Remove return">×</button>
          <div class="val">${+day} <small>${MON[+m - 1]}'${r.slice(2, 4)}</small></div><div class="hint">${dayName(r)}</div>`; })()
    : `<div class="ghost">Tap to add a return date</div>`;
  return `<div class="cell" role="button" tabindex="0" data-act="date">
    <div class="lbl">Return ${UI.chev}</div>${body}
    <input type="date" class="date-input" data-ret="1" value="${r || ""}" min="${min}" tabindex="-1" aria-label="Return date" /></div>`;
}

const paxCell = () => `<div class="cell" role="button" tabindex="0" data-act="pax">
    <div class="lbl">Travellers ${UI.chev}</div>
    <div class="val" id="paxVal">${paxTotal()}</div>
    <div class="hint" id="paxHint">${paxTotal() === S.adults ? (S.adults > 1 ? "Adults" : "Adult") : "Travellers"}</div></div>`;

const cabinCell = () => `<div class="cell" role="button" tabindex="0" data-act="cabin">
    <div class="lbl">Cabin Class ${UI.chev}</div><div class="val mid" id="cabinVal">${CABIN[S.cabin]}</div></div>`;

function renderRows() {
  const multi = S.trip === "multi";
  let html = `<div class="fx-row main" style="${multi ? "grid-template-columns:1.35fr 1.35fr 1fr 1fr 1fr" : ""}">
    ${placeCell(0, "from")}${placeCell(0, "to")}${dateCell(0)}${multi ? "" : returnCell()}${paxCell()}${cabinCell()}</div>`;
  if (multi) {
    for (let i = 1; i < S.legs.length; i++) {
      html += `<div class="fx-row multi">${placeCell(i, "from")}${placeCell(i, "to")}${dateCell(i)}
        <button type="button" class="rm-leg" data-act="rm-leg" data-leg="${i}" aria-label="Remove flight ${i + 1}"
          ${S.legs.length <= 2 ? "disabled style='visibility:hidden'" : ""}>×</button></div>`;
    }
    if (S.legs.length < 5) html += `<button type="button" class="add-leg" data-act="add-leg">+ Add another city</button>`;
  }
  $("rows").innerHTML = html;
}

function setTrip(trip) {
  S.trip = trip;
  document.querySelector(`input[name=trip][value=${trip}]`).checked = true;
  if (trip !== "round") S.ret = null;
  if (trip === "round" && !S.ret) S.ret = addDays(S.legs[0].date, 3);
  if (trip === "multi" && S.legs.length < 2)
    S.legs.push({ from: S.legs[0].to, to: null, date: addDays(S.legs[0].date, 2) });
  if (trip !== "multi") S.legs = [S.legs[0]];
  renderRows();
}
document.querySelectorAll("input[name=trip]").forEach(r => r.onchange = () => setTrip(r.value));

// ---- popovers: one at a time, anchored inside the clicked cell ----
let pop = null;
function closePop() {
  if (!pop) return;
  pop.cell.classList.remove("open");
  pop.el.remove();
  pop = null;
}
function openPop(cell, html, right = false) {
  closePop();
  const el = document.createElement("div");
  el.className = "pop" + (right ? " right" : "");
  el.innerHTML = html;
  cell.appendChild(el);
  cell.classList.add("open");
  pop = { el, cell };
  return el;
}
document.addEventListener("mousedown", e => { if (pop && !pop.cell.contains(e.target)) closePop(); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && pop) { const c = pop.cell; closePop(); c.focus(); } });

// Place search: popular list first, then live Duffel suggestions as you type.
const suggestCache = {};
function placePop(cell, i, end) {
  const el = openPop(cell, `<input type="text" placeholder="Type a city or airport" aria-label="${end === "from" ? "From" : "To"}" />
    <ul class="sugs" role="listbox"></ul>`);
  const input = el.querySelector("input"), list = el.querySelector("ul");
  let items = [], hl = 0, timer = null, note = "";

  const draw = () => {
    const q = input.value.trim().toUpperCase();
    const opts = [...items];
    if (/^[A-Z]{3}$/.test(q) && !opts.some(p => p.code === q))
      opts.push({ code: q, city: q, name: "Use this airport code", type: "code" });
    items = opts;
    hl = Math.min(hl, Math.max(opts.length - 1, 0));
    list.innerHTML = (note ? `<li class="msg">${esc(note)}</li>` : "") + (opts.length ? opts.map((p, k) => `
      <li role="option" data-k="${k}" class="${k === hl ? "hl" : ""}">
        <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${ICONS[p.type === "city" ? "hotel" : "plane"]}</svg>
        <div><div class="nm">${esc(p.city)}${p.country ? `, ${esc(p.country)}` : ""}</div><div class="ds">${esc(p.name)}</div></div>
        <span class="cd">${esc(p.code)}</span></li>`).join("")
      : (input.value.trim().length >= 2 && !note ? `<li class="msg">No airports found. Try another name or a 3-letter code.</li>` : ""));
  };
  const pick = p => {
    const place = { code: p.code, city: p.city, name: p.type === "code" ? p.code : p.name, type: p.type };
    S.legs[i][end] = place;
    if (end === "to" && S.legs[i + 1] && !S.legs[i + 1].from) S.legs[i + 1].from = place;
    closePop(); renderRows();
    if (end === "from" && !S.legs[i].to) document.querySelector(`[data-act=place][data-leg="${i}"][data-end=to]`)?.click();
  };
  const search = async () => {
    const q = input.value.trim().toLowerCase();
    note = "";
    if (q.length < 2) { items = POPULAR.filter(p => p.city.toLowerCase().startsWith(q) || !q); draw(); return; }
    if (!suggestCache[q]) {
      try {
        const r = await fetch("/api/places?q=" + encodeURIComponent(q));
        const d = await r.json();
        if (!r.ok) { note = "Live airport search isn't set up yet. You can still type a 3-letter airport code."; }
        suggestCache[q] = d.places || [];
      } catch (_) { suggestCache[q] = []; }
    }
    if (input.value.trim().toLowerCase() !== q) return;          // a newer keystroke won
    const local = POPULAR.filter(p => (p.city + " " + p.code).toLowerCase().includes(q));
    const live = suggestCache[q];
    items = live.length ? live : local;
    hl = 0; draw();
  };
  input.oninput = () => { clearTimeout(timer); timer = setTimeout(search, 200); };
  input.onkeydown = e => {
    if (e.key === "ArrowDown") { hl = Math.min(hl + 1, items.length - 1); draw(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { hl = Math.max(hl - 1, 0); draw(); e.preventDefault(); }
    else if (e.key === "Enter") { e.preventDefault(); if (items[hl]) pick(items[hl]); }
  };
  list.onmousedown = e => { const li = e.target.closest("li[data-k]"); if (li) { e.preventDefault(); pick(items[+li.dataset.k]); } };
  items = POPULAR; draw(); input.focus();
}

function paxPop(cell) {
  const rows = [
    ["adults", "Adults", "12 years and above"],
    ["children", "Children", "2 to 11 years"],
    ["infants", "Infants", "Under 2 years, on an adult's lap"],
  ];
  const el = openPop(cell, rows.map(([k, t, d]) => `<div class="ctr"><div><div class="t">${t}</div><div class="d">${d}</div></div>
    <div class="step"><button type="button" data-k="${k}" data-d="-1" aria-label="Fewer ${t}">−</button>
    <output data-o="${k}">${S[k]}</output>
    <button type="button" data-k="${k}" data-d="1" aria-label="More ${t}">+</button></div></div>`).join("")
    + `<button type="button" class="btn-navy done">Done</button>`, true);
  const sync = () => {
    rows.forEach(([k]) => {
      el.querySelector(`[data-o=${k}]`).textContent = S[k];
      const min = k === "adults" ? 1 : 0;
      const max = k === "infants" ? S.adults : 9;
      el.querySelector(`[data-k=${k}][data-d="-1"]`).disabled = S[k] <= min;
      el.querySelector(`[data-k=${k}][data-d="1"]`).disabled = S[k] >= max || paxTotal() >= 9;
    });
    $("paxVal").textContent = paxTotal();
    $("paxHint").textContent = paxTotal() === S.adults ? (S.adults > 1 ? "Adults" : "Adult") : "Travellers";
  };
  el.onclick = e => {
    const b = e.target.closest("button[data-k]");
    if (b) { S[b.dataset.k] += +b.dataset.d; S.infants = Math.min(S.infants, S.adults); sync(); }
    if (e.target.closest(".done")) closePop();
  };
  sync();
}

// Small line icons for the cabin perks.
const PERK = {
  legroom: '<path d="M7 4v9a3 3 0 0 0 3 3h6"/><path d="M16 16v4M5 20h14"/>',
  baggage: '<rect x="6" y="7" width="12" height="13" rx="2"/><path d="M9 7V4h6v3M10 11v5M14 11v5"/>',
  meals:   '<path d="M4 12h16a8 8 0 0 1-16 0Z"/><path d="M9 4c0 1.5 1 1.5 1 3M13 4c0 1.5 1 1.5 1 3"/>',
  lounge:  '<path d="M5 11V8a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v3"/><path d="M3 18v-5a2 2 0 0 1 4 0v1h10v-1a2 2 0 0 1 4 0v5Z"/><path d="M5 18v2M19 18v2"/>',
  comfort: '<path d="M6 5l3 9h8"/><path d="M9 14l-1 5M17 14v5M4 19h16"/>',
  dining:  '<path d="M4 17a8 8 0 0 1 16 0Z"/><path d="M2 20h20M12 6v3"/>',
  suite:   '<rect x="6" y="3" width="12" height="18" rx="1"/><circle cx="15" cy="12" r="1"/>',
  wine:    '<path d="M8 3h8l-1 6a3 3 0 0 1-6 0Z"/><path d="M12 12v8M9 21h6"/>',
  service: '<circle cx="12" cy="7" r="3.5"/><path d="M5 21a7 7 0 0 1 14 0"/><path d="M10 14l2 2 2-2"/>',
};
const perkSvg = n => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PERK[n]}</svg>`;

// Flat seat illustrations, one per cabin (drawn for this app).
const SEAT_BLUE = "#3f7fe0", SEAT_DARK = "#2a5fb8", SEAT_LIGHT = "#dfe9f7";
const SEATS = {
  economy: `<rect x="25" y="6" width="22" height="36" rx="6" fill="${SEAT_BLUE}"/>
    <rect x="28" y="9" width="16" height="7" rx="2" fill="#fff"/>
    <rect x="18" y="38" width="36" height="10" rx="4" fill="${SEAT_DARK}"/>
    <rect x="15" y="30" width="7" height="16" rx="3" fill="${SEAT_LIGHT}"/>
    <path d="M26 48v8M46 48v8M22 56h28" stroke="#9aa9bb" stroke-width="3" stroke-linecap="round"/>`,
  premium_economy: `<rect x="23" y="4" width="26" height="38" rx="7" fill="${SEAT_BLUE}"/>
    <rect x="27" y="7" width="18" height="8" rx="2" fill="#fff"/>
    <rect x="14" y="37" width="44" height="11" rx="4" fill="${SEAT_DARK}"/>
    <rect x="10" y="28" width="9" height="18" rx="3" fill="${SEAT_LIGHT}"/>
    <rect x="53" y="28" width="9" height="18" rx="3" fill="${SEAT_LIGHT}"/>
    <path d="M58 46l8 8" stroke="${SEAT_BLUE}" stroke-width="5" stroke-linecap="round"/>
    <path d="M24 48v8M48 48v8M20 56h32" stroke="#9aa9bb" stroke-width="3" stroke-linecap="round"/>`,
  business: `<rect x="4" y="18" width="16" height="38" rx="4" fill="${SEAT_LIGHT}"/>
    <rect x="7" y="22" width="10" height="6" rx="1.5" fill="#fff"/>
    <path d="M24 8l12-3 7 34-12 3Z" fill="${SEAT_BLUE}"/>
    <path d="M26 9l8-2 1.6 7-8 2Z" fill="#fff"/>
    <rect x="28" y="38" width="36" height="10" rx="4" fill="${SEAT_DARK}"/>
    <path d="M62 44l6 8" stroke="${SEAT_BLUE}" stroke-width="5" stroke-linecap="round"/>
    <path d="M34 48v8M56 48v8" stroke="#9aa9bb" stroke-width="3" stroke-linecap="round"/>`,
  first: `<path d="M4 14h14v42H4Z" fill="${SEAT_LIGHT}"/>
    <path d="M4 14q34-10 68 0v6H4Z" fill="${SEAT_LIGHT}"/>
    <rect x="7" y="19" width="8" height="5" rx="1.5" fill="#fff"/>
    <rect x="16" y="36" width="54" height="11" rx="5" fill="${SEAT_BLUE}"/>
    <rect x="19" y="30" width="15" height="8" rx="3" fill="#fff"/>
    <rect x="16" y="45" width="54" height="5" rx="2.5" fill="${SEAT_DARK}"/>
    <path d="M22 50v6M64 50v6" stroke="#9aa9bb" stroke-width="3" stroke-linecap="round"/>`,
};
const seatSvg = k => `<svg class="seat" viewBox="0 0 76 64" aria-hidden="true">${SEATS[k]}</svg>`;

const CABIN_CARDS = [
  { k: "economy",         t: "Economy",         perks: [] },
  { k: "premium_economy", t: "Premium Economy", perks: [["legroom", "Extra Legroom"], ["baggage", "Extra Baggage"], ["meals", "Premium Meals"]] },
  { k: "business",        t: "Business Class",  perks: [["lounge", "Luxury Lounges"], ["comfort", "Cabin Comfort"], ["dining", "Premium Dining"]] },
  { k: "first",           t: "First Class",     perks: [["suite", "Private Suites"], ["wine", "Fine Dining"], ["service", "Highly Personalised Service"]] },
];

function cabinPop(cell) {
  const el = openPop(cell, `<div class="pop-ttl">Choose cabin class</div>` + CABIN_CARDS.map(c => `
    <label class="cab"><input type="radio" name="cabinopt" value="${c.k}" ${c.k === S.cabin ? "checked" : ""} />
      <div><div class="hd"><span class="rd"></span>${c.t}</div>
        ${c.perks.length ? `<div class="perks">${c.perks.map(([i, t]) => `<span class="perk">${perkSvg(i)}${t}</span>`).join("")}</div>` : ""}</div>
      ${seatSvg(c.k)}</label>`).join("")
    + `<div class="cab-note">Perks vary by airline and route.</div>`, true);
  el.classList.add("cabin");
  el.onchange = e => { S.cabin = e.target.value; $("cabinVal").textContent = CABIN[S.cabin]; closePop(); };
}

// One click handler for every cell and button in the rows.
$("rows").addEventListener("click", e => {
  if (e.target.closest(".pop")) return;
  const t = e.target.closest("[data-act]");
  if (!t) return;
  const i = +t.dataset.leg || 0;
  switch (t.dataset.act) {
    case "swap": {
      e.stopPropagation();
      const L = S.legs[i]; [L.from, L.to] = [L.to, L.from]; renderRows(); break;
    }
    case "clear-ret": setTrip("oneway"); break;
    case "place": if (pop?.cell !== t) placePop(t, i, t.dataset.end); break;
    case "date": {
      closePop();
      const input = t.querySelector(".date-input");
      try { input.showPicker(); } catch (_) { input.focus(); }
      break;
    }
    case "pax": if (pop?.cell !== t) paxPop(t); break;
    case "cabin": if (pop?.cell !== t) cabinPop(t); break;
    case "rm-leg": S.legs.splice(i, 1); renderRows(); break;
    case "add-leg": {
      const last = S.legs[S.legs.length - 1];
      S.legs.push({ from: last.to, to: null, date: addDays(last.date, 2) }); renderRows(); break;
    }
  }
});
$("rows").addEventListener("keydown", e => {
  if ((e.key === "Enter" || e.key === " ") && e.target.matches(".cell")) { e.preventDefault(); e.target.click(); }
});
$("rows").addEventListener("change", e => {
  const inp = e.target.closest(".date-input");
  if (!inp || !inp.value) return;
  if (inp.dataset.ret) { S.ret = inp.value; setTrip("round"); return; }
  const i = +inp.dataset.leg;
  S.legs[i].date = inp.value;
  for (let k = i + 1; k < S.legs.length; k++)          // keep later flights in order
    if (S.legs[k].date < S.legs[k - 1].date) S.legs[k].date = S.legs[k - 1].date;
  if (S.ret && S.ret < S.legs[0].date) S.ret = S.legs[0].date;
  renderRows();
});

// ---- popular destinations: click a card to fly there ----
// Photos are from Wikimedia Commons (downloaded once, served locally); each
// licence requires the credit shown under "Photo credits".
const CC = "https://commons.wikimedia.org/w/index.php?curid=";
const DESTINATIONS = {
  domestic: [
    { img: "goa",      city: "Goa",        tag: "Beaches & nightlife",    code: "GOI", name: "Dabolim Airport",                          by: "iMahesh", lic: "CC BY-SA 4.0", src: 151673985 },
    { img: "jaipur",   city: "Jaipur",     tag: "The Pink City",          code: "JAI", name: "Jaipur International Airport",             by: "Chainwit.", lic: "CC BY-SA 4.0", src: 120750436 },
    { img: "srinagar", city: "Srinagar",   tag: "Dal Lake & the Himalayas", code: "SXR", name: "Sheikh ul-Alam International Airport",  by: "Suhail Skindar Sofi", lic: "CC BY-SA 4.0", src: 78425112 },
    { img: "kochi",    city: "Kochi",      tag: "Kerala backwaters",      code: "COK", name: "Cochin International Airport",             by: "Augustus Binu", lic: "CC BY-SA 3.0", src: 28310294 },
    { img: "leh",      city: "Leh",        tag: "Monasteries of Ladakh",  code: "IXL", name: "Kushok Bakula Rimpochee Airport",          by: "Aksveer", lic: "CC BY-SA 4.0", src: 76046385 },
    { img: "andaman",  city: "Port Blair", tag: "Andaman Islands",        code: "IXZ", name: "Veer Savarkar International Airport",      by: "Harvinder Chandigarh", lic: "CC BY-SA 4.0", src: 47825254 },
    { img: "udaipur",  city: "Udaipur",    tag: "City of lakes",          code: "UDR", name: "Maharana Pratap Airport",                  by: "Flicka", lic: "CC BY-SA 3.0", src: 1133566 },
    { img: "varanasi", city: "Varanasi",   tag: "Ghats of the Ganges",    code: "VNS", name: "Lal Bahadur Shastri International Airport", by: "Ken Wieland", lic: "CC BY-SA 2.0", src: 7711423 },
  ],
  international: [
    { img: "dubai",     city: "Dubai",     tag: "Skyline & desert",       code: "DXB", name: "Dubai International Airport",           by: "Imran Shahabuddin", lic: "CC BY 2.0", src: 77350165 },
    { img: "singapore", city: "Singapore", tag: "The garden city",        code: "SIN", name: "Changi Airport",                        by: "Supanut Arunoprayote", lic: "CC BY 4.0", src: 86347540 },
    { img: "bangkok",   city: "Bangkok",   tag: "Temples & street food",  code: "BKK", name: "Suvarnabhumi Airport",                  by: "Mastertongapollo", lic: "CC BY-SA 4.0", src: 156207072 },
    { img: "bali",      city: "Bali",      tag: "Temples & rice terraces", code: "DPS", name: "Ngurah Rai International Airport",     by: "LukeTriton", lic: "CC BY-SA 4.0", src: 118993252 },
    { img: "maldives",  city: "Maldives",  tag: "Island resorts",         code: "MLE", name: "Velana International Airport",          by: "Priyaflorenceshah", lic: "CC BY-SA 4.0", src: 64964873 },
    { img: "paris",     city: "Paris",     tag: "Art, food & the Eiffel Tower", code: "CDG", name: "Charles de Gaulle Airport",       by: "Benh LIEU SONG", lic: "Public domain", src: 48220385 },
    { img: "london",    city: "London",    tag: "Royal history & the Thames", code: "LHR", name: "Heathrow Airport",                  by: "Fuzzypiggy", lic: "CC BY-SA 3.0", src: 35601800 },
    { img: "sydney",    city: "Sydney",    tag: "Harbour & beaches",      code: "SYD", name: "Sydney Kingsford Smith Airport",        by: "Bernard Spragg", lic: "CC0", src: 70521604 },
  ],
};
let region = "domestic";

function renderDestinations() {
  const list = DESTINATIONS[region];
  $("pdGrid").innerHTML = list.map((d, k) => `
    <button type="button" class="pd-card" data-k="${k}" aria-label="Fly to ${d.city}">
      <img src="/flights/static/destinations/${d.img}.jpg" alt="" loading="lazy" />
      <span class="shade"></span><span class="cd">${d.code}</span>
      <span class="txt"><div class="nm">${d.city}</div><div class="tg">${d.tag}</div></span>
    </button>`).join("");
  document.querySelectorAll("[data-region]").forEach(b => {
    b.classList.toggle("on", b.dataset.region === region);
    b.setAttribute("aria-pressed", b.dataset.region === region);
  });
}
// Credits for all 16 photos, whichever tab is showing.
$("pdCredits").innerHTML = [...DESTINATIONS.domestic, ...DESTINATIONS.international].map(d =>
  `<li>${d.city}: <a href="${CC}${d.src}" target="_blank" rel="noopener">photo</a> by ${esc(d.by)}, ${d.lic}</li>`).join("");

document.querySelectorAll("[data-region]").forEach(b => b.onclick = () => { region = b.dataset.region; renderDestinations(); });
$("pdGrid").onclick = e => {
  const card = e.target.closest(".pd-card");
  if (!card) return;
  const d = DESTINATIONS[region][+card.dataset.k];
  const leg = S.legs[0];
  leg.to = { code: d.code, city: d.city, name: d.name, type: "airport" };
  if (leg.from?.code === d.code) leg.from = null;          // can't fly Goa -> Goa
  closePop(); renderRows();
  $("fx").scrollIntoView({ behavior: "smooth", block: "start" });
  // Nothing to fly from yet? Open the From picker so the search is one step away.
  if (!leg.from) setTimeout(() => document.querySelector("[data-act=place][data-leg='0'][data-end=from]")?.click(), 350);
};
renderDestinations();

// ---- search + results ----
let offers = [], sortBy = "price", nonstopOnly = false, lastQuery = null, page = 1;
const PER_PAGE = 10;

function buildLegs() {
  if (S.trip === "round")
    return [S.legs[0], { from: S.legs[0].to, to: S.legs[0].from, date: S.ret }];
  return S.legs;
}
function validate(legs) {
  for (const [k, l] of legs.entries()) {
    const n = legs.length > 1 ? ` for flight ${k + 1}` : "";
    if (!l.from || !l.to) return `Choose where you're flying from and to${n}.`;
    if (l.from.code === l.to.code) return `From and To can't be the same${n}.`;
  }
  if (S.trip === "round" && !S.ret) return "Choose a return date.";
  return null;
}

$("fx").onsubmit = async e => {
  e.preventDefault();
  closePop();
  const legs = buildLegs();
  const problem = validate(legs);
  if (problem) return showState(problem, true);

  const fare = document.querySelector("input[name=fare]:checked").value;
  lastQuery = { legs, pax: paxText(), cabin: CABIN[S.cabin], fare };
  $("searchBtn").disabled = true;
  $("searchBtn").textContent = "SEARCHING…";
  $("results").innerHTML = `<div class="state">Checking airlines… this can take up to 20 seconds.</div>`
    + '<div class="skel"></div>'.repeat(3);
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const r = await fetch("/api/flights/search", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        legs: legs.map(l => ({ origin: l.from.code, destination: l.to.code, date: l.date })),
        adults: S.adults, children: S.children, infants: S.infants, cabin: S.cabin, fare,
      }),
    });
    if (r.status === 401) { window.location.href = "/login"; return; }
    const d = await r.json();
    if (!r.ok) return showState(d.error || "Search failed.", true);
    offers = d.offers || []; page = 1;
    renderResults();
  } catch (_) {
    showState("Couldn't reach the server. Is it still running?", true);
  } finally {
    $("searchBtn").disabled = false;
    $("searchBtn").textContent = "SEARCH";
  }
};

function showState(msg, isErr) {
  $("results").innerHTML = `<div class="card state"><span class="${isErr ? "err" : ""}">${esc(msg)}</span></div>`;
}

const hm = s => (s || "").slice(11, 16);                    // "2026-10-15T06:15:00" -> "06:15"
const dur = m => m == null ? "" : `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
const dayDiff = (a, b) => Math.round((parse(b.slice(0, 10)) - parse(a.slice(0, 10))) / 864e5);
const money = (n, cur) => {
  // en-IN gives Indian digit grouping for rupees: ₹1,23,456
  try { return new Intl.NumberFormat(cur === "INR" ? "en-IN" : undefined, { style: "currency", currency: cur, maximumFractionDigits: 0 }).format(n); }
  catch (_) { return `${cur} ${Math.round(n).toLocaleString()}`; }
};

function sliceHtml(s) {
  const segs = s.segments;
  const first = segs[0]?.carrier || {};
  const nums = segs.map(g => `${esc(g.carrier.code || "")} ${esc(g.flight_number || "")}`).join(" · ");
  const ops = [...new Set(segs.filter(g => g.operator?.name && g.operator.name !== g.carrier.name)
    .map(g => g.operator.name))];
  const logo = first.logo
    ? `<img src="${esc(first.logo)}" alt="" onerror="this.replaceWith(document.createTextNode('${esc(first.code || "")}'))" />`
    : esc(first.code || "✈");
  const plus = s.depart && s.arrive ? dayDiff(s.depart, s.arrive) : 0;
  const via = segs.slice(0, -1).map(g => g.destination.code).join(", ");
  const dots = segs.slice(0, -1).map((_, k) => `<i style="left:${((k + 1) / segs.length) * 100}%"></i>`).join("");
  return `<div class="sl">
    <div class="air"><span class="logo-b">${logo}</span>
      <div><div class="n">${esc(first.name || "Airline")}</div><div class="f">${nums}</div>
      ${ops.length ? `<div class="op">Operated by ${esc(ops.join(", "))}</div>` : ""}</div></div>
    <div class="times">
      <div><div class="tm">${hm(s.depart)}</div><div class="ap">${esc(s.origin.code)}</div></div>
      <div class="path"><div>${dur(s.duration_min)}</div><div class="ln">${dots}</div>
        <div class="st ${s.stops ? "" : "ns"}">${s.stops ? `${s.stops} stop${s.stops > 1 ? "s" : ""} · ${esc(via)}` : "Non-stop"}</div></div>
      <div class="end"><div class="tm">${hm(s.arrive)}${plus > 0 ? `<sup>+${plus}</sup>` : ""}</div><div class="ap">${esc(s.destination.code)}</div></div>
    </div></div>`;
}

function detailsHtml(o) {
  return o.slices.flatMap(s => s.segments).map(g => `<div class="dseg">
    <div><b>${esc(g.origin.code)} → ${esc(g.destination.code)}</b></div>
    <div class="c">${esc(g.carrier.name || "")} ${esc(g.carrier.code || "")} ${esc(g.flight_number || "")}${
      g.operator?.name && g.operator.name !== g.carrier.name ? ` · operated by ${esc(g.operator.name)}` : ""}</div>
    <div>${esc((g.depart || "").slice(0, 10))} · ${hm(g.depart)}–${hm(g.arrive)} · ${dur(g.duration_min)}</div></div>`).join("");
}

// "Showing 11–20 of 92" + ‹ Prev 1 … 4 5 6 … 10 Next ›
function pagerHtml(start, count, total, pages) {
  const info = `<div class="pg-info">Showing ${start + 1}–${start + count} of ${total} flights</div>`;
  if (pages === 1) return `<nav class="pager">${info}</nav>`;
  const nums = [...new Set([1, page - 1, page, page + 1, pages])].filter(n => n >= 1 && n <= pages).sort((a, b) => a - b);
  let btns = "", prev = 0;
  for (const n of nums) {
    if (n - prev > 1) btns += `<span class="pg-gap">…</span>`;
    btns += `<button type="button" data-page="${n}" class="${n === page ? "on" : ""}"
      ${n === page ? 'aria-current="page"' : ""} aria-label="Page ${n}">${n}</button>`;
    prev = n;
  }
  return `<nav class="pager" aria-label="Results pages">${info}<div class="pg-btns">
    <button type="button" data-page="${page - 1}" ${page === 1 ? "disabled" : ""}>‹ Prev</button>${btns}
    <button type="button" data-page="${page + 1}" ${page === pages ? "disabled" : ""}>Next ›</button></div></nav>`;
}

function renderResults() {
  const q = lastQuery;
  const route = S.trip === "round"
    ? `${q.legs[0].from.code} ⇄ ${q.legs[0].to.code}`
    : [q.legs[0].from.code, ...q.legs.map(l => l.to.code)].join(" → ");
  let list = offers.filter(o => !nonstopOnly || o.slices.every(s => s.stops === 0));
  const key = { price: o => o.price, duration: o => o.duration_min, depart: o => o.slices[0]?.depart || "" }[sortBy];
  list = [...list].sort((a, b) => key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0);

  const head = `<div class="res-head">
    <div><h2>${esc(route)}</h2>
      <div class="meta">${q.legs.map(l => shortDate(l.date)).join(" – ")} · ${esc(q.pax)} · ${esc(q.cabin)}${
        q.fare === "student" ? " · Student fare" : ""} · ${list.length} flight${list.length === 1 ? "" : "s"}</div></div>
    <div class="tools">
      <div class="seg" role="group" aria-label="Sort by">
        ${[["price", "Cheapest"], ["duration", "Fastest"], ["depart", "Earliest"]].map(([k, t]) =>
          `<button type="button" data-sort="${k}" class="${k === sortBy ? "on" : ""}">${t}</button>`).join("")}
      </div>
      <label class="chk"><input type="checkbox" id="nonstop" ${nonstopOnly ? "checked" : ""} /> Non-stop only</label>
    </div></div>`;

  const pages = Math.max(1, Math.ceil(list.length / PER_PAGE));
  page = Math.min(page, pages);
  const start = (page - 1) * PER_PAGE, shown = list.slice(start, start + PER_PAGE);

  const body = shown.length ? shown.map((o, k) => `<article class="card offer">
      <div class="slices">${o.slices.map(sliceHtml).join("")}</div>
      <div class="price"><div class="amt">${o.original_currency ? "≈ " : ""}${money(o.price, o.currency)}</div>
        <div class="per">total${paxTotal() > 1 ? ` · ${paxTotal()} travellers` : ""}</div>
        ${o.original_currency ? `<div class="orig" title="The airline charges in ${esc(o.original_currency)}; INR is an estimate at today's exchange rate">
          from ${money(o.original_price, o.original_currency)}</div>` : ""}
        <button type="button" class="btn-select" data-sel="${esc(o.id)}">Select</button></div>
      <button type="button" class="more" data-k="${k}" aria-expanded="false">Flight details ▾</button>
      <div class="details" hidden>${detailsHtml(o)}</div></article>`).join("")
    : `<div class="card state">${offers.length
        ? "No non-stop flights for this search. Untick “Non-stop only” to see connecting flights."
        : "No flights found for these dates. Try different dates or nearby airports."}</div>`;

  $("results").innerHTML = head + body + (list.length ? pagerHtml(start, shown.length, list.length, pages) : "");
  $("results").querySelectorAll("[data-sort]").forEach(b => b.onclick = () => { sortBy = b.dataset.sort; page = 1; renderResults(); });
  $("nonstop").onchange = e => { nonstopOnly = e.target.checked; page = 1; renderResults(); };
  $("results").querySelectorAll("[data-page]").forEach(b => b.onclick = () => {
    page = +b.dataset.page; renderResults();
    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("results").querySelectorAll("[data-sel]").forEach(b => b.onclick = () => startBooking(b.dataset.sel));
  $("results").querySelectorAll(".more").forEach(b => b.onclick = () => {
    const d = b.nextElementSibling, open = d.hidden;
    d.hidden = !open; b.setAttribute("aria-expanded", open);
    b.textContent = open ? "Hide details ▴" : "Flight details ▾";
  });
}

renderRows();

// Home / logo / "Back to flights": a fresh flight search, from any tab.
function goHome() {
  closePop();
  exitBooking();
  Object.assign(S, freshState());
  document.querySelector("input[name=trip][value=oneway]").checked = true;
  document.querySelector("input[name=fare][value=regular]").checked = true;
  offers = []; sortBy = "price"; nonstopOnly = false; lastQuery = null; page = 1;
  $("results").innerHTML = "";
  renderRows();
  // Drop "#hotels" etc. from the URL; Back still returns to that tab.
  if (location.hash) history.pushState(null, "", location.pathname);
  showView();
}
document.querySelectorAll("[data-home]").forEach(a => a.onclick = e => { e.preventDefault(); goHome(); });
