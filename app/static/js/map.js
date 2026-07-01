/**
 * map.js — Leaflet map para Deptos Scraper
 * Reemplaza el mapa Folium de Streamlit.
 */

// ---- Mapa base ----
const map = L.map('map', {
  center: [-34.6037, -58.3816],
  zoom: 13,
  preferCanvas: true,
});

L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
  subdomains: 'abcd',
  maxZoom: 19,
}).addTo(map);

// ---- Estado de capas ----
const layers = {
  barrios: null,
  ev: null,
  subte: null,
  gyms: null,
  deptos: L.layerGroup().addTo(map),
};

// ---- Colores ----
const COLOR_SUBTE = { A:'#00AEEF', B:'#ED1C24', C:'#0054A6', D:'#00802F', E:'#662D91', H:'#FFD100' };
const COLOR_GYMS  = { SportClub:'#003366', Megatlon:'#ff6600', Smartfit:'#cc0000' };
const EV_COLORS   = { PARQUE:'#2d6a4f', PLAZA:'#74c69d', 'JARDÍN BOTANICO':'#1b4332' };

function scoreColor(score) {
  if (score === null || score === undefined) return '#555';
  if (score >= 70) return '#1a9641';
  if (score >= 55) return '#74c69d';
  if (score >= 40) return '#fd8d3c';
  return '#d73027';
}

function precioColor(precio, minP, maxP) {
  if (!precio || maxP === minP) return '#888';
  const t = (precio - minP) / (maxP - minP);
  const r = Math.round(26 + (215 - 26) * t);
  const g = Math.round(150 + (48 - 150) * t);
  const b = Math.round(65 + (39 - 65) * t);
  return `rgb(${r},${g},${b})`;
}

function fmt(v) {
  if (v === null || v === undefined) return '—';
  return Number(v).toLocaleString('es-AR');
}

// ---- Popup de departamento ----
function buildPopup(p) {
  const score = p.score !== null ? `<strong style="color:#7c8cf8;">${p.score.toFixed(1)}</strong>` : '—';
  return `<div class="prop-popup" style="background:#1a1d27;color:#e0e0e0;border-radius:8px;padding:10px;min-width:230px;font-size:.84rem;">
    <h6 style="color:#7c8cf8;margin-bottom:.4rem;">${p.direccion || p.titulo || 'Sin dirección'}</h6>
    <div style="margin-bottom:.4rem;">
      <span style="background:#2d3148;padding:2px 6px;border-radius:4px;font-size:.72rem;">${p.portal}</span>
      <span style="background:#1e2235;padding:2px 6px;border-radius:4px;font-size:.72rem;margin-left:4px;">${p.barrio || ''}</span>
      ${p.activo ? '' : '<span style="background:#7b1f1f;padding:2px 6px;border-radius:4px;font-size:.72rem;margin-left:4px;">inactivo</span>'}
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:.82rem;">
      <tr><td style="color:#6c7293;padding:2px 0;">Score</td><td>${score}</td></tr>
      <tr><td style="color:#6c7293;padding:2px 0;">Precio</td><td>$${fmt(p.precio)}</td></tr>
      <tr><td style="color:#6c7293;padding:2px 0;">Expensas</td><td>${p.expensas ? '$' + fmt(p.expensas) : '—'}</td></tr>
      <tr><td style="color:#6c7293;padding:2px 0;">Costo total</td><td><strong>$${fmt(p.costo_total)}</strong></td></tr>
      <tr><td style="color:#6c7293;padding:2px 0;">Ambientes</td><td>${p.ambientes ?? '—'} amb / ${p.dormitorios ?? '—'} dorm</td></tr>
      <tr><td style="color:#6c7293;padding:2px 0;">M² cubiertos</td><td>${p.metros_cubiertos ? p.metros_cubiertos + ' m²' : '—'}</td></tr>
      <tr><td style="color:#6c7293;padding:2px 0;">Subte</td><td>${p.distancia_m_subte ? fmt(p.distancia_m_subte) + ' m' : '—'}</td></tr>
      <tr><td style="color:#6c7293;padding:2px 0;">Verde</td><td>${p.dist_verde_final ? fmt(p.dist_verde_final) + ' m' : '—'}</td></tr>
      <tr><td style="color:#6c7293;padding:2px 0;">Gym</td><td>${p.distancia_m_gym ? fmt(p.distancia_m_gym) + ' m' : '—'}</td></tr>
      ${p.snap_warning ? '<tr><td colspan="2" style="color:#fd8d3c;font-size:.75rem;">⚠ snap_warning</td></tr>' : ''}
    </table>
    ${p.url ? `<div style="margin-top:.5rem;"><a href="${p.url}" target="_blank" style="color:#7c8cf8;font-size:.8rem;">Ver en portal ↗</a></div>` : ''}
  </div>`;
}

// ---- Cargar capas base ----
const LAYER_CHECKBOX_IDS = { barrios: 'layBarrios', ev: 'layEV', subte: 'laySubte', gyms: 'layGyms' };

async function loadBaseLayer(key, url, styleFn, labelFn) {
  try {
    const resp = await fetch(url);
    const gj = await resp.json();
    const layer = L.geoJSON(gj, { style: styleFn, onEachFeature: labelFn });
    layers[key] = layer;
    if (document.getElementById(LAYER_CHECKBOX_IDS[key])?.checked) {
      layer.addTo(map);
    }
  } catch(e) { console.warn(`Error cargando capa ${key}:`, e); }
}

async function initBaseLayers() {
  // Barrios
  await loadBaseLayer('barrios', '/api/shapes/barrios',
    () => ({ color: '#4a5080', weight: 1, fillOpacity: 0.05, fillColor: '#4a5080' }),
    (feature, layer) => layer.bindTooltip(feature.properties?.nombre || '', { sticky: true, opacity: 0.85 })
  );

  // Espacios verdes
  await loadBaseLayer('ev', '/api/shapes/ev',
    (f) => {
      const c = EV_COLORS[f.properties?.clasificac] || '#74c69d';
      return { color: c, weight: 0.5, fillColor: c, fillOpacity: 0.35 };
    },
    null
  );

  // Subte (líneas + estaciones como un solo layer)
  try {
    const [lineas, estaciones] = await Promise.all([
      fetch('/api/shapes/subte/lineas').then(r=>r.json()),
      fetch('/api/shapes/subte/estaciones').then(r=>r.json()),
    ]);
    const subteGroup = L.layerGroup();
    L.geoJSON(lineas, {
      style: f => {
        const letra = (f.properties?.LINEASUB || '').replace('LINEA ', '').trim();
        return { color: COLOR_SUBTE[letra] || '#aaa', weight: 3, opacity: 0.8 };
      },
    }).addTo(subteGroup);
    L.geoJSON(estaciones, {
      pointToLayer: (f, latlng) => L.circleMarker(latlng, {
        radius: 4, fillColor: COLOR_SUBTE[f.properties?.linea] || '#aaa',
        color: '#fff', weight: 1, fillOpacity: 0.9,
      }),
      onEachFeature: (f, layer) => layer.bindTooltip(f.properties?.estacion || '', { sticky: true }),
    }).addTo(subteGroup);
    layers['subte'] = subteGroup;
    if (document.getElementById(LAYER_CHECKBOX_IDS['subte'])?.checked) subteGroup.addTo(map);
  } catch(e) { console.warn('Error cargando subte:', e); }

  // Gyms
  try {
    const gj = await fetch('/api/shapes/gyms').then(r=>r.json());
    layers['gyms'] = L.geoJSON(gj, {
      pointToLayer: (f, latlng) => L.circleMarker(latlng, {
        radius: 5,
        fillColor: f.properties?.color_map || COLOR_GYMS[f.properties?.cadena] || '#888',
        color: '#fff', weight: 1, fillOpacity: 0.85,
      }),
      onEachFeature: (f, layer) => layer.bindTooltip(
        `${f.properties?.cadena || 'Gym'}: ${f.properties?.nombre || ''}`, { sticky: true }
      ),
    });
    if (document.getElementById(LAYER_CHECKBOX_IDS['gyms'])?.checked) layers['gyms'].addTo(map);
  } catch(e) { console.warn('Error cargando gyms:', e); }
}

// ---- Cargar departamentos ----
let colorMode = 'score';

async function loadDeptos() {
  const perfilSel = document.getElementById('selPerfil');
  const perfilId = perfilSel?.value || '';
  const globalView = perfilId === 'global';
  const activoSel = document.querySelector('input[name="activo"]:checked')?.value;
  const precioMin = document.getElementById('precioMin')?.value;
  const precioMax = document.getElementById('precioMax')?.value;
  const scoreMin = document.getElementById('scoreMin')?.value;
  const dormChecked = [...document.querySelectorAll('.dorm-btn.active')].map(b => b.dataset.val);

  let url = '/api/departamentos?';
  if (activoSel) url += `activo=${activoSel}&`;
  if (globalView) url += 'global_view=true&';
  else if (perfilId) url += `perfil_id=${perfilId}&`;
  if (precioMin) url += `precio_min=${precioMin}&`;
  if (precioMax) url += `precio_max=${precioMax}&`;
  if (scoreMin) url += `score_min=${scoreMin}&`;
  dormChecked.forEach(d => { url += `dormitorios=${d}&`; });

  try {
    const resp = await fetch(url, { credentials: 'include' });
    const gj = await resp.json();
    const features = (gj.features || []).filter(f => f.geometry);

    layers.deptos.clearLayers();

    // Calcular rango de precios para colorear
    const precios = features.map(f => f.properties.precio).filter(Boolean);
    const minP = Math.min(...precios);
    const maxP = Math.max(...precios);

    features.forEach(f => {
      const p = f.properties;
      const [lon, lat] = f.geometry.coordinates;
      const color = colorMode === 'score'
        ? scoreColor(p.score)
        : precioColor(p.precio, minP, maxP);
      const radius = 5 + (p.dormitorios || 0);

      const marker = L.circleMarker([lat, lon], {
        radius,
        fillColor: color,
        color: p.activo ? '#fff' : '#555',
        weight: p.activo ? 1 : 0.5,
        fillOpacity: p.activo ? 0.85 : 0.4,
      });

      marker.bindPopup(buildPopup(p), { maxWidth: 280 });
      layers.deptos.addLayer(marker);
    });

    const counter = document.getElementById('contadorProps');
    if (counter) counter.textContent = `${features.length} propiedades cargadas`;

  } catch(e) {
    console.error('Error cargando departamentos:', e);
  }
}

// ---- Toggle de capas ----
document.querySelectorAll('.layer-toggle').forEach(cb => {
  cb.addEventListener('change', () => {
    const key = cb.dataset.layer;
    if (!layers[key]) return;
    if (cb.checked) layers[key].addTo(map);
    else map.removeLayer(layers[key]);
  });
});

// ---- Toggle de modo de color ----
document.querySelectorAll('input[name="colorMode"]').forEach(r => {
  r.addEventListener('change', () => {
    colorMode = r.value;
    const ls = document.getElementById('legendaScore');
    const lp = document.getElementById('legendaPrecio');
    if (ls) ls.style.display = colorMode === 'score' ? '' : 'none';
    if (lp) lp.style.display = colorMode === 'precio' ? '' : 'none';
    loadDeptos();
  });
});

// ---- Botones de dormitorios ----
document.querySelectorAll('.dorm-btn').forEach(btn => {
  btn.addEventListener('click', () => btn.classList.toggle('active'));
});

// ---- Botón aplicar filtros ----
document.getElementById('btnAplicar')?.addEventListener('click', loadDeptos);

// ---- Init ----
initBaseLayers();
loadDeptos();
