const state = {
  maxExtra: 45,
  showAll: false,
  fuelType: 'SP95-E10',
  routes: [],
  selectedRoute: null,
};

const $ = (selector) => document.querySelector(selector);
const formatMoney = (value) => new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(value);
const formatDuration = (minutes) => `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')}`;
const tagClass = (tag) => tag === 'Recommandé' ? 'recommended' : (tag === 'À vérifier' || tag === 'Péage estimé' ? 'estimated' : '');

async function health() {
  try {
    const data = await fetch('/api/health').then((response) => response.json());
    const status = $('#status');
    status.className = `status ${data.graphhopper ? 'ready' : 'demo'}`;
    status.querySelector('span:last-child').textContent = data.graphhopper
      ? 'Moteur local opérationnel'
      : 'Mode démo · GraphHopper hors ligne';
  } catch {
    $('#status').querySelector('span:last-child').textContent = 'Serveur indisponible';
  }
}

function setupAutocomplete(inputId, hiddenId, suggestionId) {
  const input = $(inputId);
  const hidden = $(hiddenId);
  const box = $(suggestionId);
  let timer;
  const search = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (input.value.trim().length < 2) return;
      const results = await fetch(`/api/geocode?q=${encodeURIComponent(input.value.trim())}`).then((r) => r.json());
      box.innerHTML = results.map((place, index) => `
        <button type="button" class="suggestion" data-index="${index}">
          ${escapeHtml(place.label)}<small>${place.source === 'ban' ? 'Base Adresse Nationale' : 'Lieu de démonstration'}</small>
        </button>`).join('');
      box.classList.toggle('open', results.length > 0);
      box.querySelectorAll('.suggestion').forEach((button) => button.addEventListener('click', () => {
        const place = results[Number(button.dataset.index)];
        input.value = place.label;
        hidden.value = JSON.stringify({ lat: place.lat, lon: place.lon });
        box.classList.remove('open');
      }));
    }, 220);
  };
  input.addEventListener('input', () => { hidden.value = ''; search(); });
  input.addEventListener('focus', search);
  document.addEventListener('click', (event) => { if (!box.contains(event.target) && event.target !== input) box.classList.remove('open'); });
}

async function resolveAddress(inputId, hiddenId) {
  const hidden = $(hiddenId);
  if (hidden.value) return JSON.parse(hidden.value);
  const query = $(inputId).value.trim();
  const results = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`).then((r) => r.json());
  if (!results.length) throw new Error(`Adresse introuvable : ${query}`);
  const result = results[0];
  hidden.value = JSON.stringify({ lat: result.lat, lon: result.lon });
  $(inputId).value = result.label;
  return { lat: result.lat, lon: result.lon };
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
}

function renderTollSegments(route) {
  const segments = route.toll_segments || [];
  if (!segments.length || route.toll_cost <= 0) return '';
  const rows = segments.map((segment) => {
    const label = segment.entry
      ? `${escapeHtml(segment.entry)}${segment.exit ? ` → ${escapeHtml(segment.exit)}` : ''}`
      : `Partie estimée${segment.distance_km ? ` · ${Number(segment.distance_km).toFixed(0)} km` : ''}`;
    const badge = segment.confidence === 'exact' ? 'exact' : 'estimated';
    return `<div class="toll-segment"><span>${label}</span><strong>${formatMoney(segment.cost)}</strong><i class="${badge}">${segment.confidence === 'exact' ? 'exact' : 'estimé'}</i></div>`;
  }).join('');
  return `<details class="toll-details"><summary>Détail des péages</summary>${rows}</details>`;
}

function renderResults(data) {
  state.routes = data.routes;
  $('#empty-state').style.display = 'none';
  $('#results-title').textContent = `${data.routes.length} itinéraire${data.routes.length > 1 ? 's' : ''} proposé${data.routes.length > 1 ? 's' : ''}`;
  $('#summary-pill').textContent = `Twingo 2 · ${state.fuelType} · ${Number($('#fuel-price').value).toFixed(3)} €/L`;
  $('#results').innerHTML = data.routes.map((route, index) => `
    <article class="route-card ${index === 0 ? 'selected' : ''} ${route.within_limit ? '' : 'outside'}" data-id="${route.id}">
      <div class="card-top">
        <div><h3>${escapeHtml(route.label)}</h3><div class="desc">${escapeHtml(route.description)}</div></div>
        <div class="tags">${route.tags.map((tag) => `<span class="tag ${tagClass(tag)}">${escapeHtml(tag)}</span>`).join('')}</div>
      </div>
      <div class="main-metrics"><strong>${formatMoney(route.total_cost)}</strong><span>${formatDuration(route.duration_minutes)}${route.extra_minutes ? ` · +${route.extra_minutes} min` : ''}</span></div>
      <div class="metrics">
        <div class="metric"><span>Carburant</span><strong>${formatMoney(route.fuel_cost)}</strong></div>
        <div class="metric"><span>Péages</span><strong>${formatMoney(route.toll_cost)}</strong></div>
        <div class="metric"><span>Autoroute</span><strong>${route.motorway_km.toFixed(0)} km</strong></div>
        <div class="metric"><span>Autres routes</span><strong>${route.road_km.toFixed(0)} km</strong></div>
      </div>
      ${route.savings > 0 ? `<div class="saving">${formatMoney(route.savings)} économisés face au plus rapide</div>` : ''}
      ${route.toll_confidence === 'exact'
        ? `<div class="toll-exact">${escapeHtml(route.toll_message || 'Tarif de péage exact classe 1.')}</div>`
        : route.toll_confidence === 'estimated'
          ? `<div class="warning">${escapeHtml(route.toll_message || 'Péage encore estimé.')}</div>`
          : ''}
      ${renderTollSegments(route)}
    </article>`).join('');
  document.querySelectorAll('.route-card').forEach((card) => card.addEventListener('click', () => selectRoute(card.dataset.id)));
  selectRoute(data.routes[0]?.id);
}

function selectRoute(id) {
  state.selectedRoute = state.routes.find((route) => route.id === id) || state.routes[0];
  document.querySelectorAll('.route-card').forEach((card) => card.classList.toggle('selected', card.dataset.id === state.selectedRoute?.id));
  drawRoutes();
}

function drawRoutes() {
  window.RoutecoMap?.render(state.routes, state.selectedRoute);
}

async function calculate(event) {
  event?.preventDefault();
  const button = $('#calculate');
  button.disabled = true;
  button.querySelector('span:first-child').textContent = 'Calcul en cours…';
  try {
    const [start, end] = await Promise.all([
      resolveAddress('#start', '#start-coords'),
      resolveAddress('#end', '#end-coords'),
    ]);
    const payload = {
      start,
      end,
      start_label: $('#start').value,
      end_label: $('#end').value,
      fuel_type: state.fuelType,
      fuel_price: Number($('#fuel-price').value),
      max_extra_minutes: state.showAll ? null : state.maxExtra,
      show_all: state.showAll,
      motorway_consumption: Number($('#motorway-consumption').value),
      road_consumption: Number($('#road-consumption').value),
    };
    const response = await fetch('/api/routes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Calcul impossible');
    }
    const data = await response.json();
    $('#map-title').textContent = `${$('#start').value.split(',')[0]} → ${$('#end').value.split(',')[0]}`;
    const status = $('#status');
    status.className = `status ${data.engine === 'graphhopper' ? 'ready' : 'demo'}`;
    status.querySelector('span:last-child').textContent = data.engine_message;
    renderResults(data);
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
    button.querySelector('span:first-child').textContent = 'Comparer les itinéraires';
  }
}

setupAutocomplete('#start', '#start-coords', '#start-suggestions');
setupAutocomplete('#end', '#end-coords', '#end-suggestions');
$('#route-form').addEventListener('submit', calculate);
$('#swap').addEventListener('click', () => {
  const startValue = $('#start').value, startCoords = $('#start-coords').value;
  $('#start').value = $('#end').value; $('#start-coords').value = $('#end-coords').value;
  $('#end').value = startValue; $('#end-coords').value = startCoords;
});
$('#time-chips').querySelectorAll('button').forEach((button) => button.addEventListener('click', () => {
  $('#time-chips').querySelectorAll('button').forEach((item) => item.classList.remove('active'));
  button.classList.add('active');
  state.showAll = button.dataset.minutes === 'all';
  state.maxExtra = state.showAll ? null : Number(button.dataset.minutes);
}));
$('#fuel-type').querySelectorAll('button').forEach((button) => button.addEventListener('click', () => {
  $('#fuel-type').querySelectorAll('button').forEach((item) => item.classList.remove('active'));
  button.classList.add('active');
  state.fuelType = button.dataset.fuel;
}));

health();
calculate();
