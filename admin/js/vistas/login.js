// Pantalla de inicio de sesión (endpoint 1).
import { api, sesion } from '../api.js';
import { el, campo, entrada, limpiarErrores, mostrarErrores, mensajeDeError } from '../ui.js';

const CORREO = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function montarLogin(raiz, { mensaje = null, alEntrar }) {
  const correo = entrada({ id: 'login-email', nombre: 'email', tipo: 'email', autocomplete: 'username', placeholder: 'tu@correo.com', maxlength: '120' });
  const clave = entrada({ id: 'login-password', nombre: 'password', tipo: 'password', autocomplete: 'current-password', maxlength: '128' });
  const ver = el('button', { type: 'button', class: 'boton boton--sutil boton--chico', 'aria-pressed': 'false',
    onclick: () => { const visible = clave.type === 'password'; clave.type = visible ? 'text' : 'password'; ver.setAttribute('aria-pressed', String(visible)); ver.textContent = visible ? 'Ocultar' : 'Mostrar'; } }, 'Mostrar');
  const boton = el('button', { type: 'submit', class: 'boton boton--primario boton--ancho', id: 'btn-entrar' }, 'Entrar');
  const formulario = el('form', { class: 'formulario', novalidate: true },
    campo({ nombre: 'email', etiqueta: 'Correo', control: correo, requerido: true }),
    campo({ nombre: 'password', etiqueta: 'Contraseña', control: el('div', { class: 'campo__con-boton' }, clave, ver), paraId: 'login-password', requerido: true }),
    boton);
  let cuentaAtras = null;

  function bloquear(segundos) {
    clearInterval(cuentaAtras);
    let restante = Math.max(1, Number(segundos) || 60);
    boton.disabled = true;
    const pintar = () => { boton.textContent = `Reintenta en ${restante} s`; };
    pintar();
    cuentaAtras = setInterval(() => {
      restante -= 1;
      if (restante <= 0) { clearInterval(cuentaAtras); boton.disabled = false; boton.textContent = 'Entrar'; } else pintar();
    }, 1000);
  }

  formulario.addEventListener('submit', async (evento) => {
    evento.preventDefault();
    limpiarErrores(formulario);
    const problemas = [];
    if (!CORREO.test(correo.value.trim())) problemas.push({ field: 'email', issue: 'Escribe un correo válido.' });
    if (clave.value.length < 8) problemas.push({ field: 'password', issue: 'La contraseña tiene al menos 8 caracteres.' });
    if (problemas.length) { mostrarErrores(formulario, { code: 'VALIDATION_ERROR', details: problemas }); return; }

    boton.disabled = true;
    boton.textContent = 'Entrando…';
    try {
      const r = await api.iniciarSesion(correo.value.trim(), clave.value);
      sesion.iniciar(r.datos.access_token);
      alEntrar();
    } catch (error) {
      boton.disabled = false;
      boton.textContent = 'Entrar';
      if (error.code === 'TOO_MANY_ATTEMPTS') {
        mostrarErrores(formulario, { code: error.code, message: `Demasiados intentos fallidos. ${error.message}`, details: [] });
        bloquear(error.retryAfter);
      } else if (error.code === 'ADMIN_NOT_CONFIGURED') {
        mostrarErrores(formulario, { code: error.code, message: 'Falta crear el administrador. En la carpeta de la API ejecuta: python -m app.configurar_admin', details: [] });
      } else if (error.code === 'INVALID_CREDENTIALS') {
        mostrarErrores(formulario, { code: error.code, message: 'Correo o contraseña incorrectos.', details: [] });
      } else {
        mostrarErrores(formulario, { code: error.code, message: mensajeDeError(error), details: error.details ?? [] });
      }
    }
  });

  raiz.replaceChildren(el('main', { class: 'acceso', id: 'principal' },
    el('section', { class: 'acceso__tarjeta' },
      el('p', { class: 'marca marca--grande' }, 'SEGOPE', el('span', { class: 'marca__sub' }, '.dev')),
      el('h1', {}, 'Consola de administración'),
      mensaje ? el('p', { class: 'acceso__mensaje', role: 'status' }, mensaje) : null,
      formulario)));
  correo.focus();
}
