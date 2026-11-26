// Estadísticas: visitas, visitantes, páginas más vistas, fuentes de tráfico y reparto por sitio.
import { api } from '../api.js';
import { colorSeguro, dona, graficaLineas, numero } from '../grafica.js';
import { cargando, el, errorDeCarga } from '../ui.js';

const PERIODOS = [
  { clave: '1d', texto: 'Hoy' }, { clave: '1w', texto: '1 semana' }, { clave: '2w', texto: '2 semanas' },
  { clave: '1m', texto: '1 mes' }, { clave: '3m', texto: '3 meses' }, { clave: '1y', texto: '1 año' },
];
const COMPARACION = { '1d': 'ayer', '1w': 'la semana anterior', '2w': 'las 2 semanas anteriores', '1m': 'el mes anterior', '3m': 'los 3 meses anteriores', '1y': 'el año anterior' };

// Se recuerdan mientras dure la pestaña: al volver de «Sitios» se ve lo mismo que antes.
let periodoElegido = '1w';
let sitioElegido = null;

function delta(porcentaje, periodo) {
  if (porcentaje === null || porcentaje === undefined) return el('span', { class: 'kpi__delta kpi__delta--igual' }, 'Sin datos del periodo anterior');
  const clase = porcentaje > 0 ? 'sube' : porcentaje < 0 ? 'baja' : 'igual';
  const flecha = porcentaje > 0 ? '▲' : porcentaje < 0 ? '▼' : '=';
  const texto = porcentaje > 0 ? `+${porcentaje}` : String(porcentaje);
  return el('span', { class: `kpi__delta kpi__delta--${clase}` }, `${flecha} ${texto.replace('.', ',')} % frente a ${COMPARACION[periodo]}`);
}

function tarjetaKpi(id, titulo, valor, pie) {
  return el('div', { class: 'kpi', dataset: { kpi: id } },
    el('span', { class: 'kpi__titulo' }, titulo), el('strong', { class: 'kpi__valor' }, valor), pie);
}

function barra(porcentaje, color) {
  const relleno = el('span', { class: 'barra__relleno' });
  relleno.style.width = `${Math.max(2, Math.min(100, porcentaje))}%`;      // por CSSOM: la CSP no permite style="" en el HTML
  if (color) relleno.style.background = colorSeguro(color);
  return el('span', { class: 'barra' }, relleno);
}

function puntoDeSitio(color) {
  const punto = el('span', { class: 'punto-sitio punto-sitio--chico', 'aria-hidden': 'true' });
  punto.style.background = colorSeguro(color);
  return punto;
}

export async function montar(contenedor) {
  const cuerpo = el('div', { class: 'vista' });
  contenedor.replaceChildren(cuerpo);
  let sitios = [];
  let numeroPeticion = 0;

  async function cargar() {
    const mia = ++numeroPeticion;
    cuerpo.replaceChildren(cargando('Calculando estadísticas…'));
    try {
      if (!sitios.length) sitios = await api.listarTodo('/api/v1/sites');
      if (sitioElegido && !sitios.some((s) => s.site_id === sitioElegido)) sitioElegido = null;
      const parametros = { period: periodoElegido, ...(sitioElegido ? { site_id: sitioElegido } : {}) };
      const r = await api.obtener('/api/v1/stats', parametros);
      if (mia === numeroPeticion) pintar(r.datos);
    } catch (error) {
      if (mia === numeroPeticion) cuerpo.replaceChildren(errorDeCarga(error, cargar));
    }
  }

  function filtros() {
    const chips = (lista, esActivo, alElegir, etiqueta, id) => el('div', { class: 'chips', role: 'group', 'aria-label': etiqueta, id },
      lista.map((x) => el('button', { type: 'button', class: 'chip', dataset: { valor: x.clave ?? '' }, 'aria-pressed': String(esActivo(x)), onclick: () => alElegir(x) }, x.texto)));
    const filas = [chips(PERIODOS, (p) => p.clave === periodoElegido, (p) => { periodoElegido = p.clave; cargar(); }, 'Periodo', 'filtro-periodo')];
    if (sitios.length > 1) {
      const opciones = [{ clave: null, texto: 'Todos los sitios' }, ...sitios.map((s) => ({ clave: s.site_id, texto: s.name }))];
      filas.push(chips(opciones, (o) => o.clave === sitioElegido, (o) => { sitioElegido = o.clave; cargar(); }, 'Sitio', 'filtro-sitio'));
    }
    return el('div', { class: 'barra-filtros barra-filtros--apilada' }, filas);
  }

  function cabecera() {
    return el('div', { class: 'vista__cab' },
      el('h1', {}, 'Estadísticas'),
      el('div', { class: 'vista__cab-acciones' },
        el('button', { type: 'button', class: 'boton', id: 'btn-actualizar', onclick: cargar }, 'Actualizar'),
        el('a', { class: 'boton', href: '#/sitios', id: 'enlace-sitios' }, 'Sitios')));
  }

  function pintarSinSitios() {
    cuerpo.replaceChildren(cabecera(), el('div', { class: 'vacio-guiado', id: 'estadisticas-sin-sitios' },
      el('p', {}, el('strong', {}, 'Todavía no monitoreas ningún sitio.')),
      el('p', { class: 'dato' }, 'Agrega tu blog y pega su línea de código para empezar a ver cuántas visitas recibe.'),
      el('a', { class: 'boton boton--primario', href: '#/sitios' }, 'Agregar un sitio')));
  }

  function pintar(d) {
    if (!sitios.length) { pintarSinSitios(); return; }
    const activos = sitios.filter((s) => s.is_active).length;
    const t = d.totals;
    const kpis = el('div', { class: 'kpis', id: 'kpis' },
      tarjetaKpi('visitas', 'Visitas', numero(t.views), delta(t.views_delta_pct, d.period)),
      tarjetaKpi('visitantes', 'Visitantes', numero(t.visitors), delta(t.visitors_delta_pct, d.period)),
      tarjetaKpi('paginas', 'Páginas con visitas', numero(t.pages), el('span', { class: 'kpi__delta kpi__delta--igual' }, 'Distintas en el periodo')),
      tarjetaKpi('sitios', 'Sitios activos', `${activos} de ${sitios.length}`, el('span', { class: 'kpi__delta kpi__delta--igual' }, activos < sitios.length ? 'Los pausados no cuentan visitas' : 'Todos cuentan visitas')));

    const partes = [cabecera(), filtros(), kpis];
    if (t.views === 0) {
      partes.push(el('div', { class: 'vacio-guiado', id: 'estadisticas-vacio' },
        el('p', {}, el('strong', {}, 'Aún no hay visitas en este periodo.')),
        el('p', { class: 'dato' }, 'Si acabas de agregar el sitio, pega su línea de código en tus páginas y abre el blog para probar. Si el servidor estaba dormido, la primera visita puede tardar un minuto en contarse.'),
        el('a', { class: 'boton', href: '#/sitios' }, 'Ver el código de cada sitio')));
    } else {
      partes.push(tarjetaTiempo(d), el('div', { class: 'dos-columnas' }, ...columnas(d)), tarjetaPaginas(d));
    }
    partes.push(el('p', { class: 'nota nota--pie' },
      `Del ${d.from_date.split('-').reverse().join('/')} al ${d.to_date.split('-').reverse().join('/')} · horario UTC${d.utc_offset_hours >= 0 ? '+' : '−'}${Math.abs(d.utc_offset_hours)}. `,
      '«Visitantes» son visitantes distintos por día, sumados: no se rastrea a nadie de un día a otro.'));
    cuerpo.replaceChildren(...partes);
  }

  function tarjetaTiempo(d) {
    return el('section', { class: 'tarjeta tarjeta--grafica', id: 'tarjeta-tiempo', 'aria-labelledby': 'titulo-tiempo' },
      el('div', { class: 'tarjeta__fila' },
        el('h2', { class: 'tarjeta__titulo tarjeta__titulo--limpio', id: 'titulo-tiempo' }, d.granularity === 'hour' ? 'Visitas por hora' : 'Visitas en el tiempo'),
        el('ul', { class: 'leyenda' },
          el('li', {}, el('span', { class: 'leyenda__marca leyenda__marca--visitas' }), 'Visitas'),
          el('li', {}, el('span', { class: 'leyenda__marca leyenda__marca--visitantes' }), 'Visitantes'))),
      graficaLineas(d.series));
  }

  function columnas(d) {
    const salida = [];
    if (!sitioElegido && d.sites.length > 1) {                           // reparto por sitio (solo si hay varios)
      const total = d.totals.views;
      salida.push(el('section', { class: 'tarjeta', id: 'tarjeta-sitios' },
        el('h2', { class: 'tarjeta__titulo' }, 'Visitas por sitio'),
        el('div', { class: 'reparto' },
          dona(d.sites.map((s) => ({ valor: s.views, color: s.color, titulo: `${s.name}: ${numero(s.views)} visitas (${s.share_pct} %)` })), numero(total), 'visitas'),
          el('ul', { class: 'reparto__lista' }, d.sites.map((s) => el('li', {},
            puntoDeSitio(s.color), el('span', { class: 'reparto__nombre' }, s.name),
            el('span', { class: 'reparto__dato mono' }, `${numero(s.views)} · ${String(s.share_pct).replace('.', ',')} %`)))))));
    }
    const maxFuente = Math.max(...d.referrers.map((f) => f.views), 1);
    salida.push(el('section', { class: 'tarjeta', id: 'tarjeta-fuentes' },
      el('h2', { class: 'tarjeta__titulo' }, 'De dónde llegan'),
      d.referrers.length
        ? el('ul', { class: 'ranking ranking--simple' }, d.referrers.map((f) => el('li', { class: 'ranking__fila' },
          el('span', { class: 'ranking__nombre' }, f.source ?? 'Directo o sin referencia'),
          barra((f.views / maxFuente) * 100), el('span', { class: 'ranking__dato mono' }, numero(f.views)))))
        : el('p', { class: 'dato' }, 'Todavía no hay fuentes de tráfico.')));
    return salida;
  }

  function tarjetaPaginas(d) {
    const maximo = Math.max(...d.top_pages.map((p) => p.views), 1);
    const variosSitios = sitios.length > 1 && !sitioElegido;
    return el('section', { class: 'tarjeta', id: 'tarjeta-paginas' },
      el('h2', { class: 'tarjeta__titulo' }, 'Páginas más vistas'),
      el('ol', { class: 'ranking' }, d.top_pages.map((p, i) => el('li', { class: 'ranking__fila ranking__fila--pagina', dataset: { ruta: p.path } },
        el('span', { class: 'ranking__pos mono' }, String(i + 1)),
        el('span', { class: 'ranking__nombre' }, el('span', { class: 'mono ranking__ruta' }, p.path),
          variosSitios ? el('span', { class: 'ranking__sitio' }, puntoDeSitio(p.color), p.site_name) : null),
        barra((p.views / maximo) * 100, p.color),
        el('span', { class: 'ranking__dato mono', title: `${numero(p.visitors)} visitantes` }, `${numero(p.views)} visitas`)))));
  }

  await cargar();
  return {};
}
