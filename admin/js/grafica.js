// Gráficas SVG hechas a mano (sin librerías): la consola no puede cargar scripts de otros sitios (CSP).
// Igual que el(): todo se construye con nodos, nunca con innerHTML. Los colores de las líneas van en clases CSS
// (admin.css); solo los colores de cada sitio, que ya validó la API (#rrggbb), se ponen como atributo.
const NS = 'http://www.w3.org/2000/svg';

export function svg(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElementNS(NS, etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) {
    if (valor === undefined || valor === null || valor === false) continue;
    nodo.setAttribute(clave === 'className' ? 'class' : clave, String(valor));
  }
  nodo.append(...hijos.flat().filter((h) => h !== null && h !== undefined && h !== false));
  return nodo;
}

export const colorSeguro = (color, defecto = '#ef4444') => (/^#[0-9a-f]{6}$/i.test(color ?? '') ? color : defecto);
export const numero = (n) => Number(n ?? 0).toLocaleString('es-MX');

// «2026-11-24» -> «24 nov»; las horas («09:00») se dejan igual.
export function etiquetaFecha(etiqueta) {
  if (etiqueta.includes(':')) return etiqueta;
  const [anio, mes, dia] = etiqueta.split('-').map(Number);
  return new Date(anio, mes - 1, dia).toLocaleDateString('es-MX', { day: 'numeric', month: 'short' }).replace('.', '');
}

// Más de ~120 puntos (periodo de un año) no se leen bien: se suman por semana.
export function agruparPorSemana(serie) {
  const semanas = [];
  for (let i = 0; i < serie.length; i += 7) {
    const trozo = serie.slice(i, i + 7);
    semanas.push({
      label: trozo[0].label, semana: true,
      views: trozo.reduce((s, p) => s + p.views, 0),
      visitors: trozo.reduce((s, p) => s + p.visitors, 0),
    });
  }
  return semanas;
}

// Tope «redondo» del eje vertical. El eje tiene 4 tramos iguales y cada marca debe ser un número entero
// (nadie tiene 12,5 visitas): se busca el paso más chico, entre los «bonitos», cuyo cuádruple alcance el máximo.
export function techoRedondo(maximo) {
  if (maximo <= 4) return 4;
  const base = 10 ** Math.floor(Math.log10(maximo / 4));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) {
    const paso = Math.round(m * base * 1000) / 1000;
    if (Number.isInteger(paso) && paso * 4 >= maximo) return paso * 4;
  }
  return 40 * base;
}

function titulo(punto) {
  const cuando = punto.semana ? `Semana del ${etiquetaFecha(punto.label)}` : etiquetaFecha(punto.label);
  return `${cuando}: ${numero(punto.views)} visitas · ${numero(punto.visitors)} visitantes`;
}

// Líneas de visitas y de visitantes. Cada punto lleva un <title>: al pasar el cursor el navegador muestra el dato.
export function graficaLineas(serie) {
  const ancho = 720, alto = 260, izq = 44, der = 12, arriba = 14, abajo = 28;
  const puntos = serie.length > 120 ? agruparPorSemana(serie) : serie;
  const techo = techoRedondo(Math.max(...puntos.map((p) => Math.max(p.views, p.visitors)), 0));
  const x = (i) => (puntos.length === 1 ? (izq + ancho - der) / 2 : izq + (i * (ancho - izq - der)) / (puntos.length - 1));
  const y = (valor) => arriba + (alto - arriba - abajo) * (1 - valor / techo);
  const resumen = `Visitas y visitantes: ${puntos.length} puntos, máximo ${numero(techo)}`;
  const grafica = svg('svg', { className: 'grafica', viewBox: `0 0 ${ancho} ${alto}`, role: 'img', 'aria-label': resumen, preserveAspectRatio: 'xMidYMid meet' });

  for (let i = 0; i <= 4; i++) {                                    // rejilla y eje vertical
    const valor = (techo * i) / 4;
    grafica.append(
      svg('line', { className: 'grafica__rejilla', x1: izq, x2: ancho - der, y1: y(valor), y2: y(valor) }),
      svg('text', { className: 'grafica__eje', x: izq - 6, y: y(valor) + 4, 'text-anchor': 'end' }, numero(valor)));
  }
  const cantidadEtiquetas = Math.min(puntos.length, 6);               // eje horizontal: ~6 etiquetas repartidas
  for (let k = 0; k < cantidadEtiquetas; k++) {
    const i = cantidadEtiquetas === 1 ? 0 : Math.round((k * (puntos.length - 1)) / (cantidadEtiquetas - 1));
    // la primera y la última etiqueta se alinean hacia adentro para que no se corten en los bordes
    const ancla = k === 0 && cantidadEtiquetas > 1 ? 'start' : k === cantidadEtiquetas - 1 && cantidadEtiquetas > 1 ? 'end' : 'middle';
    grafica.append(svg('text', { className: 'grafica__eje', x: x(i), y: alto - 8, 'text-anchor': ancla }, etiquetaFecha(puntos[i].label)));
  }

  const trazo = (clave) => puntos.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)} ${y(p[clave]).toFixed(1)}`).join(' ');
  const base = y(0).toFixed(1);
  grafica.append(
    svg('path', { className: 'grafica__area', d: `${trazo('views')} L${x(puntos.length - 1).toFixed(1)} ${base} L${x(0).toFixed(1)} ${base} Z` }),
    svg('path', { className: 'grafica__linea grafica__linea--visitantes', d: trazo('visitors'), fill: 'none' }),
    svg('path', { className: 'grafica__linea grafica__linea--visitas', d: trazo('views'), fill: 'none' }));

  const visibles = puntos.length <= 31;                              // pocos puntos: se dibujan; muchos: solo zona sensible
  puntos.forEach((p, i) => grafica.append(
    svg('circle', { className: visibles ? 'grafica__punto' : 'grafica__punto grafica__punto--oculto', cx: x(i), cy: y(p.views), r: visibles ? 3.5 : 7 }, svg('title', {}, titulo(p)))));
  return grafica;
}

// Dona: una porción por sitio. Cada porción es un círculo con trazo parcial (stroke-dasharray).
export function dona(rebanadas, centroGrande, centroChico) {
  const total = rebanadas.reduce((s, r) => s + r.valor, 0);
  const radio = 38, circunferencia = 2 * Math.PI * radio;
  const grafica = svg('svg', { className: 'dona', viewBox: '0 0 100 100', role: 'img', 'aria-label': `${centroChico}: ${centroGrande}` },
    svg('circle', { className: 'dona__fondo', cx: 50, cy: 50, r: radio, fill: 'none', 'stroke-width': 14 }));
  let acumulado = 0;
  if (total > 0) {
    for (const r of rebanadas.filter((x) => x.valor > 0)) {
      const largo = (r.valor / total) * circunferencia;
      grafica.append(svg('circle', {
        cx: 50, cy: 50, r: radio, fill: 'none', stroke: colorSeguro(r.color), 'stroke-width': 14,
        'stroke-dasharray': `${largo.toFixed(2)} ${(circunferencia - largo).toFixed(2)}`,
        'stroke-dashoffset': (-acumulado).toFixed(2), transform: 'rotate(-90 50 50)',
      }, svg('title', {}, r.titulo)));
      acumulado += largo;
    }
  }
  grafica.append(
    svg('text', { className: 'dona__numero', x: 50, y: 52, 'text-anchor': 'middle' }, centroGrande),
    svg('text', { className: 'dona__etiqueta', x: 50, y: 63, 'text-anchor': 'middle' }, centroChico));
  return grafica;
}
