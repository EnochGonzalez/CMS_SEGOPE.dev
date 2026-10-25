// Certificados: listado público (12) y administración: crear (11), actualizar (13) y eliminar (14).
// El PDF y la imagen se suben con POST /api/v1/files (21) y la URL que devuelve se usa en el certificado.
import { api } from '../api.js';
import { pendiente } from '../estado.js';
import {
  avisar, campo, cargando, confirmar, dialogo, el, entrada, errorDeCarga, formatearFecha, hoy,
  limpiarErrores, mensajeDeError, mostrarErrores, selectorArchivo,
} from '../ui.js';

export async function montar(contenedor) {
  const cuerpo = el('div', { class: 'vista' });
  contenedor.replaceChildren(cuerpo);
  let certificados = [];

  async function cargar() {
    cuerpo.replaceChildren(cargando('Cargando certificados…'));
    try {
      certificados = await api.listarTodo('/api/v1/public/certificates');
    } catch (error) {
      cuerpo.replaceChildren(errorDeCarga(error, cargar));
      return;
    }
    pintar();
  }

  function formulario(certificado) {
    const esNuevo = !certificado;
    const titulo = entrada({ id: 'c-title', nombre: 'title', valor: certificado?.title, maxlength: '120' });
    const emisor = entrada({ id: 'c-issuer', nombre: 'issuer', valor: certificado?.issuer, maxlength: '80' });
    const fecha = entrada({ id: 'c-issued_at', nombre: 'issued_at', tipo: 'date', valor: certificado?.issued_at, max: hoy() });
    const pdf = selectorArchivo({ nombre: 'pdf_url', etiqueta: 'PDF del certificado', proposito: 'CERTIFICATE_PDF', accept: 'application/pdf', valor: certificado?.pdf_url, requerido: true, ayuda: 'Hasta 5 MB.' });
    const imagen = selectorArchivo({ nombre: 'image_url', etiqueta: 'Imagen del certificado', proposito: 'CERTIFICATE_IMAGE', accept: 'image/png,image/jpeg,image/webp', valor: certificado?.image_url, requerido: true, ayuda: 'JPG, PNG o WebP, hasta 2 MB. Es la que se ve al abrir el certificado en el blog.' });
    const guardar = el('button', { type: 'submit', class: 'boton boton--primario', id: 'btn-guardar-certificado' }, esNuevo ? 'Crear certificado' : 'Guardar cambios');
    const cancelar = el('button', { type: 'button', class: 'boton boton--sutil', onclick: () => ventana.cerrar() }, 'Cancelar');
    const f = el('form', { class: 'formulario', novalidate: true },
      campo({ nombre: 'title', etiqueta: 'Título', control: titulo, requerido: true }),
      el('div', { class: 'campos-dos' },
        campo({ nombre: 'issuer', etiqueta: 'Institución', control: emisor, requerido: true }),
        campo({ nombre: 'issued_at', etiqueta: 'Fecha de emisión', control: fecha, requerido: true })),
      pdf.elemento, imagen.elemento,
      el('div', { class: 'dialogo__acciones' }, cancelar, guardar));

    f.addEventListener('submit', async (evento) => {
      evento.preventDefault();
      limpiarErrores(f);
      const datos = { title: titulo.value.trim(), issuer: emisor.value.trim(), issued_at: fecha.value, pdf_url: pdf.url(), image_url: imagen.url() };
      const problemas = [];
      if (datos.title.length < 3) problemas.push({ field: 'title', issue: 'El título necesita al menos 3 caracteres.' });
      if (datos.issuer.length < 2) problemas.push({ field: 'issuer', issue: 'La institución necesita al menos 2 caracteres.' });
      if (!datos.issued_at) problemas.push({ field: 'issued_at', issue: 'Elige la fecha de emisión.' });
      if (!datos.pdf_url) problemas.push({ field: 'pdf_url', issue: 'Sube el PDF del certificado.' });
      if (!datos.image_url) problemas.push({ field: 'image_url', issue: 'Sube la imagen del certificado.' });
      if (pdf.subiendo() || imagen.subiendo()) problemas.push({ field: '', issue: 'Espera a que termine la subida del archivo.' });
      if (problemas.length) { mostrarErrores(f, { code: 'VALIDATION_ERROR', details: problemas }); return; }

      guardar.disabled = true;
      try {
        if (esNuevo) await api.crear('/api/v1/certificates', datos);
        else await api.reemplazar(`/api/v1/certificates/${certificado.certificate_id}`, datos);
        pendiente.marcar();
        avisar(esNuevo ? 'Certificado creado.' : 'Certificado actualizado.');
        ventana.cerrar();
        await cargar();
      } catch (error) {
        mostrarErrores(f, error);
        guardar.disabled = false;
      }
    });
    const ventana = dialogo({ titulo: esNuevo ? 'Nuevo certificado' : 'Editar certificado', cuerpo: f });
    titulo.focus();
  }

  async function eliminar(certificado) {
    const seguro = await confirmar({
      titulo: `¿Eliminar "${certificado.title}"?`,
      texto: 'Se elimina el certificado del CMS y dejará de aparecer en el blog. Sus archivos (PDF e imagen) se conservan en el almacenamiento.',
      aceptar: 'Eliminar', peligro: true,
    });
    if (!seguro) return;
    try {
      await api.eliminar(`/api/v1/certificates/${certificado.certificate_id}`);
      pendiente.marcar();
      avisar('Certificado eliminado.');
    } catch (error) {
      avisar(mensajeDeError(error), 'error');
    }
    await cargar();
  }

  function tarjeta(c) {
    const miniatura = el('img', { src: c.image_url, alt: '', loading: 'lazy', class: 'tarjeta-cert__img' });
    miniatura.addEventListener('error', () => miniatura.replaceWith(el('span', { class: 'tarjeta-cert__sin-vista' }, 'Sin vista previa')));
    return el('li', { class: 'tarjeta-cert', dataset: { id: c.certificate_id } },
      el('div', { class: 'tarjeta-cert__vista' }, miniatura),
      el('div', { class: 'tarjeta-cert__datos' },
        el('h2', { class: 'tarjeta-cert__titulo' }, c.title),
        el('p', { class: 'dato' }, c.issuer),
        el('p', { class: 'dato mono' }, formatearFecha(c.issued_at)),
        el('div', { class: 'tarjeta-cert__enlaces' },
          el('a', { href: c.pdf_url, target: '_blank', rel: 'noopener noreferrer' }, 'PDF'),
          el('a', { href: c.image_url, target: '_blank', rel: 'noopener noreferrer' }, 'Imagen'))),
      el('div', { class: 'tarjeta-cert__acciones' },
        el('button', { type: 'button', class: 'boton boton--chico', dataset: { accion: 'editar' }, onclick: () => formulario(c) }, 'Editar'),
        el('button', { type: 'button', class: 'boton boton--chico boton--peligro-suave', dataset: { accion: 'eliminar' }, onclick: () => eliminar(c) }, 'Eliminar')));
  }

  function pintar() {
    cuerpo.replaceChildren(
      el('div', { class: 'vista__cab' },
        el('h1', {}, 'Certificados'),
        el('button', { type: 'button', class: 'boton boton--primario', id: 'btn-nuevo-certificado', onclick: () => formulario(null) }, 'Nuevo certificado')),
      el('p', { class: 'nota' }, `${certificados.length} en total. Los certificados no tienen borrador: al crearlos ya son públicos.`),
      certificados.length
        ? el('ul', { class: 'rejilla-cert', id: 'lista-certificados' }, certificados.map(tarjeta))
        : el('p', { class: 'estado-vacio' }, 'Todavía no hay certificados.'));
  }

  await cargar();
  return {};
}
