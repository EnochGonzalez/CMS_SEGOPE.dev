// Recordatorio de "cambios en el CMS que todavía no están en el blog". Dura lo que dure la pestaña.
const CLAVE = 'cms_pendiente';
const oyentes = new Set();

function notificar() {
  oyentes.forEach((funcion) => funcion(pendiente.hay()));
}

export const pendiente = {
  hay: () => sessionStorage.getItem(CLAVE) === '1',
  marcar() { sessionStorage.setItem(CLAVE, '1'); notificar(); },
  limpiar() { sessionStorage.removeItem(CLAVE); notificar(); },
  alCambiar(funcion) { oyentes.add(funcion); return () => oyentes.delete(funcion); },
};
