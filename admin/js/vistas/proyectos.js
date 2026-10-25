// Listado de proyectos (endpoint 3) y sus acciones: publicar (6), archivar (7) y eliminar (8).
import { api } from '../api.js';
import { pendiente } from '../estado.js';
import { avisar, cargando, confirmar, dialogo, el, errorDeCarga, ESTADOS, formatearFecha, formatearFechaHora, insignia, mensajeDeError, traducirIssue } from '../ui.js';

const FILTROS = ['TODOS', 'BORRADOR', 'PUBLICADO', 'ARCHIVADO'];

export async function montar(contenedor) {
  const estado = { proyectos: [], filtro: 'TODOS', texto: '' };

  const cuerpo = el('div', { class: 'vista' });
  contenedor.replaceChildren(cuerpo);

  async function cargar() {
    cuerpo.replaceChildren(cargando('Cargando proyectos…'));
    try {
      estado.proyectos = await api.listarTodo('/api/v1/projects');
    } catch (error) {
      cuerpo.replaceChildren(errorDeCarga(error, cargar));
      return;
    }
    pintar();
  }

  function visibles() {
    const texto = estado.texto.trim().toLowerCase();
    return estado.proyectos.filter((p) => (estado.filtro === 'TODOS' || p.status === estado.filtro)
      && (!texto || p.title.toLowerCase().includes(texto) || p.slug.includes(texto)));
  }

  function cuenta(filtro) {
    return filtro === 'TODOS' ? estado.proyectos.length : estado.proyectos.filter((p) => p.status === filtro).length;
  }

  // Si falta algo para publicar, se muestra qué y se ofrece abrir el editor.
  function explicarContrato(error, proyecto) {
    const lista = el('ul', { class: 'lista-simple' }, error.details.map((d) => el('li', {}, traducirIssue(d.issue), ` (${nombreCampo(d.field)})`)));
    const cuerpoDialogo = el('div', {},
      el('p', {}, 'Para publicar, el proyecto necesita:'), lista,
      el('div', { class: 'dialogo__acciones' },
        el('a', { class: 'boton boton--primario', href: `#/proyectos/${proyecto.project_id}`, onclick: () => d.cerrar() }, 'Abrir el editor')));
    const d = dialogo({ titulo: 'Falta información para publicar', cuerpo: cuerpoDialogo, ancho: 'chico' });
  }

  async function publicar(proyecto, boton) {
    const seguro = await confirmar({
      titulo: `¿Publicar "${proyecto.title}"?`,
      texto: 'Pasará a estar publicado en el CMS. Aparecerá en el blog la próxima vez que lo generes y lo subas.',
      aceptar: 'Publicar',
    });
    if (!seguro) return;
    boton.disabled = true;
    try {
      await api.accion(`/api/v1/projects/${proyecto.project_id}/publish`);
      avisar(`Publicado: ${proyecto.title}`);
      pendiente.marcar();
    } catch (error) {
      if (error.code === 'PUBLISH_CONTRACT_INCOMPLETE') explicarContrato(error, proyecto);
      else avisar(mensajeDeError(error), 'error');
    }
    await cargar();
  }

  async function archivar(proyecto, boton) {
    const seguro = await confirmar({
      titulo: `¿Archivar "${proyecto.title}"?`,
      texto: 'Archivar es definitivo: ya no se podrá editar ni volver a publicar, su slug queda reservado y dejará de aparecer en el blog.',
      aceptar: 'Archivar', peligro: true,
    });
    if (!seguro) return;
    boton.disabled = true;
    try {
      await api.accion(`/api/v1/projects/${proyecto.project_id}/archive`);
      avisar(`Archivado: ${proyecto.title}`);
      pendiente.marcar();
    } catch (error) {
      avisar(mensajeDeError(error), 'error');
    }
    await cargar();
  }

  async function eliminar(proyecto, boton) {
    const seguro = await confirmar({
      titulo: `¿Eliminar el borrador "${proyecto.title}"?`,
      texto: 'Se borra por completo y no se puede recuperar.',
      aceptar: 'Eliminar', peligro: true,
    });
    if (!seguro) return;
    boton.disabled = true;
    try {
      await api.eliminar(`/api/v1/projects/${proyecto.project_id}`);
      avisar(`Eliminado: ${proyecto.title}`);
    } catch (error) {
      avisar(mensajeDeError(error), 'error');
    }
    await cargar();
  }

  function fila(proyecto) {
    const accion = (clave, texto, manejador, clase = '') =>
      el('button', { type: 'button', class: `boton boton--chico ${clase}`, dataset: { accion: clave }, onclick: (e) => manejador(proyecto, e.currentTarget) }, texto);
    const acciones = [];
    if (proyecto.status === 'BORRADOR') {
      acciones.push(el('a', { class: 'boton boton--chico', href: `#/proyectos/${proyecto.project_id}`, dataset: { accion: 'editar' } }, 'Editar'));
      acciones.push(accion('publicar', 'Publicar', publicar, 'boton--primario'));
      acciones.push(accion('eliminar', 'Eliminar', eliminar, 'boton--peligro-suave'));
    } else if (proyecto.status === 'PUBLICADO') {
      acciones.push(el('a', { class: 'boton boton--chico', href: `#/proyectos/${proyecto.project_id}`, dataset: { accion: 'editar' } }, 'Editar'));
      acciones.push(accion('archivar', 'Archivar', archivar, 'boton--peligro-suave'));
    } else {
      acciones.push(el('a', { class: 'boton boton--chico', href: `#/proyectos/${proyecto.project_id}`, dataset: { accion: 'editar' } }, 'Ver'));
    }
    return el('li', { class: 'fila', dataset: { id: proyecto.project_id, estado: proyecto.status, slug: proyecto.slug } },
      el('div', { class: 'fila__principal' },
        el('a', { class: 'fila__titulo', href: `#/proyectos/${proyecto.project_id}` }, proyecto.title),
        el('span', { class: 'fila__slug' }, proyecto.slug)),
      el('div', { class: 'fila__estado' }, insignia(proyecto.status)),
      el('div', { class: 'fila__dato', 'data-etiqueta': 'Fecha' }, formatearFecha(proyecto.project_date)),
      el('div', { class: 'fila__dato', 'data-etiqueta': 'Actualizado' }, formatearFechaHora(proyecto.updated_at)),
      el('div', { class: 'fila__acciones' }, acciones));
  }

  function pintar() {
    const buscador = el('input', { type: 'search', id: 'buscar-proyecto', class: 'buscador', placeholder: 'Buscar por título o slug…', 'aria-label': 'Buscar proyectos', autocomplete: 'off' });
    buscador.value = estado.texto;
    const lista = el('ul', { class: 'lista', id: 'lista-proyectos' });
    const repintarLista = () => {
      const filas = visibles();
      lista.replaceChildren(...filas.map(fila));
      vacio.hidden = filas.length > 0;
      vacio.textContent = estado.proyectos.length ? 'Ningún proyecto coincide con el filtro.' : 'Todavía no hay proyectos. Crea el primero con «Nuevo proyecto».';
    };
    const vacio = el('p', { class: 'estado-vacio', hidden: true });
    buscador.addEventListener('input', () => { estado.texto = buscador.value; repintarLista(); });

    const chips = el('div', { class: 'chips', role: 'group', 'aria-label': 'Filtrar por estado' }, FILTROS.map((f) => {
      const chip = el('button', { type: 'button', class: 'chip', dataset: { filtro: f }, 'aria-pressed': String(estado.filtro === f),
        onclick: () => { estado.filtro = f; chips.querySelectorAll('.chip').forEach((c) => c.setAttribute('aria-pressed', String(c.dataset.filtro === f))); repintarLista(); } },
      f === 'TODOS' ? 'Todos' : ESTADOS[f], el('span', { class: 'chip__cuenta' }, String(cuenta(f))));
      return chip;
    }));

    cuerpo.replaceChildren(
      el('div', { class: 'vista__cab' },
        el('h1', {}, 'Proyectos'),
        el('a', { class: 'boton boton--primario', id: 'btn-nuevo-proyecto', href: '#/proyectos/nuevo' }, 'Nuevo proyecto')),
      el('div', { class: 'barra-filtros' }, chips, buscador),
      lista, vacio);
    repintarLista();
  }

  await cargar();
  return {};
}

const NOMBRES_CAMPO = { short_description: 'descripción corta', description: 'descripción', project_date: 'fecha', stack_ids: 'lenguajes' };
function nombreCampo(campo) {
  return NOMBRES_CAMPO[campo] ?? campo;
}
