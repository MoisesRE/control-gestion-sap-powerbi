// Utilidades compartidas por las cuatro paginas: menu, formato de cifras y los
// primitivos para dibujar en SVG.
//
// No hay ninguna dependencia externa, y es una decision y no un descuido. Una
// libreria de graficos seria menos codigo, pero un portafolio tiene que seguir
// funcionando dentro de unos anos: un <script src> a un CDN puede caducar,
// cambiar de version o estar bloqueado en la red desde la que alguien abra la
// pagina. Ademas no estaria en el repositorio, de modo que seria la unica parte
// del sitio que la auditoria de lo publicable no recorre.

export const SVG_NS = "http://www.w3.org/2000/svg";

// Formato europeo -- punto para los millares y coma para los decimales -- y no
// el de es-PE, que agrupa al reves. Lo que decide no es el origen del dato sino
// la coherencia de lo publicado: la memoria tecnica escribe las cifras asi, y
// dos convenios en el mismo portafolio obligan al lector a comprobar si
// 80.553.599,56 y 80,553,599.56 son la misma cifra.
// `useGrouping: "always"` porque es-ES no agrupa los numeros de cuatro
// digitos, y en una columna de importes eso deja "9938" al lado de "10.334":
// la misma magnitud escrita de dos maneras obliga a contar digitos.
const opciones = { useGrouping: "always" };
const ENTERO = new Intl.NumberFormat("es-ES", { ...opciones, maximumFractionDigits: 0 });
const DOS = new Intl.NumberFormat("es-ES", { ...opciones, minimumFractionDigits: 2, maximumFractionDigits: 2 });
const UNO = new Intl.NumberFormat("es-ES", { ...opciones, minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const entero = (v) => ENTERO.format(v ?? 0);
export const dosDecimales = (v) => DOS.format(v ?? 0);
export const porcentaje = (v) => `${UNO.format((v ?? 0) * 100)} %`;

/** Miles, que es como Control de Gestion presenta el estado de resultados.
 *
 *  El negativo va entre parentesis y no con signo menos, que es el convenio
 *  contable: en una columna de cifras el parentesis se ve de un vistazo y el
 *  menos se pierde. Un cero exacto se escribe "0" y no se deja en blanco,
 *  porque un hueco no distingue "no aplica" de "no cargo". */
export function miles(valor) {
  const v = Math.round((valor ?? 0) / 1000);
  if (v === 0) return "0";
  return v < 0 ? `(${ENTERO.format(Math.abs(v))})` : ENTERO.format(v);
}

/** Escala redondeada hacia arriba, para que las marcas del eje sean legibles. */
export function escalaBonita(maximo) {
  if (!(maximo > 0)) return 1;
  const magnitud = 10 ** Math.floor(Math.log10(maximo));
  for (const paso of [1, 1.5, 2, 2.5, 5, 7.5, 10]) {
    if (magnitud * paso >= maximo) return magnitud * paso;
  }
  return magnitud * 10;
}

/** Abrevia un importe para una marca de eje: 61,4 M, 850 k. */
export function compacto(valor) {
  const abs = Math.abs(valor);
  if (abs >= 1e6) return `${UNO.format(valor / 1e6)} M`;
  if (abs >= 1e3) return `${ENTERO.format(Math.round(valor / 1e3))} k`;
  return ENTERO.format(Math.round(valor));
}

export function nodo(nombre, atributos = {}, texto = null) {
  const el = document.createElementNS(SVG_NS, nombre);
  for (const [clave, valor] of Object.entries(atributos)) el.setAttribute(clave, valor);
  if (texto !== null) el.textContent = texto;
  return el;
}

/** Lienzo SVG con titulo accesible: un grafico sin alternativa textual no
 *  existe para quien use un lector de pantalla. */
export function lienzo(ancho, alto, titulo) {
  const svg = nodo("svg", {
    class: "grafico",
    viewBox: `0 0 ${ancho} ${alto}`,
    role: "img",
    "aria-label": titulo,
    preserveAspectRatio: "xMidYMid meet",
  });
  svg.appendChild(nodo("title", {}, titulo));
  return svg;
}

export function crear(etiqueta, clase, texto) {
  const el = document.createElement(etiqueta);
  if (clase) el.className = clase;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

/** Carga un JSON del sitio, con un mensaje util cuando falla.
 *
 *  El fallo tipico no es un error del codigo: es abrir el fichero con doble
 *  clic. `fetch` sobre file:// lo bloquea el navegador, de modo que el aviso
 *  dice como servirlo en lugar de dejar la pagina en blanco. */
export async function cargarDatos(ruta, idCargando) {
  const aviso = document.getElementById(idCargando);
  try {
    const respuesta = await fetch(ruta, { cache: "no-cache" });
    if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
    const datos = await respuesta.json();
    if (aviso) aviso.hidden = true;
    return datos;
  } catch (error) {
    if (aviso) {
      aviso.className = "fallo";
      aviso.innerHTML =
        `<p>No se han podido cargar las cifras (<code>${error.message}</code>).</p>` +
        "<p>Si has abierto el fichero con doble clic, el navegador bloquea la lectura " +
        `de <code>${ruta}</code> en <code>file://</code>. Hay que servirlo por HTTP: ` +
        "<code>python -m http.server -d docs</code>.</p>";
    }
    return null;
  }
}

/** Menu: marca la pagina actual y gobierna el plegado en pantalla estrecha. */
export function montarMenu() {
  const actual = location.pathname.split("/").pop() || "index.html";
  for (const enlace of document.querySelectorAll(".menu a[href]")) {
    if (enlace.getAttribute("href") === actual) enlace.setAttribute("aria-current", "page");
  }
  const boton = document.querySelector(".alternar");
  const menu = document.querySelector(".menu");
  if (!boton || !menu) return;
  boton.addEventListener("click", () => {
    const abierto = menu.classList.toggle("abierto");
    boton.setAttribute("aria-expanded", String(abierto));
  });
}

document.addEventListener("DOMContentLoaded", montarMenu);
