// Lenguajes y herramientas: listado público (16) y administración: crear (15), actualizar (17) y eliminar (18).
import { api } from '../api.js';
import { pendiente } from '../estado.js';
import {
  avisar, campo, cargando, CATEGORIAS, confirmar, dialogo, el, entrada, errorDeCarga, interruptor, limpiarErrores,
  mensajeDeError, mostrarErrores, ORDEN_CATEGORIAS, selector, selectorArchivo,
} from '../ui.js';

export async function montar(contenedor) {
  const cuerpo = el('div', { class: 'vista' });
  contenedor.replaceChildren(cuerpo);
  let elementos = [];
  let filtro = 'TODAS';

  async function cargar() {
    cuerpo.replaceChildren(cargando('Cargando lenguajes y herramientas…'));
    try {
      elementos = await api.listarTodo('/api/v1/public/tech-stack');
    } catch (error) {
      cuerpo.replaceChildren(errorDeCarga(error, cargar));
      return;
    }
    pintar();
  }

  // PUT reemplaza todo el elemento, así que siempre se envían todos sus datos (display_order incluido, para que no cambie de lugar).
  const cuerpoPut = (e, cambios = {}) => ({
    name: e.name, category: e.category, logo_url: e.logo_url, show_in_profile: e.show_in_profile, display_order: e.display_order, ...cambios,
  });

  function formulario(elemento) {
    const esNuevo = !elemento;
    const nombre = entrada({ id: 't-name', nombre: 'name', valor: elemento?.name, maxlength: '40' });
    const categoria = selector({ id: 't-category', nombre: 'category', opciones: ORDEN_CATEGORIAS.map((c) => ({ valor: c, texto: CATEGORIAS[c] })), valor: elemento?.category ?? 'LENGUAJE' });
    const orden = entrada({ id: 't-display_order', nombre: 'display_order', tipo: 'number', valor: elemento?.display_order ?? '', min: '1', step: '1', inputmode: 'numeric' });
    const logo = selectorArchivo({ nombre: 'logo_url', etiqueta: 'Logo (opcional)', proposito: 'STACK_LOGO', accept: 'image/png,image/jpeg,image/webp', valor: elemento?.logo_url, ayuda: 'JPG, PNG o WebP, hasta 2 MB.' });
    const visible = interruptor({ id: 't-show_in_profile', nombre: 'show_in_profile', etiqueta: 'Mostrar en «Lenguajes y herramientas» del blog', valor: elemento?.show_in_profile });
    const guardar = el('button', { type: 'submit', class: 'boton boton--primario', id: 'btn-guardar-elemento' }, esNuevo ? 'Crear' : 'Guardar cambios');
    const f = el('form', { class: 'formulario', novalidate: true },
      campo({ nombre: 'name', etiqueta: 'Nombre', control: nombre, requerido: true }),
      el('div', { class: 'campos-dos' },
        campo({ nombre: 'category', etiqueta: 'Categoría', control: categoria, requerido: true }),
        campo({ nombre: 'display_order', etiqueta: 'Posición', control: orden, ayuda: esNuevo ? 'Vacío = al final de la lista.' : 'Si la dejas vacía, pasa al final.' })),
      logo.elemento,
      el('div', { class: 'campo' }, visible.elemento),
      el('div', { class: 'dialogo__acciones' }, el('button', { type: 'button', class: 'boton boton--sutil', onclick: () => ventana.cerrar() }, 'Cancelar'), guardar));

    f.addEventListener('submit', async (evento) => {
      evento.preventDefault();
      limpiarErrores(f);
      const datos = {
        name: nombre.value.trim(), category: categoria.value, logo_url: logo.url(),
        show_in_profile: visible.casilla.checked, display_order: orden.value === '' ? null : Number(orden.value),
      };
      const problemas = [];
      if (!datos.name) problemas.push({ field: 'name', issue: 'El nombre es obligatorio.' });
      if (datos.display_order !== null && (!Number.isInteger(datos.display_order) || datos.display_order < 1)) problemas.push({ field: 'display_order', issue: 'La posición es un número entero desde 1.' });
      if (logo.subiendo()) problemas.push({ field: '', issue: 'Espera a que termine la subida del logo.' });
      if (problemas.length) { mostrarErrores(f, { code: 'VALIDATION_ERROR', details: problemas }); return; }

      guardar.disabled = true;
      try {
        if (esNuevo) await api.crear('/api/v1/tech-stack', datos);
        else await api.reemplazar(`/api/v1/tech-stack/${elemento.stack_id}`, datos);
        if (!esNuevo || datos.show_in_profile) pendiente.marcar();
        avisar(esNuevo ? 'Elemento creado.' : 'Elemento actualizado.');
        ventana.cerrar();
        await cargar();
      } catch (error) {
        mostrarErrores(f, error);
        guardar.disabled = false;
      }
    });
    const ventana = dialogo({ titulo: esNuevo ? 'Nuevo lenguaje o herramienta' : 'Editar elemento', cuerpo: f });
    nombre.focus();
  }

  async function cambiarVisibilidad(elemento, casilla) {
    casilla.disabled = true;
    try {
      await api.reemplazar(`/api/v1/tech-stack/${elemento.stack_id}`, cuerpoPut(elemento, { show_in_profile: casilla.checked }));
      pendiente.marcar();
      avisar(casilla.checked ? `${elemento.name} se mostrará en el blog.` : `${elemento.name} se ocultará del blog.`);
    } catch (error) {
      avisar(mensajeDeError(error), 'error');
    }
    await cargar();
  }

  async function eliminar(elemento) {
    const seguro = await confirmar({ titulo: `¿Eliminar "${elemento.name}"?`, texto: 'Se borra del catálogo. Si algún proyecto lo usa, no se podrá eliminar.', aceptar: 'Eliminar', peligro: true });
    if (!seguro) return;
    try {
      await api.eliminar(`/api/v1/tech-stack/${elemento.stack_id}`);
      if (elemento.show_in_profile) pendiente.marcar();
      avisar('Elemento eliminado.');
    } catch (error) {
      if (error.code === 'STACK_IN_USE') {
        const proyectos = (error.details[0]?.issue ?? '').replace(/^Lo usan:\s*/, '');
        dialogo({ titulo: 'No se puede eliminar', ancho: 'chico', cuerpo: el('div', {},
          el('p', {}, `«${elemento.name}» lo usan estos proyectos: `, el('strong', {}, proyectos), '.'),
          el('p', { class: 'dato' }, 'Quítalo de esos proyectos y vuelve a intentarlo.')) });
      } else {
        avisar(mensajeDeError(error), 'error');
      }
    }
    await cargar();
  }

  function fila(e) {
    const logo = e.logo_url ? el('img', { src: e.logo_url, alt: '', class: 'fila-cat__logo', loading: 'lazy' }) : el('span', { class: 'fila-cat__logo fila-cat__logo--vacio', 'aria-hidden': 'true' });
    if (e.logo_url) logo.addEventListener('error', () => logo.replaceWith(el('span', { class: 'fila-cat__logo fila-cat__logo--vacio', 'aria-hidden': 'true' })));
    const visible = interruptor({ id: `vis-${e.stack_id}`, nombre: 'visible', etiqueta: 'En el blog', valor: e.show_in_profile });
    visible.casilla.addEventListener('change', () => cambiarVisibilidad(e, visible.casilla));
    return el('li', { class: 'fila fila--cat', dataset: { id: e.stack_id, nombre: e.name } },
      el('span', { class: 'fila-cat__orden mono', title: 'Posición' }, String(e.display_order)),
      logo,
      el('div', { class: 'fila__principal' }, el('span', { class: 'fila__titulo fila__titulo--texto' }, e.name), el('span', { class: 'fila__slug' }, CATEGORIAS[e.category])),
      el('div', { class: 'fila__visible' }, visible.elemento),
      el('div', { class: 'fila__acciones' },
        el('button', { type: 'button', class: 'boton boton--chico', dataset: { accion: 'editar' }, onclick: () => formulario(e) }, 'Editar'),
        el('button', { type: 'button', class: 'boton boton--chico boton--peligro-suave', dataset: { accion: 'eliminar' }, onclick: () => eliminar(e) }, 'Eliminar')));
  }

  function pintar() {
    const lista = el('ul', { class: 'lista', id: 'lista-catalogo' });
    const repintar = () => lista.replaceChildren(...elementos.filter((e) => filtro === 'TODAS' || e.category === filtro).map(fila));
    const chips = el('div', { class: 'chips', role: 'group', 'aria-label': 'Filtrar por categoría' },
      ['TODAS', ...ORDEN_CATEGORIAS].map((c) => el('button', { type: 'button', class: 'chip', dataset: { filtro: c }, 'aria-pressed': String(filtro === c),
        onclick: () => { filtro = c; chips.querySelectorAll('.chip').forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.filtro === c))); repintar(); } },
      c === 'TODAS' ? 'Todas' : CATEGORIAS[c], el('span', { class: 'chip__cuenta' }, String(c === 'TODAS' ? elementos.length : elementos.filter((e) => e.category === c).length)))));
    cuerpo.replaceChildren(
      el('div', { class: 'vista__cab' },
        el('h1', {}, 'Lenguajes y herramientas'),
        el('button', { type: 'button', class: 'boton boton--primario', id: 'btn-nuevo-elemento', onclick: () => formulario(null) }, 'Nuevo elemento')),
      el('p', { class: 'nota' }, 'Es el catálogo que usan los proyectos. Los marcados «En el blog» aparecen en la sección Lenguajes y herramientas de Acerca y en «Stack actual».'),
      el('div', { class: 'barra-filtros' }, chips),
      lista);
    repintar();
  }

  await cargar();
  return {};
}
