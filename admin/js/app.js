// Arranque de la consola: sesión, menú, rutas y el aviso de cambios que aún no están en el blog.
import { alExpirarSesion, api, sesion } from './api.js';
import { pendiente } from './estado.js';
import { avisar, confirmar, copiarTexto, el } from './ui.js';
import { montarLogin } from './vistas/login.js';
import * as listaProyectos from './vistas/proyectos.js';
import * as editorProyecto from './vistas/proyecto_editor.js';
import * as certificados from './vistas/certificados.js';
import * as catalogo from './vistas/catalogo.js';
import * as perfil from './vistas/perfil.js';
import * as estadisticas from './vistas/estadisticas.js';
import * as sitios from './vistas/sitios.js';

const raiz = document.getElementById('raiz');

const SECCIONES = [
  { clave: 'proyectos', texto: 'Proyectos', hash: '#/proyectos' },
  { clave: 'certificados', texto: 'Certificados', hash: '#/certificados' },
  { clave: 'catalogo', texto: 'Lenguajes y herramientas', hash: '#/catalogo' },
  { clave: 'perfil', texto: 'Perfil', hash: '#/perfil' },
  { clave: 'estadisticas', texto: 'Estadísticas', hash: '#/estadisticas' },
  { clave: 'sitios', texto: 'Sitios', hash: '#/sitios' },
];

const RUTAS = [
  { patron: /^#\/proyectos\/nuevo$/, seccion: 'proyectos', vista: editorProyecto, parametros: () => ({ id: null }) },
  { patron: /^#\/proyectos\/([A-Za-z0-9-]+)$/, seccion: 'proyectos', vista: editorProyecto, parametros: (m) => ({ id: m[1] }) },
  { patron: /^#\/proyectos$/, seccion: 'proyectos', vista: listaProyectos, parametros: () => ({}) },
  { patron: /^#\/certificados$/, seccion: 'certificados', vista: certificados, parametros: () => ({}) },
  { patron: /^#\/catalogo$/, seccion: 'catalogo', vista: catalogo, parametros: () => ({}) },
  { patron: /^#\/perfil$/, seccion: 'perfil', vista: perfil, parametros: () => ({}) },
  { patron: /^#\/estadisticas$/, seccion: 'estadisticas', vista: estadisticas, parametros: () => ({}) },
  { patron: /^#\/sitios$/, seccion: 'sitios', vista: sitios, parametros: () => ({}) },
];

let vistaActual = {};          // lo que la vista mostrada deja: hayCambios() para avisar antes de salir
let hashAnterior = null;
let ignorarCambio = false;
let temporizadorSesion = null;
let numeroNavegacion = 0;

// ------------------------------------------------------------ sesión
function programarVencimiento() {
  clearTimeout(temporizadorSesion);
  const vence = sesion.venceEn();
  if (vence) temporizadorSesion = setTimeout(() => cerrarSesion('Tu sesión expiró. Inicia sesión de nuevo.'), Math.max(0, vence - Date.now() - 1000));
}

function cerrarSesion(mensaje = null) {
  clearTimeout(temporizadorSesion);
  sesion.cerrar();
  pendiente.limpiar();
  vistaActual = {};
  hashAnterior = null;
  montarLogin(raiz, { mensaje, alEntrar: iniciarConsola });
}

alExpirarSesion(() => cerrarSesion('Tu sesión expiró. Inicia sesión de nuevo.'));

// ------------------------------------------------------------ aviso de cambios pendientes
function pintarBanner() {
  const zona = document.getElementById('banner');
  if (!zona) return;
  zona.replaceChildren();
  if (!pendiente.hay()) return;
  const comando = `python generador\\build.py --api ${location.origin}`;
  zona.append(el('section', { class: 'banner', role: 'status' },
    el('div', { class: 'banner__texto' },
      el('strong', {}, 'Hay cambios en el CMS que todavía no están en tu blog.'),
      el('p', {}, 'En la carpeta del blog, con la API encendida, corre esto y luego sube los cambios con Git:'),
      el('pre', { class: 'banner__codigo' }, `${comando}\ngit add .\ngit commit -m "Actualizo el contenido"\ngit push`)),
    el('div', { class: 'banner__acciones' },
      el('button', { type: 'button', class: 'boton boton--chico', id: 'btn-copiar-comando',
        onclick: async () => avisar(await copiarTexto(comando) ? 'Comando copiado.' : 'No se pudo copiar; selecciónalo a mano.', 'info') }, 'Copiar comando'),
      el('button', { type: 'button', class: 'boton boton--chico boton--primario', id: 'btn-ya-subi', onclick: () => pendiente.limpiar() }, 'Ya lo subí'))));
}
pendiente.alCambiar(pintarBanner);

// ------------------------------------------------------------ estructura de la consola
function montarEstructura() {
  const enlaces = SECCIONES.map((s) => el('a', { href: s.hash, dataset: { seccion: s.clave } }, s.texto));
  raiz.replaceChildren(
    el('header', { class: 'cabecera' },
      el('div', { class: 'cabecera__interior' },
        el('a', { class: 'marca', href: '#/proyectos' }, 'SEGOPE', el('span', { class: 'marca__sub' }, '.dev'), el('span', { class: 'marca__consola' }, ' / consola')),
        el('nav', { class: 'menu', 'aria-label': 'Secciones' }, enlaces),
        el('div', { class: 'cabecera__acciones' },
          el('a', { class: 'enlace-sutil', href: '/docs', target: '_blank', rel: 'noopener' }, 'API'),
          el('button', { type: 'button', class: 'boton boton--sutil boton--chico', id: 'btn-salir', onclick: () => cerrarSesion('Sesión cerrada.') }, 'Salir')))),
    el('div', { id: 'banner' }),
    el('main', { id: 'principal', class: 'principal', tabindex: '-1' }));
  pintarBanner();
}

// ------------------------------------------------------------ navegación
async function navegar() {
  const hash = location.hash || '#/proyectos';
  const ruta = RUTAS.find((r) => r.patron.test(hash));
  if (!ruta) { location.hash = '#/proyectos'; return; }

  document.querySelectorAll('.menu a').forEach((a) => {
    if (a.dataset.seccion === ruta.seccion) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  const principal = document.getElementById('principal');
  const mia = ++numeroNavegacion;
  const vista = {};
  vistaActual = vista;
  hashAnterior = hash;
  // Cada navegación tiene su propio contenedor. Si una vista lenta termina de cargar cuando ya navegaste a otra,
  // pinta dentro de un contenedor que ya no está en la página y no pisa la pantalla nueva.
  const contenedor = el('div', { class: 'contenedor-vista' });
  principal.replaceChildren(contenedor);
  window.scrollTo(0, 0);
  try {
    await ruta.vista.montar(contenedor, ruta.parametros(ruta.patron.exec(hash)), vista);
  } catch (error) {
    if (mia === numeroNavegacion) avisar(`Error inesperado: ${error.message}`, 'error');
    console.error(error);
  }
}

window.addEventListener('hashchange', async () => {
  if (ignorarCambio) { ignorarCambio = false; return; }
  if (vistaActual.hayCambios?.()) {
    const salir = await confirmar({ titulo: '¿Salir sin guardar?', texto: 'Tienes cambios sin guardar en este formulario. Si sales, se pierden.', aceptar: 'Salir sin guardar', cancelar: 'Seguir editando', peligro: true });
    if (!salir) { ignorarCambio = true; location.hash = hashAnterior; return; }
  }
  navegar();
});

window.addEventListener('beforeunload', (evento) => {
  if (vistaActual.hayCambios?.()) { evento.preventDefault(); evento.returnValue = ''; }
});

// ------------------------------------------------------------ arranque
function iniciarConsola() {
  programarVencimiento();
  montarEstructura();
  if (!location.hash || location.hash === '#/') location.hash = '#/proyectos';
  navegar();
}

// Al abrir la consola con una sesión guardada se comprueba con la API que el token todavía sirva
// (por ejemplo, deja de servir si se cambió la clave secreta del servidor).
async function arrancar() {
  if (!sesion.vigente()) { sesion.cerrar(); montarLogin(raiz, { alEntrar: iniciarConsola }); return; }
  try {
    await api.obtener('/api/v1/projects', { limit: 1 });
  } catch (error) {
    if (error.status === 401) return;            // la API rechazó el token: ya se mostró el inicio de sesión
  }
  iniciarConsola();
}
arrancar();
