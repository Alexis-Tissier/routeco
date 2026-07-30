(() => {
  let map;
  let routeLayers = [];
  let endpointLayers = [];
  let fittedRouteIds = '';
  let activeRoute = null;

  function ensureMap() {
    if (map || !window.L) return map;
    map = L.map('route-map', {
      zoomControl: true,
      preferCanvas: true,
      minZoom: 4,
    });
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

  function routeBounds(route) {
    return L.latLngBounds(route.geometry.map(([lon, lat]) => [lat, lon]));
  }

  function fitRoute(route) {
    const instance = ensureMap();
    if (!instance || !route?.geometry?.length) return;
    instance.fitBounds(routeBounds(route), { padding: [46, 46], maxZoom: 12 });
  }

  function renderMap(routes, selectedRoute) {
    const instance = ensureMap();
    if (!instance || !routes.length || !selectedRoute) return;
    activeRoute = selectedRoute;
    clearLayers();

    [...routes]
      .sort((route) => (route.id === selectedRoute.id ? 1 : -1))
      .forEach((route) => {
        const selected = route.id === selectedRoute.id;
        const points = route.geometry.map(([lon, lat]) => [lat, lon]);
        const line = L.polyline(points, {
          color: selected ? '#e85b35' : '#77817c',
          weight: selected ? 7 : 5,
          opacity: selected ? 1 : 0.48,
          lineCap: 'round',
          lineJoin: 'round',
        }).addTo(instance);
        line.on('click', () => window.RoutecoSelectRoute?.(route.id));
        line.bindTooltip(
          `${route.label} · ${route.duration_minutes} min · ${Number(route.total_cost).toFixed(2)} €`,
          { sticky: true },
        );
        routeLayers.push(line);
      });

    const points = selectedRoute.geometry.map(([lon, lat]) => [lat, lon]);
    endpointLayers.push(
      L.circleMarker(points[0], {
        radius: 8,
        color: '#fff',
        weight: 4,
        fillColor: '#18211d',
        fillOpacity: 1,
      }).addTo(instance),
      L.circleMarker(points[points.length - 1], {
        radius: 8,
        color: '#fff',
        weight: 4,
        fillColor: '#e85b35',
        fillOpacity: 1,
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
    render(routes, selectedRoute) {
      renderMap(routes, selectedRoute);
    },
    fitSelected() {
      fitRoute(activeRoute);
    },
    resize() {
      window.setTimeout(() => {
        ensureMap()?.invalidateSize();
        fitRoute(activeRoute);
      }, 220);
    },
  };
})();
