// booking.js — booking a flight: review → seats → travellers → review & pay → confirmation.
// Loaded after flights.js; uses its helpers (sliceHtml, detailsHtml, money, hm, dur, ...).

const B = {};                                  // booking state, reset by startBooking()
// The Seats step only appears when the airline shares a seat map for this flight.
const STEP_TITLES = { flight: "Flight", seats: "Seats", travellers: "Travellers", review: "Review & pay" };
const TITLES = [["mr", "Mr"], ["ms", "Ms"], ["mrs", "Mrs"], ["miss", "Miss"], ["dr", "Dr"]];
const LATIN = /^[A-Za-z][A-Za-z '\-]{0,39}$/;

// ---- entering / leaving the booking flow ----
function showBooking(on) {
  $("fx").hidden = on;
  $("results").hidden = on;
  document.querySelector("#view-flights .pd").hidden = on;
  $("booking").hidden = !on;
  window.scrollTo(0, 0);
}
function exitBooking() { if (!$("booking").hidden) showBooking(false); }
document.addEventListener("viewchange", () => { if (!location.hash || location.hash === "#flights") return; exitBooking(); });

async function startBooking(offerId) {
  closePop();
  Object.keys(B).forEach(k => delete B[k]);
  Object.assign(B, { offerId, step: 0, offer: null, rate: null, maps: null, seats: {}, activePax: null,
                     activeSeg: null, travellers: {}, contact: { email: "", phone: "" }, confirmed: false });
  showBooking(true);
  $("booking").innerHTML = `<div class="card state">Checking the latest price with the airline…</div>`;
  const [o, s] = await Promise.all([api(`/api/flights/offers/${offerId}`), api(`/api/flights/offers/${offerId}/seats`)]);
  if (o.error) return bookingError(o);
  B.offer = o.offer; B.rate = o.display.rate; B.contact.email = o.email || "";
  B.maps = s.error ? [] : s.seat_maps;                    // no seat map is fine: seats at check-in
  B.flow = B.maps.length ? ["flight", "seats", "travellers", "review"] : ["flight", "travellers", "review"];
  B.pax = labelTravellers(B.offer.passengers);
  B.pax.forEach(p => B.travellers[p.id] = { title: "", gender: "", given_name: "", family_name: "", born_on: "" });
  renderStep();
}

async function api(url, body) {
  try {
    const r = await fetch(url, body ? { method: "POST", headers: { "Content-Type": "application/json" },
                                        body: JSON.stringify(body) } : {});
    if (r.status === 401) { window.location.href = "/login"; return { error: "Please log in." }; }
    const d = await r.json();
    return r.ok ? d : { ...d, error: d.error || "Something went wrong.", status: r.status };
  } catch (_) {
    return { error: "Couldn't reach the server. Is it still running?" };
  }
}

function bookingError(e) {
  $("booking").innerHTML = `<div class="card state"><p class="err">${esc(e.error)}</p>
    <div class="bk-actions center">
      <button type="button" class="bk-btn ghost" data-go="results">← Back to results</button>
      ${e.gone ? `<button type="button" class="bk-btn" data-go="research">Search again</button>` : ""}
    </div></div>`;
  wireNav();
}

// "Adult 1", "Adult 2", "Child 1", "Infant 1"
function labelTravellers(passengers) {
  const n = {};
  return passengers.map(p => {
    const kind = p.type.startsWith("infant") ? "infant" : p.type === "child" ? "child" : "adult";
    n[kind] = (n[kind] || 0) + 1;
    const name = { adult: "Adult", child: "Child", infant: "Infant" }[kind];
    return { id: p.id, kind, label: `${name} ${n[kind]}`,
             hint: { adult: "12+ years", child: "2–11 years", infant: "Under 2, on an adult's lap" }[kind] };
  });
}

// ---- money: the airline's currency, with an INR estimate next to it ----
const inr = a => B.rate ? money(a * B.rate, "INR") : "";
// Exact amounts (to the cent) wherever the traveller is paying; INR estimates stay rounded.
const exact = (n, cur) => {
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency: cur, minimumFractionDigits: 2 }).format(n); }
  catch (_) { return `${cur} ${n.toFixed(2)}`; }
};
const both = (a, cur = B.offer.currency) => B.rate && cur !== "INR"
  ? `${money(a, cur)} <span class="bk-inr">≈ ${inr(a)}</span>` : money(a, cur);
const seatTotal = () => Object.values(B.seats).reduce((t, s) => t + s.amount, 0);

// ---- page frame: step bar + current step ----
function renderStep() {
  const bar = `<ol class="bk-steps">${B.flow.map((k, i) => `<li class="${i < B.step ? "done" : i === B.step ? "on" : ""}">
      <span class="n">${i < B.step ? "✓" : i + 1}</span>${STEP_TITLES[k]}</li>`).join("")}</ol>`;
  const current = B.flow[B.step];
  const body = { flight: stepFlight, seats: stepSeats, travellers: stepTravellers, review: stepReview }[current]();
  $("booking").innerHTML = `<div class="bk-top"><button type="button" class="bk-link" data-go="results">← Back to results</button>
    ${B.offer.expires_at ? `<span class="bk-hold">Fare held until ${new Date(B.offer.expires_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>` : ""}</div>
    ${bar}${body}`;
  wireNav();
  if (current === "seats") wireSeats();
  if (current === "travellers") wireTravellers();
  window.scrollTo(0, 0);
}

function wireNav() {
  $("booking").querySelectorAll("[data-go]").forEach(b => b.onclick = () => {
    const go = b.dataset.go;
    if (go === "results") return showBooking(false);
    if (go === "research") { showBooking(false); return $("fx").requestSubmit(); }
    if (go === "home") return goHome();
    if (go === "next") { if (B.flow[B.step] === "travellers" && !travellersValid()) return; B.step++; return renderStep(); }
    if (go === "back") { B.step--; return renderStep(); }
    if (go === "book") return book();
  });
}

// ---- step 1: the flight, fare rules, baggage, price ----
function rule(r, yes, no) {
  if (r.allowed === null || r.allowed === undefined) return `<span class="chip">${no} — check with airline</span>`;
  if (!r.allowed) return `<span class="chip bad">${no}</span>`;
  return `<span class="chip good">${yes}${r.penalty ? ` · fee ${both(r.penalty, r.currency || B.offer.currency)}` : " · free"}</span>`;
}

function stepFlight() {
  const o = B.offer;
  const bags = o.baggage.length
    ? o.baggage.map(b => `${b.quantity} ${b.type === "checked" ? "checked bag" : "cabin bag"}${b.quantity === 1 ? "" : "s"}`).join(" · ")
    : "Baggage allowance not shared by the airline";
  const n = B.pax.length;
  return `<div class="bk-grid">
    <div class="card bk-main">
      <h2>Your flight</h2>
      <div class="slices">${o.slices.map(sliceHtml).join("")}</div>
      <div class="details">${detailsHtml(o)}</div>
      <h3>Fare rules</h3>
      <div class="chips">${rule(o.refund, "Refundable", "Non-refundable")}${rule(o.change, "Changes allowed", "No changes")}</div>
      <h3>Baggage <span class="muted">per traveller</span></h3><p class="kv">${bags}</p>
    </div>
    <aside class="card bk-side">
      <h3>Price</h3>
      ${o.base_amount != null ? `<div class="line"><span>Base fare</span><span>${exact(o.base_amount, o.currency)}</span></div>` : ""}
      ${o.tax_amount != null ? `<div class="line"><span>Taxes & fees</span><span>${exact(o.tax_amount, o.currency)}</span></div>` : ""}
      <div class="line total"><span>Total · ${n} traveller${n > 1 ? "s" : ""}</span><span>${exact(o.price, o.currency)}</span></div>
      ${B.rate && o.currency !== "INR" ? `<div class="bk-inr big">≈ ${inr(o.price)}</div>` : ""}
      <p class="muted small">Price just re-checked with the airline.</p>
      <button type="button" class="bk-btn full" data-go="next">${B.flow[1] === "seats" ? "Continue to seats" : "Continue to traveller details"}</button>
    </aside></div>`;
}

// ---- step 2: seat map ----
function segments() { return B.offer.slices.flatMap(s => s.segments); }
function seatable() { return B.pax.filter(p => p.kind !== "infant"); }

function stepSeats() {
  const maps = B.maps || [];
  const segs = segments().filter(g => maps.some(m => m.segment_id === g.id));
  if (!B.activeSeg || !segs.some(g => g.id === B.activeSeg)) B.activeSeg = segs[0].id;
  if (!B.activePax) B.activePax = seatable()[0]?.id;
  const map = maps.find(m => m.segment_id === B.activeSeg);

  const segTabs = segs.length > 1 ? `<div class="seg bk-segtabs">${segs.map(g =>
    `<button type="button" data-seg="${g.id}" class="${g.id === B.activeSeg ? "on" : ""}">${esc(g.origin.code)} → ${esc(g.destination.code)}</button>`).join("")}</div>` : "";
  const paxChips = `<div class="bk-pax">${seatable().map(p => {
    const s = B.seats[`${B.activeSeg}|${p.id}`];
    return `<button type="button" data-pax="${p.id}" class="${p.id === B.activePax ? "on" : ""}">
      <b>${p.label}</b><span>${s ? `Seat ${esc(s.designator)}` : "No seat yet"}</span></button>`;
  }).join("")}${B.pax.some(p => p.kind === "infant") ? `<span class="muted small">Infants sit on an adult's lap.</span>` : ""}</div>`;

  return `<div class="bk-grid">
    <div class="card bk-main">
      <h2>Choose seats</h2>${segTabs}
      <p class="muted small">Pick a seat for each traveller. Grey seats are taken.</p>
      ${paxChips}
      <div class="legend"><span><i class="sb free"></i>Free</span><span><i class="sb paid"></i>Paid</span>
        <span><i class="sb taken"></i>Taken</span><span><i class="sb mine"></i>Your pick</span></div>
      <div class="plane">${map.cabins.map(cabinHtml).join("")}</div>
    </div>
    <aside class="card bk-side">
      <h3>Your seats</h3>
      ${segs.map(g => `<div class="muted small bk-seglbl">${esc(g.origin.code)} → ${esc(g.destination.code)}</div>` +
        seatable().map(p => { const s = B.seats[`${g.id}|${p.id}`];
          return `<div class="line"><span>${p.label}</span><span>${s ? `${esc(s.designator)} · ${s.amount ? exact(s.amount, s.currency) : "free"}` : "—"}</span></div>`; }).join("")).join("")}
      <div class="line total"><span>Seats total</span><span>${exact(seatTotal(), B.offer.currency)}</span></div>
      ${B.rate && seatTotal() ? `<div class="bk-inr">≈ ${inr(seatTotal())}</div>` : ""}
      <button type="button" class="bk-btn full" data-go="next">${Object.keys(B.seats).length ? "Continue" : "Skip seats"}</button>
      <button type="button" class="bk-btn ghost full" data-go="back">Back</button>
    </aside></div>`;
}

function cabinHtml(cabin) {
  // Column letters from the widest row, e.g. "ABC DEF HJK".
  const widest = cabin.rows.reduce((a, r) => r.flat().length > a.flat().length ? r : a, []);
  const letters = widest.map(sec => sec.map(e => (e.designator || "").replace(/^\d+/, "")));
  const head = `<div class="prow head"><span class="rn"></span>${letters.map(sec =>
    `<div class="psec">${sec.map(l => `<span class="cl">${esc(l)}</span>`).join("")}</div>`).join('<span class="aisle"></span>')}</div>`;
  const rows = cabin.rows.map(row => {
    const des = row.flat().find(e => e.designator)?.designator || "";
    const exit = row.flat().some(e => e.type === "exit_row");
    return `<div class="prow${exit ? " exit" : ""}"><span class="rn">${esc(des.replace(/\D+$/, ""))}</span>${row.map(sec =>
      `<div class="psec">${sec.map(elHtml).join("")}</div>`).join('<span class="aisle"></span>')}</div>`;
  }).join("");
  return `<div class="cabin"><div class="cabin-lbl">${esc(CABIN[cabin.cabin_class] || cabin.cabin_class || "")}</div>${head}${rows}</div>`;
}

function elHtml(e) {
  if (e.type === "exit_row") return `<span class="pel exit-mk" title="Exit row">EXIT</span>`;
  if (e.type === "lavatory") return `<span class="pel fac" title="Lavatory">WC</span>`;
  if (e.type === "galley") return `<span class="pel fac" title="Galley">G</span>`;
  if (e.type !== "seat") return `<span class="pel"></span>`;
  const mine = Object.entries(B.seats).find(([k, s]) => k.startsWith(B.activeSeg + "|") && s.designator === e.designator);
  const sv = e.services[B.activePax];
  if (mine) {
    const who = B.pax.find(p => p.id === mine[0].split("|")[1]);
    return `<button type="button" class="sb mine" data-seat="${esc(e.designator)}" title="${esc(e.designator)} · ${who.label}">${who.label[0]}${who.label.split(" ")[1]}</button>`;   // "A1", "C1"
  }
  if (!sv) return `<span class="sb taken" title="${esc(e.designator)} · taken"></span>`;
  const note = e.disclosures.length ? ` · ${e.disclosures.join("; ")}` : "";
  const price = sv.amount ? `${money(sv.amount, sv.currency)}${B.rate ? ` ≈ ${inr(sv.amount)}` : ""}` : "free";
  return `<button type="button" class="sb ${sv.amount ? "paid" : "free"}" data-seat="${esc(e.designator)}"
    title="${esc(e.designator)} · ${price}${esc(note)}" aria-label="Seat ${esc(e.designator)}, ${price}"></button>`;
}

function wireSeats() {
  const root = $("booking");
  root.querySelectorAll("[data-seg]").forEach(b => b.onclick = () => { B.activeSeg = b.dataset.seg; renderStep(); });
  root.querySelectorAll("[data-pax]").forEach(b => b.onclick = () => { B.activePax = b.dataset.pax; renderStep(); });
  root.querySelectorAll("[data-seat]").forEach(b => b.onclick = () => {
    const d = b.dataset.seat, map = B.maps.find(m => m.segment_id === B.activeSeg);
    const el = map.cabins.flatMap(c => c.rows.flat(2)).find(x => x.designator === d);
    const key = `${B.activeSeg}|${B.activePax}`;
    const holder = Object.keys(B.seats).find(k => k.startsWith(B.activeSeg + "|") && B.seats[k].designator === d);
    if (holder) { delete B.seats[holder]; if (holder === key) return renderStep(); }   // tap your seat again = unselect
    const sv = el?.services[B.activePax];
    if (!sv) return;
    B.seats[key] = { serviceId: sv.id, designator: d, amount: sv.amount, currency: sv.currency };
    // Move on to the next traveller who still needs a seat on this flight.
    const next = seatable().find(p => !B.seats[`${B.activeSeg}|${p.id}`]);
    if (next) B.activePax = next.id;
    const scroll = root.querySelector(".plane")?.scrollTop;
    renderStep();
    if (scroll != null) root.querySelector(".plane").scrollTop = scroll;
  });
}

// ---- step 3: traveller details ----
function stepTravellers() {
  const field = (p, k, label, html) => `<label class="fld"><span>${label}</span>${html}</label>`;
  const cards = B.pax.map(p => {
    const t = B.travellers[p.id];
    return `<div class="card bk-trav" data-t="${p.id}">
      <div class="bk-trav-h"><h3>${p.label}</h3><span class="muted small">${p.hint}</span></div>
      <div class="fgrid">
        ${field(p, "title", "Title", `<select data-k="title"><option value="">Select</option>${TITLES.map(([v, l]) =>
          `<option value="${v}" ${t.title === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}
        ${field(p, "given_name", "First & middle name", `<input data-k="given_name" value="${esc(t.given_name)}" autocomplete="given-name" placeholder="As on ID" />`)}
        ${field(p, "family_name", "Last name", `<input data-k="family_name" value="${esc(t.family_name)}" autocomplete="family-name" placeholder="As on ID" />`)}
        ${field(p, "gender", "Gender", `<select data-k="gender"><option value="">Select</option>
          <option value="m" ${t.gender === "m" ? "selected" : ""}>Male</option><option value="f" ${t.gender === "f" ? "selected" : ""}>Female</option></select>`)}
        ${field(p, "born_on", "Date of birth", `<input type="date" data-k="born_on" value="${t.born_on}" max="${TODAY}" />`)}
      </div><div class="ferr" data-err></div></div>`;
  }).join("");
  return `<div class="bk-grid">
    <div class="bk-main plain">
      <h2>Traveller details</h2>
      <p class="muted small">Enter names exactly as on each traveller's passport or government ID, in English letters.</p>
      ${cards}
      <div class="card bk-trav"><div class="bk-trav-h"><h3>Contact</h3><span class="muted small">Booking updates go here</span></div>
        <div class="fgrid two">
          <label class="fld"><span>Email</span><input id="bkEmail" type="email" value="${esc(B.contact.email)}" autocomplete="email" /></label>
          <label class="fld"><span>Mobile (with country code)</span><input id="bkPhone" type="tel" value="${esc(B.contact.phone)}" placeholder="+91 98765 43210" autocomplete="tel" /></label>
        </div><div class="ferr" id="contactErr"></div></div>
    </div>
    <aside class="card bk-side">${priceSide()}
      <button type="button" class="bk-btn full" data-go="next">Continue to review</button>
      <button type="button" class="bk-btn ghost full" data-go="back">Back</button></aside></div>`;
}

function priceSide() {
  const o = B.offer, total = o.price + seatTotal();
  return `<h3>Price</h3>
    <div class="line"><span>Flight · ${B.pax.length} traveller${B.pax.length > 1 ? "s" : ""}</span><span>${exact(o.price, o.currency)}</span></div>
    <div class="line"><span>Seats</span><span>${seatTotal() ? exact(seatTotal(), o.currency) : "—"}</span></div>
    <div class="line total"><span>Total</span><span>${exact(total, o.currency)}</span></div>
    ${B.rate && o.currency !== "INR" ? `<div class="bk-inr big">≈ ${inr(total)}</div>` : ""}`;
}

function wireTravellers() {
  $("booking").querySelectorAll("[data-t]").forEach(card => {
    card.querySelectorAll("[data-k]").forEach(inp => inp.oninput = inp.onchange = () => {
      B.travellers[card.dataset.t][inp.dataset.k] = inp.value;
      inp.classList.remove("bad");
    });
  });
  $("bkEmail").oninput = e => B.contact.email = e.target.value;
  $("bkPhone").oninput = e => B.contact.phone = e.target.value;
}

function travellersValid() {
  let ok = true, first = null;
  $("booking").querySelectorAll("[data-t]").forEach(card => {
    const t = B.travellers[card.dataset.t], p = B.pax.find(x => x.id === card.dataset.t), errs = [];
    const mark = k => { const el = card.querySelector(`[data-k=${k}]`); el.classList.add("bad"); first ??= el; };
    ["title", "gender", "born_on"].forEach(k => { if (!t[k]) { mark(k); errs.push("Fill in every field."); } });
    ["given_name", "family_name"].forEach(k => {
      if (!LATIN.test(t[k].trim().replace(/\s+/g, " "))) { mark(k); errs.push("Names must use English letters (A–Z)."); }
    });
    if (t.born_on) {
      const age = (Date.now() - parse(t.born_on)) / (365.25 * 864e5);
      const bad = p.kind === "infant" ? age >= 2 : p.kind === "child" ? age < 2 || age >= 12 : age < 12;
      if (bad || t.born_on >= TODAY) { mark("born_on"); errs.push(`Date of birth doesn't fit ${p.hint.toLowerCase()}.`); }
    }
    card.querySelector("[data-err]").textContent = [...new Set(errs)].join(" ");
    if (errs.length) ok = false;
  });
  const c = [];
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(B.contact.email.trim())) { $("bkEmail").classList.add("bad"); c.push("Enter a valid email."); first ??= $("bkEmail"); }
  if (!/^\+[1-9]\d{6,14}$/.test(B.contact.phone.replace(/[\s\-()]/g, ""))) { $("bkPhone").classList.add("bad"); c.push("Add the country code, e.g. +91 98765 43210."); first ??= $("bkPhone"); }
  $("contactErr").textContent = c.join(" ");
  if (c.length) ok = false;
  first?.focus();
  return ok;
}

// ---- step 4: review & pay ----
function stepReview() {
  const o = B.offer;
  const rows = B.pax.map(p => {
    const t = B.travellers[p.id];
    const seats = segments().map(g => B.seats[`${g.id}|${p.id}`]?.designator).filter(Boolean);
    return `<div class="line"><span><b>${esc(`${TITLES.find(x => x[0] === t.title)?.[1] || ""} ${t.given_name} ${t.family_name}`)}</b>
      <span class="muted small"> · ${p.label}</span></span><span>${seats.length ? `Seat ${seats.map(esc).join(", ")}` : p.kind === "infant" ? "On lap" : "Seat at check-in"}</span></div>`;
  }).join("");
  return `<div class="bk-grid">
    <div class="card bk-main">
      <h2>Review your booking</h2>
      <div class="slices">${o.slices.map(sliceHtml).join("")}</div>
      <h3>Travellers</h3>${rows}
      <p class="kv small">Contact: ${esc(B.contact.email)} · ${esc(B.contact.phone)}</p>
      <div class="bk-test"><b>Test booking.</b> This is Duffel's test mode: it's paid from a pretend balance,
        no real money is taken and no real ticket is issued.</div>
      <label class="chk bk-agree"><input type="checkbox" id="bkAgree" /> I've checked that the names match each traveller's ID.</label>
    </div>
    <aside class="card bk-side">${priceSide()}
      <button type="button" class="bk-btn full" id="bkBook" data-go="book">Confirm & book</button>
      <button type="button" class="bk-btn ghost full" data-go="back">Back</button></aside></div>`;
}

async function book() {
  if (!$("bkAgree").checked) { $("bkAgree").focus(); $("bkAgree").closest("label").classList.add("bad"); return; }
  const btn = $("bkBook");
  btn.disabled = true; btn.textContent = "Booking with the airline…";
  const d = await api("/api/flights/orders", {
    offer_id: B.offerId,
    travellers: B.pax.map(p => ({ id: p.id, ...B.travellers[p.id] })),
    email: B.contact.email, phone: B.contact.phone,
    seats: Object.values(B.seats).map(s => s.serviceId),
  });
  if (d.error) {
    btn.disabled = false; btn.textContent = "Confirm & book";
    if (d.gone || d.status === 409) return bookingError(d);
    return showBookErr(d.error);
  }
  confirmation(d);
}

function showBookErr(msg) {
  let el = $("booking").querySelector(".bk-fail");
  if (!el) { el = document.createElement("p"); el.className = "err bk-fail"; $("bkBook").before(el); }
  el.textContent = msg;
}

// ---- confirmation ----
function confirmation(d) {
  const o = d.order, s = d.summary, rate = d.display.rate;
  $("booking").innerHTML = `<div class="card bk-done">
    <div class="tick">✓</div>
    <h2>Booking confirmed</h2>
    <p class="muted">Test booking with ${esc(s.airline)} — no real ticket was issued.</p>
    <div class="pnr"><span>Booking reference (PNR)</span><b>${esc(o.booking_reference)}</b></div>
    <div class="bk-done-grid">
      <div><h3>Flights</h3>${s.slices.map(x => `<div class="line"><span><b>${esc(x.origin)} → ${esc(x.destination)}</b></span>
        <span>${esc((x.depart || "").slice(0, 10))} · ${hm(x.depart)}–${hm(x.arrive)}</span></div>`).join("")}</div>
      <div><h3>Travellers</h3>${s.travellers.map(t => `<div class="line"><span>${esc(t.name)}</span>
        <span>${t.seats.length ? `Seat ${t.seats.map(esc).join(", ")}` : "—"}</span></div>`).join("")}</div>
    </div>
    <div class="line total"><span>Total paid</span><span>${exact(o.total_amount, o.total_currency)}${
      rate && o.total_currency !== "INR" ? ` <span class="bk-inr">≈ ${money(o.total_amount * rate, "INR")}</span>` : ""}</span></div>
    <p class="muted small">Order ${esc(o.order_id)}</p>
    <div class="bk-actions center"><button type="button" class="bk-btn" data-go="home">Book another flight</button></div>
  </div>`;
  wireNav();
  window.scrollTo(0, 0);
}
