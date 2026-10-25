// Recordatorio de "cambios en el CMS que todavía no están en el blog". Dura lo que dure la pestaña.
import { avisar } from './ui.js';

const CLAVE = 'cms_pendiente';
const oyentes = new Set();

function notificar() {
  oyentes.forEach((funcion) => funcion(pendiente.hay()));
}

// Se llama después de un cambio que afecta al blog. Si la API ya le avisó a Vercel (recompilation_triggered), solo se
// informa; si no (todavía no hay aviso automático, o Vercel tardó en responder), queda el recordatorio con los comandos.
export function cambioEnElBlog(datos) {
  if (datos && datos.recompilation_triggered === true) {
    avisar('Vercel está reconstruyendo el blog; en un par de minutos verás el cambio.', 'info');
  } else {
    pendiente.marcar();
  }
}

export const pendiente = {
  hay: () => sessionStorage.getItem(CLAVE) === '1',
  marcar() { sessionStorage.setItem(CLAVE, '1'); notificar(); },
  limpiar() { sessionStorage.removeItem(CLAVE); notificar(); },
  alCambiar(funcion) { oyentes.add(funcion); return () => oyentes.delete(funcion); },
};
