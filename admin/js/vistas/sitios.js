// Sitios monitoreados: agregar, pausar, editar y eliminar los sitios cuyas visitas cuenta el CMS, y copiar su código.
import { api } from '../api.js';
import { colorSeguro, numero } from '../grafica.js';
import {
  avisar, campo, cargando, confirmar, copiarTexto, dialogo, el, entrada, errorDeCarga, formatearFechaHora, interruptor,
  limpiarErrores, mensajeDeError, mostrarErrores,
} from '../ui.js';

// Acepta lo que se copia de la barra del navegador y deja solo el dominio (la API hace lo mismo).
export const limpiarDominio = (texto) => texto.trim().toLowerCase().replace(/^[a-z][a-z0-9+.-]*:\/\//, '').split(/[/?#]/)[0].replace(/:\d+$/, '');

const codigoDe = (dominio) => `<script defer src="${location.origin}/t.js" data-site="${dominio}"></script>`;

export async function montar(contenedor) {
  const cuerpo = el('div', { class: 'vista' });
  contenedor.replaceChildren(cuerpo);
  let sitios = [];

  async function cargar() {
    cuerpo.replaceChildren(cargando('Cargando sitios…'));
    try {
      sitios = await api.listarTodo('/api/v1/sites');
    } catch (error) {
      cuerpo.replaceChildren(errorDeCarga(error, cargar));
      return;
    }
    pintar();
  }

  // PUT reemplaza todo el sitio, así que siempre se envían todos sus datos.
  const cuerpoPut = (s, cambios = {}) => ({ name: s.name, domain: s.domain, color: s.color, is_active: s.is_active, ...cambios });

  function verCodigo(sitio) {
    const codigo = codigoDe(sitio.domain);
    const enLocal = ['localhost', '127.0.0.1'].includes(location.hostname);
    const ventana = dialogo({
      titulo: `Código de seguimiento de ${sitio.name}`, ancho: 'normal',
      cuerpo: el('div', { class: 'codigo-sitio' },
        el('p', {}, 'Pega esta línea en el ', el('code', {}, '<head>'), ' de cada página de tu blog (o genera el blog con el CMS y ya la incluirá). Cuenta las visitas sin cookies y sin guardar datos personales.'),
        el('pre', { class: 'banner__codigo', id: 'codigo-seguimiento' }, codigo),
        enLocal ? el('p', { class: 'dato' }, 'Ahora estás en tu computadora, por eso la dirección es localhost. Cuando abras la consola desde la dirección pública de tu API, este código ya traerá esa dirección: úsalo desde ahí.') : null,
        el('p', { class: 'dato' }, 'Solo se registran visitas que vengan de ', el('strong', {}, sitio.domain), '. Mientras el sitio esté en pausa no se cuenta nada.'),
        el('div', { class: 'dialogo__acciones' },
          el('button', { type: 'button', class: 'boton', onclick: () => ventana.cerrar() }, 'Cerrar'),
          el('button', { type: 'button', class: 'boton boton--primario', id: 'btn-copiar-codigo',
            onclick: async () => avisar(await copiarTexto(codigo) ? 'Código copiado.' : 'No se pudo copiar; selecciónalo a mano.', 'info') }, 'Copiar código'))),
    });
  }

  function formulario(sitio) {
    const esNuevo = !sitio;
    const nombre = entrada({ id: 's-name', nombre: 'name', valor: sitio?.name, maxlength: '60', placeholder: 'Mi blog' });
    const dominio = entrada({ id: 's-domain', nombre: 'domain', valor: sitio?.domain, maxlength: '120', placeholder: 'segope.vercel.app', autocapitalize: 'off', spellcheck: 'false' });
    const color = entrada({ id: 's-color', nombre: 'color', tipo: 'color', valor: sitio?.color ?? '#ef4444' });
    const activo = interruptor({ id: 's-is_active', nombre: 'is_active', etiqueta: 'Monitoreando (cuenta visitas)', valor: sitio?.is_active ?? true });
    const guardar = el('button', { type: 'submit', class: 'boton boton--primario', id: 'btn-guardar-sitio' }, esNuevo ? 'Agregar sitio' : 'Guardar cambios');
    const f = el('form', { class: 'formulario', novalidate: true },
      campo({ nombre: 'name', etiqueta: 'Nombre', control: nombre, requerido: true, ayuda: 'Cómo lo verás en las estadísticas.' }),
      campo({ nombre: 'domain', etiqueta: 'Dominio', control: dominio, requerido: true, ayuda: 'Solo el dominio, por ejemplo segope.vercel.app (sin https://).' }),
      campo({ nombre: 'color', etiqueta: 'Color en las gráficas', control: color }),
      el('div', { class: 'campo' }, activo.elemento),
      el('div', { class: 'dialogo__acciones' }, el('button', { type: 'button', class: 'boton boton--sutil', onclick: () => ventana.cerrar() }, 'Cancelar'), guardar));

    dominio.addEventListener('blur', () => { dominio.value = limpiarDominio(dominio.value); });
    f.addEventListener('submit', async (evento) => {
      evento.preventDefault();
      limpiarErrores(f);
      const datos = { name: nombre.value.trim(), domain: limpiarDominio(dominio.value), color: color.value, is_active: activo.casilla.checked };
      dominio.value = datos.domain;
      const problemas = [];
      if (!datos.name) problemas.push({ field: 'name', issue: 'El nombre es obligatorio.' });
      if (!datos.domain) problemas.push({ field: 'domain', issue: 'El dominio es obligatorio.' });
      else if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$/.test(datos.domain)) problemas.push({ field: 'domain', issue: 'Escribe solo el dominio, por ejemplo segope.vercel.app.' });
      if (problemas.length) { mostrarErrores(f, { code: 'VALIDATION_ERROR', details: problemas }); return; }

      guardar.disabled = true;
      try {
        const r = esNuevo ? await api.crear('/api/v1/sites', datos) : await api.reemplazar(`/api/v1/sites/${sitio.site_id}`, datos);
        avisar(esNuevo ? 'Sitio agregado.' : 'Sitio actualizado.');
        ventana.cerrar();
        await cargar();
        if (esNuevo) verCodigo(r.datos);                    // lo siguiente que necesita es el código para su blog
      } catch (error) {
        mostrarErrores(f, error);
        guardar.disabled = false;
      }
    });
    const ventana = dialogo({ titulo: esNuevo ? 'Nuevo sitio' : 'Editar sitio', cuerpo: f });
    nombre.focus();
  }

  async function cambiarEstado(sitio, casilla) {
    casilla.disabled = true;
    try {
      await api.reemplazar(`/api/v1/sites/${sitio.site_id}`, cuerpoPut(sitio, { is_active: casilla.checked }));
      avisar(casilla.checked ? `${sitio.name}: monitoreo activado.` : `${sitio.name}: monitoreo en pausa (se conserva el historial).`);
    } catch (error) {
      avisar(mensajeDeError(error), 'error');
    }
    await cargar();
  }

  async function eliminar(sitio) {
    const seguro = await confirmar({
      titulo: `¿Eliminar «${sitio.name}»?`, aceptar: 'Eliminar sitio y sus visitas', peligro: true,
      texto: el('div', {}, el('p', {}, `Se borran el sitio y sus ${numero(sitio.views_total)} visitas registradas. No se puede deshacer.`),
        el('p', {}, 'Si solo quieres dejar de contar, mejor ponlo en pausa: el historial se conserva.')),
    });
    if (!seguro) return;
    try {
      await api.eliminar(`/api/v1/sites/${sitio.site_id}`);
      avisar('Sitio eliminado.');
    } catch (error) {
      avisar(mensajeDeError(error), 'error');
    }
    await cargar();
  }

  function fila(s) {
    const punto = el('span', { class: 'punto-sitio', 'aria-hidden': 'true' });
    punto.style.background = colorSeguro(s.color);
    const monitoreo = interruptor({ id: `act-${s.site_id}`, nombre: 'activo', etiqueta: 'Monitoreando', valor: s.is_active });
    monitoreo.casilla.addEventListener('change', () => cambiarEstado(s, monitoreo.casilla));
    const estado = s.views_total === 0 ? 'Aún sin visitas' : `${numero(s.views_total)} visitas · última: ${formatearFechaHora(s.last_view_at)}`;
    return el('li', { class: 'fila fila--sitio', dataset: { id: s.site_id, dominio: s.domain } },
      punto,
      el('div', { class: 'fila__principal' },
        el('span', { class: 'fila__titulo fila__titulo--texto' }, s.name),
        el('span', { class: 'fila__slug' }, s.domain),
        el('span', { class: 'fila__meta' }, estado)),
      el('div', { class: 'fila__visible' }, monitoreo.elemento),
      el('div', { class: 'fila__acciones' },
        el('button', { type: 'button', class: 'boton boton--chico', dataset: { accion: 'codigo' }, onclick: () => verCodigo(s) }, 'Código'),
        el('button', { type: 'button', class: 'boton boton--chico', dataset: { accion: 'editar' }, onclick: () => formulario(s) }, 'Editar'),
        el('button', { type: 'button', class: 'boton boton--chico boton--peligro-suave', dataset: { accion: 'eliminar' }, onclick: () => eliminar(s) }, 'Eliminar')));
  }

  function pintar() {
    cuerpo.replaceChildren(
      el('div', { class: 'vista__cab' },
        el('h1', {}, 'Sitios'),
        el('div', { class: 'vista__cab-acciones' },
          el('a', { class: 'boton', href: '#/estadisticas', id: 'enlace-estadisticas' }, 'Ver estadísticas'),
          el('button', { type: 'button', class: 'boton boton--primario', id: 'btn-nuevo-sitio', onclick: () => formulario(null) }, 'Nuevo sitio'))),
      el('p', { class: 'nota' }, 'Los sitios que el CMS monitorea. Cada uno cuenta sus visitas con una línea de código en sus páginas; si lo pausas, deja de contar pero conserva su historial.'),
      sitios.length
        ? el('ul', { class: 'lista', id: 'lista-sitios' }, sitios.map(fila))
        : el('div', { class: 'vacio-guiado', id: 'sitios-vacio' },
          el('p', {}, el('strong', {}, 'Todavía no monitoreas ningún sitio.')),
          el('p', { class: 'dato' }, 'Agrega tu blog para empezar a contar visitas. Te daremos una línea de código para pegar en sus páginas.'),
          el('button', { type: 'button', class: 'boton boton--primario', id: 'btn-primer-sitio', onclick: () => formulario(null) }, 'Agregar mi primer sitio')));
  }

  await cargar();
  return {};
}
