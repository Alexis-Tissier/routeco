(() => {
  let map;
  let routeLayers = [];
  let endpointLayers = [];
  let fittedRouteIds = '';

  function ensureMap() {
    if (map || !window.L) return map;
    map = L.map('route-map', { zoomControl: true, preferCanvas: true });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap',
    }).addTo(map);
    map.setView([46.6, 2.4], 6);
    return map;
  }

  function clearLayers() {
    [...routeLayers, ...endpointLayers].forEach((layer) => layer.remove());
    routeLayers = [];
    endpointLayers = [];
  }

  function renderMap(routes, selectedRoute) {
    const instance = ensureMap();
    if (!instance || !routes.length || !selectedRoute) return;
    clearLayers();

    [...routes]
      .sort((route) => route.id === selectedRoute.id ? 1 : -1)
      .forEach((route) => {
        const selected = route.id === selectedRoute.id;
        const points = route.geometry.map(([lon, lat]) => [lat, lon]);
        const line = L.polyline(points, {
          color: selected ? '#e85b35' : '#77817c',
          weight: selected ? 7 : 5,
          opacity: selected ? 1 : 0.55,
          lineCap: 'round',
          lineJoin: 'round',
        }).addTo(instance);
        line.on('click', () => window.RoutecoMap.onSelect?.(route.id));
        line.bindTooltip(route.label, { sticky: true });
        routeLayers.push(line);
      });

    const points = selectedRoute.geometry.map(([lon, lat]) => [lat, lon]);
    endpointLayers.push(
      L.circleMarker(points[0], {
        radius: 8, color: '#fff', weight: 4, fillColor: '#18211d', fillOpacity: 1,
      }).addTo(instance),
      L.circleMarker(points[points.length - 1], {
        radius: 8, color: '#fff', weight: 4, fillColor: '#e85b35', fillOpacity: 1,
      }).addTo(instance),
    );

    const routeIds = routes.map((route) => route.id).join('|');
    if (routeIds !== fittedRouteIds) {
      const allPoints = routes.flatMap(
        (route) => route.geometry.map(([lon, lat]) => [lat, lon]),
      );
      instance.fitBounds(L.latLngBounds(allPoints), { padding: [42, 42] });
      fittedRouteIds = routeIds;
    }
  }

  window.RoutecoMap = {
    onSelect: null,
    render(routes, selectedRoute) {
      renderMap(routes, selectedRoute);
    },
  };
  window.RoutecoMap.onSelect = (id) => {
    document.querySelector(`.route-card[data-id="${CSS.escape(id)}"]`)?.click();
  };
})();
