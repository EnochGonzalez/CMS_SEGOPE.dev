// Editor de un proyecto: crear (2), leer (4), actualizar (5), publicar (6), archivar (7) y eliminar (8).
import { api } from '../api.js';
import { cambioEnElBlog } from '../estado.js';
import {
  area, avisar, campo, cargando, CATEGORIAS, confirmar, el, entrada, errorDeCarga, formatearFechaHora, insignia,
  interruptor, limpiarErrores, mensajeDeError, mostrarErrores, ORDEN_CATEGORIAS, slugificar,
} from '../ui.js';

const PATRON_SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const PATRON_HTTPS = /^https:\/\/\S+$/;

export async function montar(contenedor, { id }, vista = {}) {
  contenedor.replaceChildren(cargando(id ? 'Cargando proyecto…' : 'Preparando formulario…'));
  let catalogo;
  let proyecto = null;
  try {
    [catalogo, proyecto] = await Promise.all([
      api.listarTodo('/api/v1/public/tech-stack'),
      id ? api.obtener(`/api/v1/projects/${id}`).then((r) => r.datos) : null,
    ]);
  } catch (error) {
    contenedor.replaceChildren(errorDeCarga(error, () => montar(contenedor, { id }, vista)));
    return vista;
  }
  construir(contenedor, catalogo, proyecto, vista);
  return vista;
}

// ------------------------------------------------------------ etiquetas (hasta 5, de 2 a 30 caracteres, sin repetir)
function controlEtiquetas(iniciales, deshabilitado, alCambiar) {
  const etiquetas = [...iniciales];
  const lista = el('ul', { class: 'etiquetas__lista', id: 'p-tags-lista' });
  const aviso = el('p', { class: 'campo__ayuda etiquetas__aviso', role: 'status' });
  const caja = el('input', { id: 'p-tags', type: 'text', maxlength: '30', autocomplete: 'off', class: 'etiquetas__entrada', disabled: deshabilitado, 'aria-label': 'Nueva etiqueta' });

  function pintar() {
    lista.replaceChildren(...etiquetas.map((texto, i) => el('li', { class: 'etiqueta' },
      el('span', {}, texto),
      deshabilitado ? null : el('button', { type: 'button', class: 'etiqueta__quitar', 'aria-label': `Quitar ${texto}`,
        onclick: () => { etiquetas.splice(i, 1); pintar(); alCambiar(); } }, '×'))));
    caja.disabled = deshabilitado || etiquetas.length >= 5;
    caja.placeholder = etiquetas.length >= 5 ? 'Máximo 5 etiquetas' : 'Escribe y pulsa Enter';
  }

  function agregar() {
    const texto = caja.value.trim().replace(/,$/, '').trim();
    if (!texto) return;
    aviso.textContent = '';
    if (texto.length < 2) { aviso.textContent = 'Cada etiqueta necesita al menos 2 caracteres.'; return; }
    if (etiquetas.some((e) => e.toLowerCase() === texto.toLowerCase())) { aviso.textContent = 'Esa etiqueta ya está.'; caja.value = ''; return; }
    if (etiquetas.length >= 5) { aviso.textContent = 'Máximo 5 etiquetas.'; return; }
    etiquetas.push(texto);
    caja.value = '';
    pintar();
    alCambiar();
  }

  caja.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); agregar(); }
    else if (e.key === 'Backspace' && !caja.value && etiquetas.length) { etiquetas.pop(); pintar(); alCambiar(); }
  });
  caja.addEventListener('blur', agregar);
  pintar();
  return { id: 'p-tags', elemento: el('div', { class: 'etiquetas' }, lista, caja, aviso), valor: () => [...etiquetas] };
}

// ------------------------------------------------------------ lenguajes y herramientas, agrupados por categoría
function controlPila(catalogo, seleccion, deshabilitado, alCambiar) {
  const casillas = new Map();
  const grupos = ORDEN_CATEGORIAS
    .map((categoria) => ({ categoria, elementos: catalogo.filter((i) => i.category === categoria) }))
    .filter((g) => g.elementos.length);

  const elemento = el('div', { class: 'pila', id: 'p-stack' },
    grupos.length ? grupos.map((g) => el('fieldset', { class: 'pila__grupo' },
      el('legend', {}, CATEGORIAS[g.categoria]),
      el('div', { class: 'pila__items' }, g.elementos.map((item) => {
        const casilla = el('input', { type: 'checkbox', name: 'stack', value: item.stack_id, disabled: deshabilitado });
        casilla.checked = seleccion.has(item.stack_id);
        casilla.addEventListener('change', alCambiar);
        casillas.set(item.stack_id, { casilla, categoria: item.category });
        return el('label', { class: 'ficha' }, casilla, el('span', {}, item.name));
      }))))
      : el('p', { class: 'campo__ayuda' }, 'Todavía no hay lenguajes ni herramientas. Créalos en la sección «Lenguajes y herramientas».'));

  return {
    elemento,
    ids: () => [...casillas].filter(([, v]) => v.casilla.checked).map(([k]) => k).sort(),
    tieneLenguaje: () => [...casillas.values()].some((v) => v.casilla.checked && v.categoria === 'LENGUAJE'),
  };
}

// ------------------------------------------------------------ el editor
function construir(contenedor, catalogo, proyecto, vista) {
  const estado = proyecto?.status ?? 'BORRADOR';
  const archivado = estado === 'ARCHIVADO';
  const slugBloqueado = estado !== 'BORRADOR';
  const esNuevo = !proyecto;
  const p = proyecto ?? {};

  // ---- controles
  const titulo = entrada({ id: 'p-title', nombre: 'title', valor: p.title, maxlength: '120', disabled: archivado });
  const slug = entrada({ id: 'p-slug', nombre: 'slug', valor: p.slug, maxlength: '80', disabled: archivado || slugBloqueado, spellcheck: 'false', class: 'mono' });
  const corta = area({ id: 'p-short_description', nombre: 'short_description', valor: p.short_description, filas: 2, maxlength: '250', disabled: archivado });
  const larga = area({ id: 'p-description', nombre: 'description', valor: p.description, filas: 9, maxlength: '2000', disabled: archivado });
  const fecha = entrada({ id: 'p-project_date', nombre: 'project_date', tipo: 'date', valor: p.project_date, disabled: archivado });
  const demo = entrada({ id: 'p-demo_url', nombre: 'demo_url', tipo: 'url', valor: p.demo_url, maxlength: '300', placeholder: 'https://mi-proyecto.vercel.app', disabled: archivado });
  const repo = entrada({ id: 'p-repo_url', nombre: 'repo_url', tipo: 'url', valor: p.repo_url, maxlength: '300', placeholder: 'https://github.com/usuario/repositorio', disabled: archivado });
  const destacado = interruptor({ id: 'p-is_featured', nombre: 'is_featured', etiqueta: 'Proyecto destacado', valor: p.is_featured, deshabilitado: archivado });
  const etiquetas = controlEtiquetas(p.tags ?? [], archivado, () => actualizar());
  const pila = controlPila(catalogo, new Set(p.stack_ids ?? []), archivado, () => actualizar());

  const ayudaSlug = el('span', {});
  const pintarAyudaSlug = () => {
    ayudaSlug.textContent = slugBloqueado
      ? 'El slug ya no se puede cambiar porque el proyecto salió de borrador.'
      : `Solo minúsculas, números y guiones. Dirección en el blog: proyectos/${slug.value || '…'}.html`;
  };

  // El slug se arma solo a partir del título, hasta que lo escribas tú.
  let slugManual = !esNuevo;
  titulo.addEventListener('input', () => { if (!slugManual && !slugBloqueado) { slug.value = slugificar(titulo.value); pintarAyudaSlug(); } });
  slug.addEventListener('input', () => { slugManual = true; pintarAyudaSlug(); });
  pintarAyudaSlug();

  // ---- requisitos para publicar (Invariante 5 de la especificación)
  const requisitos = [
    { texto: 'Descripción corta', cumple: (d) => Boolean(d.short_description) },
    { texto: 'Descripción completa (mínimo 20 caracteres)', cumple: (d) => (d.description ?? '').length >= 20 },
    { texto: 'Fecha del proyecto', cumple: (d) => Boolean(d.project_date) },
    { texto: 'Al menos un lenguaje elegido', cumple: () => pila.tieneLenguaje() },
  ];
  const listaRequisitos = el('ul', { class: 'requisitos', id: 'requisitos' });

  // ---- lectura del formulario
  const valorOpcional = (texto) => { const t = texto.trim(); return t === '' ? null : t; };
  function leer() {
    return {
      title: titulo.value.trim(),
      slug: slug.value.trim(),
      short_description: valorOpcional(corta.value),
      description: valorOpcional(larga.value),
      project_date: fecha.value || null,
      stack_ids: pila.ids(),
      tags: etiquetas.valor(),
      repo_url: valorOpcional(repo.value),
      demo_url: valorOpcional(demo.value),
      is_featured: destacado.casilla.checked,
    };
  }

  // Las mismas reglas del Diccionario de Tipos, para avisarte antes de enviar. La API sigue siendo la que decide.
  function validar(d) {
    const e = [];
    if (d.title.length < 3) e.push({ field: 'title', issue: 'El título necesita al menos 3 caracteres.' });
    if (!d.slug) e.push({ field: 'slug', issue: 'El slug es obligatorio.' });
    else if (!PATRON_SLUG.test(d.slug)) e.push({ field: 'slug', issue: 'Solo minúsculas, números y guiones (sin espacios ni guiones al inicio o al final).' });
    if (d.description !== null && d.description.length < 20) e.push({ field: 'description', issue: 'La descripción necesita al menos 20 caracteres.' });
    if (d.demo_url && !PATRON_HTTPS.test(d.demo_url)) e.push({ field: 'demo_url', issue: 'Debe empezar con https://' });
    if (d.repo_url && !PATRON_HTTPS.test(d.repo_url)) e.push({ field: 'repo_url', issue: 'Debe empezar con https://' });
    return e;
  }

  let base = JSON.stringify(leer());
  vista.hayCambios = () => !archivado && JSON.stringify(leer()) !== base;

  // ---- botones
  const botonGuardar = el('button', { type: 'button', class: 'boton', id: 'btn-guardar', onclick: () => guardar(false) }, esNuevo ? 'Guardar borrador' : estado === 'PUBLICADO' ? 'Guardar cambios' : 'Guardar');
  const botonPublicar = el('button', { type: 'button', class: 'boton boton--primario', id: 'btn-publicar', onclick: () => guardar(true) }, 'Guardar y publicar');
  const botonArchivar = el('button', { type: 'button', class: 'boton boton--peligro-suave', id: 'btn-archivar', onclick: archivar }, 'Archivar');
  const botonEliminar = el('button', { type: 'button', class: 'boton boton--peligro-suave', id: 'btn-eliminar', onclick: eliminar }, 'Eliminar borrador');
  const todosLosBotones = [botonGuardar, botonPublicar, botonArchivar, botonEliminar];

  function actualizar() {
    const d = leer();
    listaRequisitos.replaceChildren(...requisitos.map((r) => {
      const ok = r.cumple(d);
      return el('li', { class: `requisito ${ok ? 'requisito--ok' : ''}`, dataset: { ok: String(ok) } }, el('span', { class: 'requisito__marca', 'aria-hidden': 'true' }, ok ? '✓' : '○'), r.texto);
    }));
    const completo = requisitos.every((r) => r.cumple(d));
    botonPublicar.disabled = !completo;
    botonPublicar.title = completo ? '' : 'Completa los requisitos para publicar';
    if (estado === 'PUBLICADO') botonGuardar.disabled = !completo;
  }

  function ocupado(si) {
    todosLosBotones.forEach((b) => { b.disabled = si; });
    formulario.setAttribute('aria-busy', String(si));
    if (!si) actualizar();
  }

  // ---- acciones
  async function guardar(publicar) {
    limpiarErrores(formulario);
    const datos = leer();
    const problemas = validar(datos);
    if (problemas.length) { mostrarErrores(formulario, { code: 'VALIDATION_ERROR', details: problemas }); return; }

    ocupado(true);
    let idProyecto = proyecto?.project_id ?? null;
    try {
      if (esNuevo) {
        const r = await api.crear('/api/v1/projects', datos);
        idProyecto = r.datos.project_id;
      } else {
        const r = await api.reemplazar(`/api/v1/projects/${idProyecto}`, datos);
        if (estado === 'PUBLICADO') cambioEnElBlog(r.datos);
      }
    } catch (error) {
      mostrarErrores(formulario, error);
      ocupado(false);
      return;
    }

    let publicado = false;
    if (publicar) {
      try {
        const r = await api.accion(`/api/v1/projects/${idProyecto}/publish`);
        publicado = true;
        cambioEnElBlog(r.datos);
      } catch (error) {
        avisar(`Se guardó el borrador, pero no se pudo publicar: ${mensajeDeError(error)}`, 'error');
      }
    }
    avisar(publicado ? 'Proyecto guardado y publicado.' : esNuevo ? 'Borrador creado.' : 'Cambios guardados.');
    base = JSON.stringify(leer());            // ya no hay cambios sin guardar
    if (esNuevo) location.hash = `#/proyectos/${idProyecto}`;
    else await montar(contenedor, { id: idProyecto }, vista);
  }

  async function archivar() {
    const seguro = await confirmar({
      titulo: `¿Archivar "${p.title}"?`,
      texto: 'Archivar es definitivo: ya no se podrá editar ni volver a publicar, su slug queda reservado y dejará de aparecer en el blog.',
      aceptar: 'Archivar', peligro: true,
    });
    if (!seguro) return;
    ocupado(true);
    try {
      const r = await api.accion(`/api/v1/projects/${p.project_id}/archive`);
      cambioEnElBlog(r.datos);
      avisar('Proyecto archivado.');
      base = JSON.stringify(leer());
      location.hash = '#/proyectos';
    } catch (error) {
      avisar(mensajeDeError(error), 'error');
      ocupado(false);
    }
  }

  async function eliminar() {
    const seguro = await confirmar({ titulo: `¿Eliminar el borrador "${p.title}"?`, texto: 'Se borra por completo y no se puede recuperar.', aceptar: 'Eliminar', peligro: true });
    if (!seguro) return;
    ocupado(true);
    try {
      await api.eliminar(`/api/v1/projects/${p.project_id}`);
      avisar('Borrador eliminado.');
      base = JSON.stringify(leer());
      location.hash = '#/proyectos';
    } catch (error) {
      avisar(mensajeDeError(error), 'error');
      ocupado(false);
    }
  }

  // ---- estructura
  const formulario = el('form', { class: 'formulario editor__form', id: 'form-proyecto', novalidate: true, 'aria-label': 'Datos del proyecto' },
    campo({ nombre: 'title', etiqueta: 'Título', control: titulo, requerido: true, contador: { max: 120 } }),
    campo({ nombre: 'slug', etiqueta: 'Slug (parte de la dirección)', control: slug, ayuda: ayudaSlug, requerido: true }),
    campo({ nombre: 'short_description', etiqueta: 'Descripción corta', control: corta, ayuda: 'Es el resumen que aparece en la tarjeta del inicio.', contador: { max: 250 } }),
    campo({ nombre: 'description', etiqueta: 'Descripción completa', control: larga, ayuda: 'Es el texto de la página del proyecto.', contador: { max: 2000 } }),
    campo({ nombre: 'project_date', etiqueta: 'Fecha del proyecto', control: fecha, ayuda: 'Con esta fecha se ordena el blog (la más reciente va primero).' }),
    campo({ nombre: 'stack_ids', etiqueta: 'Lenguajes y herramientas', control: pila.elemento, paraId: 'p-stack', ayuda: 'Para publicar hace falta al menos un lenguaje.' }),
    campo({ nombre: 'tags', etiqueta: 'Etiquetas', control: etiquetas.elemento, paraId: etiquetas.id, ayuda: 'Hasta 5. Enter o coma para agregar.' }),
    el('div', { class: 'campos-dos' },
      campo({ nombre: 'demo_url', etiqueta: 'Enlace al proyecto en línea', control: demo }),
      campo({ nombre: 'repo_url', etiqueta: 'Enlace al repositorio', control: repo })),
    el('div', { class: 'campo' }, destacado.elemento));
  formulario.addEventListener('submit', (e) => { e.preventDefault(); if (!archivado) guardar(false); });
  formulario.addEventListener('input', actualizar);
  formulario.addEventListener('change', actualizar);

  const resumen = el('aside', { class: 'editor__lateral', 'aria-label': 'Estado del proyecto' },
    el('section', { class: 'tarjeta' },
      el('h2', { class: 'tarjeta__titulo' }, 'Estado'),
      el('p', {}, insignia(estado)),
      !esNuevo ? el('p', { class: 'dato' }, 'Actualizado: ', formatearFechaHora(p.updated_at)) : null,
      p.published_at ? el('p', { class: 'dato' }, 'Publicado: ', formatearFechaHora(p.published_at)) : null),
    archivado ? el('section', { class: 'tarjeta' }, el('p', { class: 'dato' }, 'Este proyecto está archivado: ya no se puede editar, publicar ni eliminar.'))
      : el('section', { class: 'tarjeta' },
        el('h2', { class: 'tarjeta__titulo' }, estado === 'PUBLICADO' ? 'Debe seguir cumpliendo' : 'Para publicar necesitas'),
        listaRequisitos));

  const barra = el('div', { class: 'barra-acciones' },
    el('a', { class: 'boton boton--sutil', href: '#/proyectos', id: 'btn-volver' }, archivado ? 'Volver' : 'Cancelar'),
    el('div', { class: 'barra-acciones__grupo' },
      estado === 'BORRADOR' && !esNuevo ? botonEliminar : null,
      estado === 'PUBLICADO' ? botonArchivar : null,
      archivado ? null : botonGuardar,
      estado === 'PUBLICADO' || archivado ? null : botonPublicar));

  contenedor.replaceChildren(el('div', { class: 'vista' },
    el('div', { class: 'vista__cab' },
      el('h1', {}, esNuevo ? 'Nuevo proyecto' : archivado ? 'Proyecto archivado' : 'Editar proyecto')),
    el('div', { class: 'editor' }, formulario, resumen),
    barra));
  actualizar();
  if (esNuevo) titulo.focus();
}
