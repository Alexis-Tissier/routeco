const state = {
  maxExtra: 45,
  showAll: false,
  routes: [],
  selectedRoute: null,
  mapExpanded: false,
};

const $ = (selector) => document.querySelector(selector);
const formatMoney = (value) => new Intl.NumberFormat('fr-FR', {
  style: 'currency',
  currency: 'EUR',
}).format(value);
const formatDuration = (minutes) => (
  `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')}`
);
const tagClass = (tag) => (
  tag === 'Recommandé'
    ? 'recommended'
    : (tag === 'À vérifier' || tag === 'Péage estimé' ? 'estimated' : '')
);

function escapeHtml(value) {
  return String(value).replace(
    /[&<>'"]/g,
    (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;',
    }[char]),
  );
}

function sourceLabel(place) {
  if (place.source === 'commune') return 'Commune française';
  if (place.source === 'ban') return 'Adresse · Base Adresse Nationale';
  return 'Lieu de démonstration';
}

async function health() {
  try {
    const data = await fetch('/api/health').then((response) => response.json());
    const status = $('#status');
    status.className = `status ${data.graphhopper ? 'ready' : 'demo'}`;
    if (!data.graphhopper) {
      status.querySelector('span:last-child').textContent = 'Mode démo · moteur hors ligne';
    } else if (data.communes >= 30000) {
      status.querySelector('span:last-child').textContent = 'Moteur local · toutes les communes';
    } else {
      status.querySelector('span:last-child').textContent = 'Moteur local · index des communes incomplet';
    }
  } catch {
    $('#status').querySelector('span:last-child').textContent = 'Serveur indisponible';
  }
}

function setupAutocomplete(inputSelector, hiddenSelector, boxSelector) {
  const input = $(inputSelector);
  const hidden = $(hiddenSelector);
  const box = $(boxSelector);
  let timer;
  let results = [];
  let activeIndex = -1;
  let requestNumber = 0;

  function close() {
    box.classList.remove('open');
    input.setAttribute('aria-expanded', 'false');
    activeIndex = -1;
  }

  function activate(index) {
    const buttons = [...box.querySelectorAll('.suggestion')];
    if (!buttons.length) return;
    activeIndex = (index + buttons.length) % buttons.length;
    buttons.forEach((button, buttonIndex) => {
      const active = buttonIndex === activeIndex;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
    buttons[activeIndex].scrollIntoView({ block: 'nearest' });
  }

  function select(place) {
    if (!place) return;
    clearTimeout(timer);
    requestNumber += 1;
    input.value = place.label;
    hidden.value = JSON.stringify({
      lat: Number(place.lat),
      lon: Number(place.lon),
      label: place.label,
    });
    input.classList.remove('invalid');
    close();
  }

  function render(nextResults, message = '') {
    results = nextResults || [];
    if (message && !results.length) {
      box.innerHTML = `<div class="suggestion-state">${escapeHtml(message)}</div>`;
    } else {
      box.innerHTML = results.map((place, index) => `
        <button type="button" class="suggestion" role="option"
                aria-selected="false" data-index="${index}">
          <strong>${escapeHtml(place.label)}</strong>
          <small>${escapeHtml(sourceLabel(place))}</small>
        </button>
      `).join('');
    }
    const shouldOpen = Boolean(message || results.length);
    box.classList.toggle('open', shouldOpen);
    input.setAttribute('aria-expanded', String(shouldOpen));
    activeIndex = -1;
    box.querySelectorAll('.suggestion').forEach((button) => {
      button.addEventListener('click', () => select(results[Number(button.dataset.index)]));
    });
  }

  async function search() {
    clearTimeout(timer);
    const query = input.value.trim();
    if (query.length < 2) {
      close();
      return;
    }
    const currentRequest = ++requestNumber;
    render([], 'Recherche…');
    try {
      const response = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
      if (!response.ok) throw new Error('Recherche indisponible');
      const payload = await response.json();
      if (currentRequest !== requestNumber) return;
      render(payload, payload.length ? '' : 'Aucun résultat');
    } catch {
      if (currentRequest === requestNumber) render([], 'Recherche indisponible');
    }
  }

  function scheduleSearch() {
    clearTimeout(timer);
    timer = setTimeout(search, 180);
  }

  input.addEventListener('input', () => {
    hidden.value = '';
    input.classList.remove('invalid');
    scheduleSearch();
  });
  input.addEventListener('focus', scheduleSearch);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      activate(activeIndex + 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      activate(activeIndex - 1);
    } else if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault();
      select(results[activeIndex]);
    } else if (event.key === 'Escape') {
      close();
    }
  });
  document.addEventListener('click', (event) => {
    if (!box.contains(event.target) && event.target !== input) close();
  });

  return {
    input,
    hidden,
    close,
    render,
    select,
    invalidate() {
      input.classList.add('invalid');
    },
  };
}

const startAutocomplete = setupAutocomplete(
  '#start',
  '#start-coords',
  '#start-suggestions',
);
const endAutocomplete = setupAutocomplete(
  '#end',
  '#end-coords',
  '#end-suggestions',
);

function showFormMessage(message = '') {
  const element = $('#form-message');
  element.textContent = message;
  element.classList.toggle('visible', Boolean(message));
}

async function resolveAddress(controller) {
  if (controller.hidden.value) {
    const saved = JSON.parse(controller.hidden.value);
    return { lat: saved.lat, lon: saved.lon };
  }
  const query = controller.input.value.trim();
  const response = await fetch(`/api/geocode/resolve?q=${encodeURIComponent(query)}`);
  const payload = await response.json();
  if (response.status === 409) {
    const detail = payload.detail || {};
    controller.render(detail.choices || []);
    controller.invalidate();
    throw new Error(
      detail.message
      || `Plusieurs lieux correspondent à « ${query} ». Choisis-en un dans la liste.`,
    );
  }
  if (!response.ok) {
    controller.invalidate();
    throw new Error(
      typeof payload.detail === 'string'
        ? payload.detail
        : `Adresse ou commune introuvable : ${query}`,
    );
  }
  controller.select(payload);
  return { lat: payload.lat, lon: payload.lon };
}

function renderTollSegments(route) {
  const segments = route.toll_segments || [];
  if (!segments.length || route.toll_cost <= 0) return '';
  const rows = segments.map((segment) => {
    const label = segment.entry
      ? `${escapeHtml(segment.entry)}${segment.exit ? ` → ${escapeHtml(segment.exit)}` : ''}`
      : `Partie estimée${segment.distance_km ? ` · ${Number(segment.distance_km).toFixed(0)} km` : ''}`;
    const badge = segment.confidence === 'exact' ? 'exact' : 'estimated';
    return `
      <div class="toll-segment">
        <span>${label}</span>
        <strong>${formatMoney(segment.cost)}</strong>
        <i class="${badge}">${segment.confidence === 'exact' ? 'exact' : 'estimé'}</i>
      </div>
    `;
  }).join('');
  return `<details class="toll-details"><summary>Détail des péages</summary>${rows}</details>`;
}

function candidateSummary(data) {
  const parts = [`${data.candidate_count} calculé${data.candidate_count > 1 ? 's' : ''}`];
  const filtered = Math.max(0, data.hidden_count - data.merged_count);
  if (filtered) {
    parts.push(`${filtered} hors critères`);
  }
  if (data.merged_count) {
    parts.push(`${data.merged_count} trop proche${data.merged_count > 1 ? 's' : ''} regroupé${data.merged_count > 1 ? 's' : ''}`);
  }
  parts.push(`${data.routes.length} affiché${data.routes.length > 1 ? 's' : ''}`);
  return parts.join(' · ');
}

function renderResults(data) {
  state.routes = data.routes;
  $('#empty-state').style.display = 'none';
  const alternativeCount = Math.max(0, data.routes.length - 1);
  $('#results-title').textContent = alternativeCount
    ? `1 référence rapide · ${alternativeCount} alternative${alternativeCount > 1 ? 's' : ''}`
    : 'Le trajet de référence';
  $('#candidate-count').textContent = candidateSummary(data);
  $('#results').innerHTML = data.routes.map((route, index) => `
    <article class="route-card ${index === 0 ? 'selected' : ''} ${route.within_limit ? '' : 'outside'}"
             data-id="${escapeHtml(route.id)}" tabindex="0">
      <div class="card-top">
        <div>
          <h3>${escapeHtml(route.label)}</h3>
          <div class="desc">${escapeHtml(route.description)}</div>
        </div>
        <div class="tags">
          ${route.tags.map((tag) => `<span class="tag ${tagClass(tag)}">${escapeHtml(tag)}</span>`).join('')}
        </div>
      </div>
      <div class="main-metrics">
        <strong>${formatMoney(route.total_cost)}</strong>
        <span>${formatDuration(route.duration_minutes)}${route.extra_minutes ? ` · +${route.extra_minutes} min` : ''}</span>
      </div>
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
    </article>
  `).join('');
  document.querySelectorAll('.route-card').forEach((card) => {
    card.addEventListener('click', () => selectRoute(card.dataset.id));
    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectRoute(card.dataset.id);
      }
    });
  });
  $('#nav-toggle').disabled = !data.routes.length;
  $('#map-fit').disabled = !data.routes.length;
  selectRoute(data.routes[0]?.id);
}

function selectRoute(id, scroll = false) {
  state.selectedRoute = state.routes.find((route) => route.id === id) || state.routes[0];
  document.querySelectorAll('.route-card').forEach((card) => {
    card.classList.toggle('selected', card.dataset.id === state.selectedRoute?.id);
  });
  if (scroll && state.selectedRoute) {
    document.querySelector(`.route-card[data-id="${CSS.escape(state.selectedRoute.id)}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  drawRoutes();
  updateNavigationLinks();
}

window.RoutecoSelectRoute = (id) => selectRoute(id, true);

function drawRoutes() {
  window.RoutecoMap?.render(state.routes, state.selectedRoute);
}

function sampledWaypoints(geometry, count = 6) {
  if (!geometry || geometry.length < 3) return [];
  return Array.from({ length: count }, (_, index) => {
    const pointIndex = Math.round(((index + 1) * (geometry.length - 1)) / (count + 1));
    return geometry[pointIndex];
  });
}

function updateNavigationLinks() {
  const route = state.selectedRoute;
  if (!route?.geometry?.length) return;
  const start = route.geometry[0];
  const end = route.geometry[route.geometry.length - 1];
  const origin = `${start[1]},${start[0]}`;
  const destination = `${end[1]},${end[0]}`;
  const waypoints = sampledWaypoints(route.geometry)
    .map(([lon, lat]) => `${lat},${lon}`)
    .join('|');
  $('#google-link').href = `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&travelmode=driving&waypoints=${encodeURIComponent(waypoints)}`;
  $('#waze-link').href = `https://www.waze.com/ul?ll=${encodeURIComponent(destination)}&navigate=yes`;
  $('#apple-link').href = `https://maps.apple.com/?saddr=${encodeURIComponent(origin)}&daddr=${encodeURIComponent(destination)}&dirflg=d`;
}

async function calculate(event) {
  event?.preventDefault();
  showFormMessage();
  const button = $('#calculate');
  button.disabled = true;
  button.querySelector('span:first-child').textContent = 'Calcul en cours…';
  try {
    const [start, end] = await Promise.all([
      resolveAddress(startAutocomplete),
      resolveAddress(endAutocomplete),
    ]);
    const payload = {
      start,
      end,
      start_label: $('#start').value,
      end_label: $('#end').value,
      fuel_type: 'SP95-E10',
      fuel_price: Number($('#fuel-price').value),
      min_savings: Number($('#min-savings').value),
      max_extra_minutes: state.showAll ? null : state.maxExtra,
      show_all: state.showAll,
      motorway_consumption: Number($('#motorway-consumption').value),
      road_consumption: Number($('#road-consumption').value),
    };
    const response = await fetch('/api/routes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Calcul impossible');
    }
    const data = await response.json();
    $('#map-title').textContent = (
      `${$('#start').value.split(/[,(]/)[0].trim()} → ${$('#end').value.split(/[,(]/)[0].trim()}`
    );
    renderResults(data);
  } catch (error) {
    showFormMessage(error.message);
  } finally {
    button.disabled = false;
    button.querySelector('span:first-child').textContent = 'Comparer les itinéraires';
  }
}

$('#route-form').addEventListener('submit', calculate);
$('#swap').addEventListener('click', () => {
  const startValue = $('#start').value;
  const startCoords = $('#start-coords').value;
  $('#start').value = $('#end').value;
  $('#start-coords').value = $('#end-coords').value;
  $('#end').value = startValue;
  $('#end-coords').value = startCoords;
  showFormMessage();
});
$('#time-chips').querySelectorAll('button').forEach((button) => {
  button.addEventListener('click', () => {
    $('#time-chips').querySelectorAll('button').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    state.showAll = button.dataset.minutes === 'all';
    state.maxExtra = state.showAll ? null : Number(button.dataset.minutes);
  });
});
$('#nav-toggle').addEventListener('click', () => {
  const menu = $('#nav-options');
  const open = menu.classList.toggle('open');
  $('#nav-toggle').setAttribute('aria-expanded', String(open));
});
$('#map-fit').addEventListener('click', () => window.RoutecoMap?.fitSelected());
$('#map-expand').addEventListener('click', () => {
  state.mapExpanded = !state.mapExpanded;
  $('.map-card').classList.toggle('expanded', state.mapExpanded);
  $('#map-expand').textContent = state.mapExpanded ? 'Réduire' : 'Agrandir';
  $('#map-expand').setAttribute('aria-pressed', String(state.mapExpanded));
  window.RoutecoMap?.resize();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && state.mapExpanded) {
    state.mapExpanded = false;
    $('.map-card').classList.remove('expanded');
    $('#map-expand').textContent = 'Agrandir';
    $('#map-expand').setAttribute('aria-pressed', 'false');
    window.RoutecoMap?.resize();
  }
});
document.addEventListener('click', (event) => {
  if (!event.target.closest('.nav-menu')) {
    $('#nav-options').classList.remove('open');
    $('#nav-toggle').setAttribute('aria-expanded', 'false');
  }
});

health();
