(() => {
  const $ = (selector) => document.querySelector(selector);

  function renderSchematic(routes, selectedRoute) {
    if (!routes.length || !selectedRoute) return;
    const allPoints = routes.flatMap((route) => route.geometry);
    if (!allPoints.length) return;

    const lons = allPoints.map((point) => point[0]);
    const lats = allPoints.map((point) => point[1]);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const pad = 78;
    const width = 900 - pad * 2;
    const height = 520 - pad * 2;

    const project = ([lon, lat]) => {
      const x = pad + ((lon - minLon) / Math.max(0.00001, maxLon - minLon)) * width;
      const y = 520 - pad - ((lat - minLat) / Math.max(0.00001, maxLat - minLat)) * height;
      return [x, y];
    };
    const pathFor = (geometry) => geometry
      .map((point, index) => `${index ? 'L' : 'M'} ${project(point).join(' ')}`)
      .join(' ');

    const ordered = [...routes].sort((a) => a.id === selectedRoute.id ? 1 : -1);
    $('#route-lines').innerHTML = ordered.map((route) => {
      const selected = route.id === selectedRoute.id;
      return `<path d="${pathFor(route.geometry)}" fill="none" stroke="${selected ? '#e85b35' : '#98a19c'}" stroke-width="${selected ? 7 : 3}" stroke-linecap="round" stroke-linejoin="round" opacity="${selected ? 1 : 0.42}" ${selected ? 'filter="url(#shadow)"' : ''}/>`;
    }).join('');

    const first = project(selectedRoute.geometry[0]);
    const last = project(selectedRoute.geometry[selectedRoute.geometry.length - 1]);
    $('#markers').innerHTML = `
      <circle cx="${first[0]}" cy="${first[1]}" r="12" fill="#18211d" stroke="#fff" stroke-width="5" filter="url(#shadow)"/>
      <circle cx="${last[0]}" cy="${last[1]}" r="12" fill="#e85b35" stroke="#fff" stroke-width="5" filter="url(#shadow)"/>`;
  }

  // The UI calls this adapter rather than manipulating the SVG directly.
  // A self-hosted MapLibre implementation can replace this method later
  // without changing route selection, cards or API responses.
  window.RoutecoMap = {
    render(routes, selectedRoute) {
      renderSchematic(routes, selectedRoute);
    },
  };
})();
