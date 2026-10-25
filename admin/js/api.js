// Conexión con la API. La consola se sirve desde el mismo servidor, así que las rutas son relativas.

export class ErrorApi extends Error {
  constructor({ status, code, message, details = [], retryAfter = null }) {
    super(message);
    this.name = 'ErrorApi';
    this.status = status;
    this.code = code;
    this.details = details;
    this.retryAfter = retryAfter;
  }
}

// ------------------------------------------------------------ sesión (token JWT)
const CLAVE_TOKEN = 'cms_token';

export const sesion = {
  token: () => sessionStorage.getItem(CLAVE_TOKEN),
  iniciar(token) { sessionStorage.setItem(CLAVE_TOKEN, token); },
  cerrar() { sessionStorage.removeItem(CLAVE_TOKEN); },
  // Momento (en milisegundos) en que vence el token, leído de su propio contenido.
  venceEn() {
    const token = this.token();
    if (!token) return null;
    try {
      const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      const carga = JSON.parse(atob(base64 + '='.repeat((4 - (base64.length % 4)) % 4)));
      return carga.exp * 1000;
    } catch {
      return null;
    }
  },
  vigente() {
    const vence = this.venceEn();
    return vence !== null && vence > Date.now() + 5000;
  },
};

let alExpirar = null;
export function alExpirarSesion(funcion) { alExpirar = funcion; }

// ------------------------------------------------------------ Idempotency-Key
export function nuevaClave() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

const esperar = (ms) => new Promise((resolver) => setTimeout(resolver, ms));

async function pedir(metodo, ruta, { cuerpo, formData, clave, parametros, reintentos = 2 } = {}) {
  const url = parametros ? `${ruta}?${new URLSearchParams(parametros)}` : ruta;
  const cabeceras = { Accept: 'application/json' };
  const token = sesion.token();
  if (token) cabeceras.Authorization = `Bearer ${token}`;
  if (clave) cabeceras['Idempotency-Key'] = clave;
  let body;
  if (formData) {
    body = formData;
  } else if (cuerpo !== undefined) {
    cabeceras['Content-Type'] = 'application/json';
    body = JSON.stringify(cuerpo);
  }

  let respuesta;
  for (let intento = 0; ; intento++) {
    try {
      // 'no-cache': el navegador siempre pregunta a la API si cambió (ETag); así nunca ves datos de hace un minuto.
      respuesta = await fetch(url, { method: metodo, headers: cabeceras, body, cache: 'no-cache' });
      break;
    } catch {
      // Si se cayó la red a mitad de una operación, se reintenta con la MISMA clave: la API no la repite dos veces.
      if (clave && intento < reintentos) {
        await esperar(700 * (intento + 1));
        continue;
      }
      throw new ErrorApi({ status: 0, code: 'NETWORK_ERROR', message: 'No se pudo conectar con la API. Revisa que esté encendida.' });
    }
  }

  const texto = await respuesta.text();
  let json = null;
  if (texto) {
    try { json = JSON.parse(texto); } catch { json = null; }
  }
  if (respuesta.ok) {
    return { status: respuesta.status, mensaje: json?.message ?? '', datos: json?.data ?? null, repetida: respuesta.headers.get('idempotent-replayed') === 'true' };
  }

  const error = new ErrorApi({
    status: respuesta.status,
    code: json?.code ?? 'ERROR',
    message: json?.message ?? `La API respondió HTTP ${respuesta.status}`,
    details: json?.details ?? [],
    retryAfter: respuesta.headers.get('retry-after'),
  });
  if (respuesta.status === 401 && ruta !== '/api/v1/auth/login') {
    sesion.cerrar();
    if (alExpirar) alExpirar(error);
  }
  throw error;
}

export const api = {
  iniciarSesion: (email, password) => pedir('POST', '/api/v1/auth/login', { cuerpo: { email, password } }),
  obtener: (ruta, parametros) => pedir('GET', ruta, { parametros }),
  crear: (ruta, cuerpo) => pedir('POST', ruta, { cuerpo, clave: nuevaClave() }),
  accion: (ruta) => pedir('POST', ruta, { clave: nuevaClave() }),                 // publicar, archivar
  reemplazar: (ruta, cuerpo) => pedir('PUT', ruta, { cuerpo }),
  eliminar: (ruta) => pedir('DELETE', ruta),
  subirArchivo(archivo, proposito) {
    const formulario = new FormData();
    formulario.append('purpose', proposito);
    formulario.append('file', archivo);
    return pedir('POST', '/api/v1/files', { formData: formulario, clave: nuevaClave() });
  },
  // Lee todas las páginas de una lista (la API entrega máximo 50 por página).
  async listarTodo(ruta, parametros = {}) {
    const elementos = [];
    let cursor = null;
    do {
      const r = await pedir('GET', ruta, { parametros: { limit: 50, ...parametros, ...(cursor ? { cursor } : {}) } });
      elementos.push(...r.datos.items);
      cursor = r.datos.next_cursor;
    } while (cursor);
    return elementos;
  },
};
