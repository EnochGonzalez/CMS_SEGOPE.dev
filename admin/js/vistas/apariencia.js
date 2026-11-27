// Apariencia del blog: estilo, color de acento, tipografías, esquinas y tamaño del texto, con vista previa en vivo.
// Solo cambian los valores de las variables CSS del blog: la estructura de las páginas no se toca.
import { api } from '../api.js';
import { cambioEnElBlog } from '../estado.js';
import { avisar, campo, cargando, el, errorDeCarga, mensajeDeError, selector } from '../ui.js';

const NOMBRES_CSS = { bg: '--bg', bg_elevated: '--bg-elevated', ink: '--ink', ink_soft: '--ink-soft', line: '--line', line_strong: '--line-strong', accent: '--accent', accent_warm: '--accent-warm' };
const colorValido = (c) => /^#[0-9a-f]{6}$/i.test(c ?? '');

// ---- contraste (WCAG 2.x): las mismas fórmulas que el servidor (app/services/tema.py)
const canal = (v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
export function luminancia(hex) { const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)); return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b); }
export function contraste(a, b) { const [claro, oscuro] = [luminancia(a), luminancia(b)].sort((x, y) => y - x); return (claro + 0.05) / (oscuro + 0.05); }
export const acentoCalido = (hex) => '#' + [1, 3, 5].map((i) => Math.floor((parseInt(hex.slice(i, i + 2), 16) * 86 + 50) / 100).toString(16).padStart(2, '0')).join('');

// De la selección a las variables CSS (igual que el servidor).
export function resolver(sel, cat) {
  const paleta = cat.presets.find((p) => p.key === sel.preset).palette;
  const vars = Object.fromEntries(Object.entries(NOMBRES_CSS).map(([clave, css]) => [css, paleta[clave]]));
  if (sel.accent) { vars['--accent'] = sel.accent.toLowerCase(); vars['--accent-warm'] = acentoCalido(sel.accent); }
  vars['--font-body'] = cat.fonts_body.find((f) => f.key === sel.font_body).stack;
  vars['--font-mono'] = cat.fonts_mono.find((f) => f.key === sel.font_mono).stack;
  vars['--radius'] = cat.radius.find((r) => r.key === sel.radius).value;
  return { vars, tamano: cat.text_size.find((t) => t.key === sel.text_size).value };
}

const normalizar = (sel) => ({ ...sel, accent: sel.accent ? sel.accent.toLowerCase() : null });

export async function montar(contenedor) {
  const cuerpo = el('div', { class: 'vista' });
  contenedor.replaceChildren(cuerpo);
  let cat, guardado, sel;

  async function cargar() {
    cuerpo.replaceChildren(cargando('Cargando la apariencia…'));
    try {
      cat = (await api.obtener('/api/v1/public/theme/options')).datos;
      const actual = (await api.obtener('/api/v1/public/theme')).datos;
      guardado = normalizar({ preset: actual.preset, accent: actual.accent, font_body: actual.font_body, font_mono: actual.font_mono, radius: actual.radius, text_size: actual.text_size });
    } catch (error) {
      cuerpo.replaceChildren(errorDeCarga(error, cargar));
      return;
    }
    sel = { ...guardado };
    pintar();
  }

  function pintar() {
    // ---- estilos
    const botonesEstilo = cat.presets.map((p) => {
      const muestras = el('span', { class: 'preset__muestras', 'aria-hidden': 'true' },
        ['bg', 'bg_elevated', 'line_strong', 'accent'].map((k) => { const m = el('span', { class: 'preset__punto' }); m.style.background = p.palette[k]; return m; }));
      return el('button', { type: 'button', class: 'preset', dataset: { preset: p.key }, onclick: () => { sel.preset = p.key; actualizar(); } }, muestras, el('span', { class: 'preset__nombre' }, p.label));
    });

    // ---- acento: «el del estilo» + sugeridos + color propio
    const muestra = (color, etiqueta) => {
      const b = el('button', { type: 'button', class: 'muestra', dataset: { color: color ?? '' }, 'aria-label': etiqueta, title: etiqueta, onclick: () => { sel.accent = color; actualizar(); } });
      if (color) b.style.background = color; else b.classList.add('muestra--estilo');
      return b;
    };
    const propio = el('input', { type: 'color', id: 'acento-propio', class: 'entrada-color', 'aria-label': 'Elegir otro color de acento', value: '#ef4444' });
    propio.addEventListener('input', () => { sel.accent = propio.value; actualizar(); });
    const contrasteTexto = el('p', { class: 'contraste', id: 'contraste-fondo' });
    const contrasteBoton = el('p', { class: 'contraste', id: 'contraste-boton' });
    const avisoAcento = el('p', { class: 'campo__error', id: 'error-acento', role: 'alert', hidden: true });

    // ---- tipografías, esquinas, tamaño
    const cuerpoSel = selector({ id: 'f-body', nombre: 'font_body', opciones: cat.fonts_body.map((f) => ({ valor: f.key, texto: f.label })), valor: sel.font_body });
    const monoSel = selector({ id: 'f-mono', nombre: 'font_mono', opciones: cat.fonts_mono.map((f) => ({ valor: f.key, texto: f.label })), valor: sel.font_mono });
    cuerpoSel.addEventListener('change', () => { sel.font_body = cuerpoSel.value; actualizar(); });
    monoSel.addEventListener('change', () => { sel.font_mono = monoSel.value; actualizar(); });
    const chips = (lista, campoSel, etiqueta, id) => el('div', { class: 'chips', role: 'group', 'aria-label': etiqueta, id },
      lista.map((o) => el('button', { type: 'button', class: 'chip', dataset: { valor: o.key }, onclick: () => { sel[campoSel] = o.key; actualizar(); } }, o.label)));
    const chipsEsquinas = chips(cat.radius, 'radius', 'Esquinas', 'chips-esquinas');
    const chipsTamano = chips(cat.text_size, 'text_size', 'Tamaño del texto', 'chips-tamano');

    const guardar = el('button', { type: 'button', class: 'boton boton--primario', id: 'btn-guardar-apariencia', onclick: guardarCambios }, 'Guardar apariencia');
    const original = el('button', { type: 'button', class: 'boton boton--sutil', id: 'btn-original', onclick: () => { sel = { ...cat.default }; actualizar(); } }, 'Volver al diseño original');

    // ---- vista previa
    const previa = el('div', { class: 'vista-previa', id: 'vista-previa', role: 'img', 'aria-label': 'Vista previa de cómo se verá el blog' },
      el('div', { class: 'vp-cabecera' }, el('span', { class: 'vp-marca' }, 'SEGOPE', el('span', { class: 'vp-marca-sub' }, '.dev')),
        el('span', { class: 'vp-nav' }, el('span', {}, 'Inicio'), el('span', {}, 'Artículos'), el('span', {}, 'Acerca'))),
      el('div', { class: 'vp-cuerpo' },
        el('p', { class: 'vp-etiqueta' }, '// bitácora de desarrollo'),
        el('h3', { class: 'vp-titulo' }, 'Así se verá tu blog'),
        el('p', { class: 'vp-texto' }, 'Este texto de ejemplo usa la tipografía, los colores y el tamaño que elijas. Cámbialos y míralo aquí al instante.'),
        el('div', { class: 'vp-acciones' }, el('span', { class: 'vp-boton' }, 'Ver proyecto'), el('span', { class: 'vp-codigo' }, 'pip install fastapi')),
        el('div', { class: 'vp-tarjeta' }, el('strong', {}, 'LawPocket'), el('p', {}, 'Gestión de despachos jurídicos.'), el('span', { class: 'vp-chip' }, 'Python'))));

    cuerpo.replaceChildren(
      el('div', { class: 'vista__cab' }, el('h1', {}, 'Apariencia'), el('div', { class: 'vista__cab-acciones' }, original, guardar)),
      el('p', { class: 'nota' }, 'Cambia el estilo, el color y las tipografías de tu blog sin tocar código. La estructura de las páginas no cambia; los cambios llegan al blog cuando se regenera.'),
      el('div', { class: 'apariencia' },
        el('div', { class: 'apariencia__ajustes' },
          el('section', { class: 'tarjeta' }, el('h2', { class: 'tarjeta__titulo' }, 'Estilo'), el('div', { class: 'presets', id: 'presets' }, botonesEstilo)),
          el('section', { class: 'tarjeta' }, el('h2', { class: 'tarjeta__titulo' }, 'Color de acento'),
            el('p', { class: 'dato' }, 'El color de enlaces, etiquetas y botones. Debe leerse bien sobre el fondo y con texto blanco encima.'),
            el('div', { class: 'muestras', id: 'muestras' }, muestra(null, 'El del estilo elegido'), cat.accent_suggestions.map((c) => muestra(c, c)),
              el('label', { class: 'muestra-propia' }, el('span', {}, 'Otro'), propio)),
            contrasteTexto, contrasteBoton, avisoAcento),
          el('section', { class: 'tarjeta' }, el('h2', { class: 'tarjeta__titulo' }, 'Tipografía y forma'),
            campo({ nombre: 'font_body', etiqueta: 'Letra del texto', control: cuerpoSel }),
            campo({ nombre: 'font_mono', etiqueta: 'Letra de etiquetas y código', control: monoSel }),
            el('div', { class: 'campo' }, el('span', { class: 'campo__etiqueta' }, 'Esquinas'), chipsEsquinas),
            el('div', { class: 'campo' }, el('span', { class: 'campo__etiqueta' }, 'Tamaño del texto'), chipsTamano))),
        el('aside', { class: 'apariencia__previa', 'aria-label': 'Vista previa' }, el('h2', { class: 'tarjeta__titulo' }, 'Vista previa'), previa,
          el('p', { class: 'dato' }, 'Es una muestra aproximada: el blog real usa tus páginas con estos mismos colores y letras.'))));

    // ---- reflejar la selección en la pantalla (sin reconstruirla, para no perder el foco)
    function actualizar() {
      const { vars, tamano } = resolver(sel, cat);
      for (const [nombre, valor] of Object.entries(vars)) previa.style.setProperty(nombre, valor);
      previa.style.fontSize = tamano;
      botonesEstilo.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.preset === sel.preset)));
      cuerpo.querySelectorAll('#muestras .muestra').forEach((m) => m.setAttribute('aria-pressed', String((m.dataset.color || null) === (sel.accent ? sel.accent.toLowerCase() : null))));
      for (const [raiz, valorActual] of [[chipsEsquinas, sel.radius], [chipsTamano, sel.text_size]]) raiz.querySelectorAll('.chip').forEach((c) => c.setAttribute('aria-pressed', String(c.dataset.valor === valorActual)));
      cuerpoSel.value = sel.font_body; monoSel.value = sel.font_mono;
      if (sel.accent) propio.value = sel.accent;

      const acento = vars['--accent'];
      const fondo = vars['--bg'];
      const cT = contraste(acento, fondo), cB = contraste('#ffffff', acento);
      const okT = cT >= cat.min_contrast_text, okB = cB >= cat.min_contrast_button;
      contrasteTexto.textContent = `${okT ? '✓' : '✗'} Contraste con el fondo: ${cT.toFixed(1)}:1 (mínimo ${cat.min_contrast_text}:1)${okT ? '' : ' — prueba un color más claro'}`;
      contrasteBoton.textContent = `${okB ? '✓' : '✗'} Contraste del texto blanco de los botones: ${cB.toFixed(1)}:1 (mínimo ${cat.min_contrast_button}:1)${okB ? '' : ' — prueba un color más oscuro'}`;
      contrasteTexto.classList.toggle('contraste--ok', okT); contrasteTexto.classList.toggle('contraste--mal', !okT);
      contrasteBoton.classList.toggle('contraste--ok', okB); contrasteBoton.classList.toggle('contraste--mal', !okB);
      avisoAcento.hidden = true;

      const cambio = JSON.stringify(normalizar(sel)) !== JSON.stringify(guardado);
      guardar.disabled = !cambio || !okT || !okB;
      guardar.title = !okT || !okB ? 'El color de acento no se lee bien: elige otro.' : cambio ? '' : 'No hay cambios por guardar.';
    }

    async function guardarCambios() {
      guardar.disabled = true;
      try {
        const r = await api.reemplazar('/api/v1/theme', normalizar(sel));
        guardado = normalizar(sel);
        avisar('Apariencia guardada.');
        cambioEnElBlog(r.datos);
        actualizar();
      } catch (error) {
        const detalle = (error.details || []).find((d) => d.field === 'accent');
        if (detalle) { avisoAcento.textContent = detalle.issue; avisoAcento.hidden = false; }
        avisar(mensajeDeError(error), 'error');
        guardar.disabled = false;
      }
    }

    actualizar();
  }

  await cargar();
  return {};
}
