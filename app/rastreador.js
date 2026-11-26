/* Seguimiento de visitas del CMS (SEGOPE.dev). Sin cookies, sin datos personales.
   Uso:  <script defer src="https://TU-API/t.js" data-site="tu-dominio.com"></script>
   data-site es opcional: si falta, se usa el dominio de la página. */
(function () {
  'use strict';
  var actual = document.currentScript;
  if (!actual || !actual.src) return;
  if (navigator.doNotTrack === '1' || window.doNotTrack === '1') return;       // se respeta «No rastrear»
  var sitio = actual.getAttribute('data-site') || location.hostname;
  var api = new URL(actual.src).origin;
  var cuerpo = JSON.stringify({ site: sitio, path: location.pathname, referrer: document.referrer || null });
  var destino = api + '/api/v1/track';
  try {
    if (navigator.sendBeacon && navigator.sendBeacon(destino, cuerpo)) return;   // texto plano: no necesita CORS
  } catch (e) { /* se prueba con fetch */ }
  try {
    fetch(destino, { method: 'POST', body: cuerpo, keepalive: true, mode: 'no-cors', credentials: 'omit' });
  } catch (e) { /* un fallo del seguimiento nunca debe afectar a la página */ }
})();
