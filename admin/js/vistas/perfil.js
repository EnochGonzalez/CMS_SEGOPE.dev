// Perfil y contacto: lectura pública (19) y actualización (20). Es un registro único: solo se edita.
import { api } from '../api.js';
import { cambioEnElBlog } from '../estado.js';
import {
  area, avisar, campo, cargando, el, entrada, errorDeCarga, formatearFechaHora, limpiarErrores, mostrarErrores, selectorArchivo,
} from '../ui.js';

const PATRON_CORREO = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PATRON_TELEFONO = /^\+?[0-9][0-9 -]{6,18}$/;
const PATRON_GITHUB = /^https:\/\/github\.com\/[A-Za-z0-9-]+\/?$/;

export async function montar(contenedor, parametros, vista = {}) {
  const cuerpo = el('div', { class: 'vista' });
  contenedor.replaceChildren(cuerpo);
  cuerpo.append(cargando('Cargando perfil…'));
  let perfil;
  try {
    perfil = (await api.obtener('/api/v1/public/profile')).datos;
  } catch (error) {
    cuerpo.replaceChildren(errorDeCarga(error, () => montar(contenedor, parametros, vista)));
    return vista;
  }

  const opcional = (texto) => { const t = texto.trim(); return t === '' ? null : t; };
  const nombre = entrada({ id: 'f-full_name', nombre: 'full_name', valor: perfil.full_name, maxlength: '80' });
  const puesto = entrada({ id: 'f-job_title', nombre: 'job_title', valor: perfil.job_title, maxlength: '80' });
  const lema = area({ id: 'f-tagline', nombre: 'tagline', valor: perfil.tagline, filas: 2, maxlength: '160' });
  const bio = area({ id: 'f-bio', nombre: 'bio', valor: perfil.bio, filas: 6, maxlength: '1000' });
  const correo = entrada({ id: 'f-email', nombre: 'email', tipo: 'email', valor: perfil.email, maxlength: '120', autocomplete: 'off' });
  const telefono = entrada({ id: 'f-phone', nombre: 'phone', tipo: 'tel', valor: perfil.phone, maxlength: '20', placeholder: '960-123-4567' });
  const github = entrada({ id: 'f-github_url', nombre: 'github_url', tipo: 'url', valor: perfil.github_url, maxlength: '100', placeholder: 'https://github.com/usuario' });
  const foto = selectorArchivo({ nombre: 'photo_url', etiqueta: 'Foto', proposito: 'PROFILE_PHOTO', accept: 'image/png,image/jpeg,image/webp', valor: perfil.photo_url, ayuda: 'JPG, PNG o WebP, hasta 2 MB.' });
  const guardar = el('button', { type: 'submit', class: 'boton boton--primario', id: 'btn-guardar-perfil' }, 'Guardar perfil');

  const leer = () => ({
    full_name: nombre.value.trim(), job_title: puesto.value.trim(), tagline: lema.value.trim(), bio: bio.value.trim(),
    photo_url: foto.url(), email: correo.value.trim(), phone: opcional(telefono.value), github_url: opcional(github.value),
  });
  let base = JSON.stringify(leer());
  vista.hayCambios = () => JSON.stringify(leer()) !== base;

  const formulario = el('form', { class: 'formulario formulario--ancho', id: 'form-perfil', novalidate: true },
    el('div', { class: 'campos-dos' },
      campo({ nombre: 'full_name', etiqueta: 'Nombre completo', control: nombre, requerido: true }),
      campo({ nombre: 'job_title', etiqueta: 'Puesto', control: puesto, requerido: true })),
    campo({ nombre: 'tagline', etiqueta: 'Frase corta', control: lema, ayuda: 'Aparece en «Sobre el autor» del inicio.', requerido: true, contador: { max: 160 } }),
    campo({ nombre: 'bio', etiqueta: 'Biografía', control: bio, ayuda: 'Aparece en la página Acerca.', requerido: true, contador: { max: 1000 } }),
    foto.elemento,
    el('div', { class: 'campos-tres' },
      campo({ nombre: 'email', etiqueta: 'Correo', control: correo, requerido: true }),
      campo({ nombre: 'phone', etiqueta: 'Teléfono', control: telefono, ayuda: 'Opcional.' }),
      campo({ nombre: 'github_url', etiqueta: 'GitHub', control: github, ayuda: 'Opcional.' })),
    el('div', { class: 'barra-acciones' }, el('span', { class: 'dato' }, `Última actualización: ${formatearFechaHora(perfil.updated_at)}`), guardar));

  formulario.addEventListener('submit', async (evento) => {
    evento.preventDefault();
    limpiarErrores(formulario);
    const d = leer();
    const e = [];
    if (d.full_name.length < 3) e.push({ field: 'full_name', issue: 'El nombre necesita al menos 3 caracteres.' });
    if (d.job_title.length < 3) e.push({ field: 'job_title', issue: 'El puesto necesita al menos 3 caracteres.' });
    if (!d.tagline) e.push({ field: 'tagline', issue: 'Escribe una frase corta.' });
    if (d.bio.length < 20) e.push({ field: 'bio', issue: 'La biografía necesita al menos 20 caracteres.' });
    if (!PATRON_CORREO.test(d.email)) e.push({ field: 'email', issue: 'Escribe un correo válido.' });
    if (d.phone && !PATRON_TELEFONO.test(d.phone)) e.push({ field: 'phone', issue: 'Usa solo números, espacios y guiones (7 a 19 caracteres).' });
    if (d.github_url && !PATRON_GITHUB.test(d.github_url)) e.push({ field: 'github_url', issue: 'Debe ser https://github.com/tu-usuario' });
    if (foto.subiendo()) e.push({ field: '', issue: 'Espera a que termine la subida de la foto.' });
    if (e.length) { mostrarErrores(formulario, { code: 'VALIDATION_ERROR', details: e }); return; }

    guardar.disabled = true;
    try {
      const r = await api.reemplazar('/api/v1/profile', d);
      cambioEnElBlog(r.datos);
      base = JSON.stringify(d);
      avisar('Perfil guardado.');
      await montar(contenedor, parametros, vista);
    } catch (error) {
      mostrarErrores(formulario, error);
      guardar.disabled = false;
    }
  });

  cuerpo.replaceChildren(el('div', { class: 'vista__cab' }, el('h1', {}, 'Perfil y contacto')), formulario);
  return vista;
}
