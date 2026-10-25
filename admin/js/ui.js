// Componentes compartidos de la consola. Todo el HTML se construye con el(): el texto siempre entra como texto
// (nunca como HTML), así que nada de lo que venga de la base de datos puede inyectar código en la página.
import { api } from './api.js';

// ------------------------------------------------------------ DOM seguro
export function el(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(atributos ?? {})) {
    if (valor === undefined || valor === null || valor === false) continue;
    if (clave === 'class') nodo.className = valor;
    else if (clave === 'dataset') Object.assign(nodo.dataset, valor);
    else if (clave.startsWith('on') && typeof valor === 'function') nodo.addEventListener(clave.slice(2), valor);
    else if (valor === true) nodo.setAttribute(clave, '');
    else nodo.setAttribute(clave, valor);
  }
  nodo.append(...hijos.flat().filter((h) => h !== null && h !== undefined && h !== false));
  return nodo;
}

// ------------------------------------------------------------ textos y formatos
export const ESTADOS = { BORRADOR: 'Borrador', PUBLICADO: 'Publicado', ARCHIVADO: 'Archivado' };
export const CATEGORIAS = {
  LENGUAJE: 'Lenguaje', FRAMEWORK: 'Framework o librería', BASE_DE_DATOS: 'Base de datos', NUBE: 'Nube', HERRAMIENTA: 'Herramienta',
};
export const ORDEN_CATEGORIAS = ['LENGUAJE', 'FRAMEWORK', 'BASE_DE_DATOS', 'NUBE', 'HERRAMIENTA'];

export function insignia(estado) {
  return el('span', { class: `insignia insignia--${estado.toLowerCase()}` }, ESTADOS[estado] ?? estado);
}

export function formatearFecha(iso) {
  if (!iso) return '—';
  const [anio, mes, dia] = iso.slice(0, 10).split('-');
  return `${dia}/${mes}/${anio}`;
}

export function formatearFechaHora(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatearBytes(bytes) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function hoy() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// "Math & English Quest" -> "math-english-quest"
export function slugificar(texto) {
  return texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80).replace(/-+$/, '');
}

export async function copiarTexto(texto) {
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch {
    const area = el('textarea', { class: 'fuera-de-pantalla', 'aria-hidden': 'true' });
    area.value = texto;
    document.body.append(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    return ok;
  }
}

// ------------------------------------------------------------ avisos
export function avisar(texto, tipo = 'ok') {
  const zona = document.getElementById('avisos');
  const nodo = el('p', { class: `aviso aviso--${tipo}` }, texto);
  zona.append(nodo);
  const duracion = tipo === 'error' ? 7000 : 4000;
  setTimeout(() => nodo.classList.add('aviso--sale'), duracion);
  setTimeout(() => nodo.remove(), duracion + 400);
}

export const cargando = (texto = 'Cargando…') => el('p', { class: 'estado-carga', role: 'status' }, texto);

export function errorDeCarga(error, reintentar) {
  return el('div', { class: 'estado-error', role: 'alert' },
    el('p', {}, mensajeDeError(error)),
    reintentar ? el('button', { type: 'button', class: 'boton', onclick: reintentar }, 'Reintentar') : null);
}

// ------------------------------------------------------------ diálogos
let contadorDialogos = 0;

// Ventana modal para formularios. Se cierra con la X o con Esc (no al tocar fuera, para no perder lo escrito).
export function dialogo({ titulo, cuerpo, ancho = 'normal', alCerrar }) {
  const id = `dialogo-${++contadorDialogos}`;
  const d = el('dialog', { class: `dialogo dialogo--${ancho}`, 'aria-labelledby': id });
  d.append(
    el('header', { class: 'dialogo__cab' },
      el('h2', { id }, titulo),
      el('button', { type: 'button', class: 'icono-cerrar', 'aria-label': 'Cerrar', onclick: () => d.close() }, '×')),
    el('div', { class: 'dialogo__cuerpo' }, cuerpo));
  d.addEventListener('close', () => { d.remove(); if (alCerrar) alCerrar(); });
  document.body.append(d);
  d.showModal();
  return { elemento: d, cerrar: () => d.close() };
}

// Pregunta de sí/no. Devuelve una promesa con true o false.
export function confirmar({ titulo, texto, aceptar = 'Aceptar', cancelar = 'Cancelar', peligro = false }) {
  return new Promise((resolver) => {
    const d = el('dialog', { class: 'dialogo dialogo--chico', 'aria-labelledby': 'confirmar-titulo' });
    const no = el('button', { type: 'button', class: 'boton', 'data-respuesta': 'no', onclick: () => d.close('no') }, cancelar);
    const si = el('button', { type: 'button', class: `boton ${peligro ? 'boton--peligro' : 'boton--primario'}`, 'data-respuesta': 'si', onclick: () => d.close('si') }, aceptar);
    d.append(el('div', { class: 'dialogo__cuerpo' },
      el('h2', { id: 'confirmar-titulo' }, titulo),
      el('div', { class: 'dialogo__texto' }, texto),
      el('div', { class: 'dialogo__acciones' }, no, si)));
    d.addEventListener('close', () => { const respuesta = d.returnValue === 'si'; d.remove(); resolver(respuesta); });
    document.body.append(d);
    d.showModal();
    (peligro ? no : si).focus();
  });
}

// ------------------------------------------------------------ campos de formulario
export function campo({ nombre, etiqueta, control, paraId, ayuda, requerido = false, contador = null }) {
  const id = paraId ?? control.id;
  const cuenta = contador ? el('span', { class: 'campo__contador' }) : null;
  if (cuenta) {
    const pintar = () => { cuenta.textContent = `${control.value.length}/${contador.max}`; };
    control.addEventListener('input', pintar);
    pintar();
  }
  return el('div', { class: 'campo', dataset: { campo: nombre } },
    el('label', { class: 'campo__etiqueta', for: id }, etiqueta, requerido ? el('span', { class: 'campo__req', 'aria-hidden': 'true' }, ' *') : null),
    control,
    ayuda || cuenta ? el('div', { class: 'campo__pie' }, ayuda ? el('p', { class: 'campo__ayuda' }, ayuda) : el('span'), cuenta) : null,
    el('p', { class: 'campo__error', role: 'alert', hidden: true }));
}

export function entrada({ id, nombre, tipo = 'text', valor = '', ...extra }) {
  const nodo = el('input', { id, name: nombre, type: tipo, autocomplete: 'off', ...extra });
  nodo.value = valor ?? '';
  return nodo;
}

export function area({ id, nombre, valor = '', filas = 4, ...extra }) {
  const nodo = el('textarea', { id, name: nombre, rows: String(filas), ...extra });
  nodo.value = valor ?? '';
  return nodo;
}

export function selector({ id, nombre, opciones, valor }) {
  const nodo = el('select', { id, name: nombre }, opciones.map((o) => el('option', { value: o.valor }, o.texto)));
  nodo.value = valor ?? opciones[0].valor;
  return nodo;
}

export function interruptor({ id, nombre, etiqueta, valor = false, deshabilitado = false }) {
  const casilla = el('input', { id, name: nombre, type: 'checkbox', role: 'switch', disabled: deshabilitado });
  casilla.checked = Boolean(valor);
  return { casilla, elemento: el('label', { class: 'interruptor', for: id }, casilla, el('span', { class: 'interruptor__pista', 'aria-hidden': 'true' }), el('span', {}, etiqueta)) };
}

// ------------------------------------------------------------ errores de la API, en español y junto a su campo
const MENSAJES = {
  VALIDATION_ERROR: 'Revisa los campos marcados.',
  PUBLISH_CONTRACT_INCOMPLETE: 'Falta información para publicar el proyecto.',
  SLUG_ALREADY_EXISTS: 'Ese slug ya lo usa otro proyecto.',
  SLUG_IMMUTABLE: 'El slug ya no se puede cambiar.',
  STACK_ID_NOT_FOUND: 'Alguno de los lenguajes o herramientas elegidos ya no existe.',
  CERTIFICATE_ALREADY_EXISTS: 'Ya existe un certificado con ese título, institución y fecha.',
  FILE_URL_NOT_ALLOWED: 'Alguna URL de archivo no viene del servicio de archivos.',
  STACK_NAME_ALREADY_EXISTS: 'Ya existe un elemento con ese nombre.',
  STACK_IN_USE: 'No se puede eliminar: hay proyectos que lo usan.',
  PROJECT_ARCHIVED: 'Un proyecto archivado ya no se puede modificar.',
  PROJECT_ALREADY_PUBLISHED: 'El proyecto ya estaba publicado.',
  PROJECT_NOT_PUBLISHED: 'Solo se puede archivar un proyecto publicado.',
  PROJECT_NOT_DELETABLE: 'Solo se pueden eliminar proyectos en borrador.',
  FILE_TOO_LARGE: 'El archivo es demasiado grande.',
  UNSUPPORTED_MEDIA_TYPE: 'Solo se aceptan PDF, JPEG, PNG o WebP.',
  FILE_PURPOSE_MISMATCH: 'El archivo no coincide con lo que se esperaba (PDF o imagen).',
  IDEMPOTENCY_KEY_REUSED: 'La operación se repitió con otros datos. Intenta de nuevo.',
  NETWORK_ERROR: 'No se pudo conectar con la API. Revisa que esté encendida.',
};

export function mensajeDeError(error) {
  return MENSAJES[error.code] ?? error.message;
}

const TRADUCCIONES = [
  [/String should have at least (\d+) characters?/, (m) => `Debe tener al menos ${m[1]} caracteres.`],
  [/String should have at most (\d+) characters?/, (m) => `Debe tener máximo ${m[1]} caracteres.`],
  [/String should match pattern/, () => 'No tiene un formato válido.'],
  [/Field required/, () => 'Campo obligatorio.'],
  [/Input should be a valid date/, () => 'Fecha no válida.'],
  [/Input should be greater than or equal to (\d+)/, (m) => `Debe ser ${m[1]} o más.`],
  [/Input should be a valid (integer|number)/, () => 'Debe ser un número.'],
  [/Input should be a valid boolean/, () => 'Valor no válido.'],
  [/Value error, (.*)/, (m) => m[1]],
];

export function traducirIssue(issue) {
  for (const [patron, convertir] of TRADUCCIONES) {
    const m = issue.match(patron);
    if (m) return convertir(m);
  }
  return issue;
}

export function limpiarErrores(raiz) {
  raiz.querySelectorAll('.campo--error').forEach((c) => {
    c.classList.remove('campo--error');
    const p = c.querySelector('.campo__error');
    p.hidden = true;
    p.textContent = '';
  });
  raiz.querySelectorAll('[aria-invalid]').forEach((n) => n.removeAttribute('aria-invalid'));
  raiz.querySelectorAll('.resumen-errores').forEach((r) => r.remove());
}

// Pone cada mensaje junto a su campo (details[].field) y un resumen arriba del formulario.
export function mostrarErrores(raiz, error) {
  limpiarErrores(raiz);
  const detalles = error.details?.length ? error.details : [];
  const sueltos = [];
  let primero = null;
  for (const detalle of detalles) {
    const nombre = (detalle.field || '').split('.')[0];
    const campoNodo = nombre ? raiz.querySelector(`.campo[data-campo="${CSS.escape(nombre)}"]`) : null;
    const texto = traducirIssue(detalle.issue);
    if (!campoNodo) { sueltos.push(texto); continue; }
    const p = campoNodo.querySelector('.campo__error');
    p.textContent = p.textContent ? `${p.textContent} ${texto}` : texto;
    p.hidden = false;
    campoNodo.classList.add('campo--error');
    campoNodo.querySelectorAll('input, textarea, select').forEach((n) => n.setAttribute('aria-invalid', 'true'));
    primero = primero ?? campoNodo;
  }
  const resumen = el('div', { class: 'resumen-errores', role: 'alert', tabindex: '-1' },
    el('strong', {}, mensajeDeError(error)),
    sueltos.length ? el('ul', {}, sueltos.map((t) => el('li', {}, t))) : null);
  raiz.prepend(resumen);
  const destino = primero?.querySelector('input, textarea, select') ?? resumen;
  destino.focus({ preventScroll: true });
  (primero ?? resumen).scrollIntoView({ block: 'center', behavior: 'smooth' });
}

// ------------------------------------------------------------ selector de archivos (PDF o imagen)
const LIMITES = { pdf: 5 * 1024 * 1024, imagen: 2 * 1024 * 1024 };
let contadorArchivos = 0;

function imagenConRespaldo(url, clase) {
  const imagen = el('img', { src: url, alt: '', loading: 'lazy', class: clase });
  imagen.addEventListener('error', () => imagen.replaceWith(el('span', { class: 'archivo__vacio' }, 'No se pudo cargar la vista previa')));
  return imagen;
}

// Elige un archivo, lo sube con POST /api/v1/files y guarda la URL que devuelve la API.
export function selectorArchivo({ nombre, etiqueta, proposito, accept, valor = null, ayuda, requerido = false, alCambiar }) {
  const id = `archivo-${nombre}-${++contadorArchivos}`;
  const esPdf = accept.includes('pdf');
  let url = valor ?? null;
  let subiendo = false;

  const vista = el('div', { class: 'archivo__vista' });
  const estado = el('p', { class: 'archivo__estado', role: 'status' });
  const entradaArchivo = el('input', { type: 'file', id, accept, class: 'archivo__entrada' });
  const urlManual = el('input', { type: 'text', id: `${id}-url`, class: 'archivo__url', placeholder: 'https://…', 'aria-label': `URL de ${etiqueta}`, autocomplete: 'off' });

  function pintar() {
    vista.replaceChildren();
    if (!url) vista.append(el('span', { class: 'archivo__vacio' }, 'Sin archivo'));
    else if (esPdf) vista.append(el('a', { href: url, target: '_blank', rel: 'noopener noreferrer', class: 'archivo__enlace' }, 'Ver PDF actual'));
    else vista.append(imagenConRespaldo(url, 'archivo__img'));
    urlManual.value = url ?? '';
  }

  entradaArchivo.addEventListener('change', async () => {
    const archivo = entradaArchivo.files[0];
    if (!archivo) return;
    const limite = esPdf ? LIMITES.pdf : LIMITES.imagen;
    if (archivo.size > limite) {
      estado.textContent = `Pesa ${formatearBytes(archivo.size)}; el máximo es ${formatearBytes(limite)}.`;
      estado.classList.add('archivo__estado--error');
      entradaArchivo.value = '';
      return;
    }
    subiendo = true;
    estado.classList.remove('archivo__estado--error');
    estado.textContent = 'Subiendo…';
    try {
      const r = await api.subirArchivo(archivo, proposito);
      url = r.datos.url;
      estado.textContent = `Subido (${formatearBytes(r.datos.size_bytes)}).`;
      pintar();
      if (alCambiar) alCambiar();
    } catch (error) {
      estado.textContent = mensajeDeError(error);
      estado.classList.add('archivo__estado--error');
    } finally {
      subiendo = false;
      entradaArchivo.value = '';
    }
  });
  urlManual.addEventListener('change', () => {
    url = urlManual.value.trim() || null;
    pintar();
    if (alCambiar) alCambiar();
  });

  pintar();
  const control = el('div', { class: 'archivo' },
    vista, entradaArchivo, estado,
    el('details', { class: 'archivo__avanzado' }, el('summary', {}, 'Pegar una URL en lugar de subir'), urlManual));
  return {
    elemento: campo({ nombre, etiqueta, control, paraId: id, ayuda, requerido }),
    url: () => url,
    subiendo: () => subiendo,
  };
}
