// Estado de resultados dinamico.
//
// Reproduce fila a fila la plantilla que Control de Gestion usa, y la compone
// desde las siete lineas de importe que publica `cifras.json` con la misma
// cascada que la medida `Importe PL` del modelo semantico. Es el tercer camino
// independiente a la misma cifra: PostgreSQL la agrega, DAX la recompone en
// VertiPaq y esto la recompone en el navegador. Un error de modelado tendria
// que repetirse identico en los tres para pasar desapercibido.
//
// Las lineas se publican y los subtotales no, porque un subtotal no es un dato:
// es aritmetica sobre las siete. Publicarlos calculados obligaria a mantener la
// misma formula en el generador y aqui, y a que las dos copias no divergieran.

import { crear, dosDecimales, entero, miles, porcentaje } from "./comun.js";

/** Las siete lineas de importe. El orden es el del estado de resultados. */
export const LINEAS = [
  "Ingresos",
  "Costos Ventas",
  "Gastos Adm/Ventas",
  "Depreciacion",
  "I/E. Excepcionales",
  "I/E. Financieros",
  "Tipo de Cambio",
];

/** Las 31 filas de la plantilla, tal y como las declara el modelo semantico.
 *
 *  `tipo` gobierna el formato y el sombreado: Importe suma cuentas, Subtotal
 *  acumula lineas anteriores y Margen divide entre los ingresos. */
const PLANTILLA = [
  ["Ingresos", "Importe", "ingresos"],
  ["Costos Ventas", "Importe", "costos"],
  ["Utilidad Bruta", "Subtotal", "bruta"],
  ["% Margen Bruto", "Margen", "bruta"],
  ["Gastos Adm/Ventas", "Importe", "gastos"],
  ["% Gastos Adm/Ventas", "Margen", "gastos"],
  ["Depreciacion", "Importe", "depreciacion"],
  ["% Gastos Depreciacion", "Margen", "depreciacion"],
  ["Depreciacion por Uso", "Importe", "depreciacionUso"],
  ["% Depreciacion por Uso", "Margen", "depreciacionUso"],
  ["I/E. Excepcionales", "Importe", "excepcionales"],
  ["% I/E. Excepcionales", "Margen", "excepcionales"],
  ["Utilidad Operativa", "Subtotal", "operativa"],
  ["% Margen operativo", "Margen", "operativa"],
  ["I/E. Financieros", "Importe", "financieros"],
  ["% I/E. Financieros", "Margen", "financieros"],
  ["Utilidad Neta Negocio (s/vta. Unidades)", "Subtotal", "netaSinVenta"],
  ["% Margen Neto Negocio", "Margen", "netaSinVenta"],
  ["Venta de Unidades (inc. Enaj.)", "Importe", "ventaUnidades"],
  ["Utilidad Neta Negocio", "Subtotal", "netaNegocio"],
  ["% Margen negocio", "Margen", "netaNegocio"],
  ["Gastos Soporte Directo - Corporativo", "Importe", "soporte"],
  ["% Gastos Soporte Directo / U. Neta Neg.", "MargenNeto", "soporte"],
  ["Utilidad Neta Negocio Total (antes T.C)", "Subtotal", "antesTC"],
  ["% Margen negocio total", "Margen", "antesTC"],
  ["Tipo de Cambio", "Importe", "tipoCambio"],
  ["% TC / U. Neta Neg.", "MargenNeto", "tipoCambio"],
  ["Utilidad Neta Negocio Total", "Subtotal", "netaTotal"],
  ["% Margen Neto", "Margen", "netaTotal"],
  ["Ebitda Negocio", "Subtotal", "ebitda"],
  ["% Margen Ebitda", "Margen", "ebitda"],
];

/** Suma las siete lineas del escenario para los periodos pedidos.
 *
 *  Una linea ausente vale cero y no queda sin resolver: los dos presupuestos no
 *  presupuestan diferencia de cambio, de modo que `Tipo de Cambio` no existe
 *  para ellos. Es un dato del origen, no un hueco, y la fila tiene que ensenar
 *  "0" -- un blanco no distingue "no aplica" de "no cargo". */
export function sumarLineas(filas, escenario, periodos) {
  const total = Object.fromEntries(LINEAS.map((l) => [l, 0]));
  for (const fila of filas) {
    if (fila.escenario_clave !== escenario) continue;
    if (periodos && !periodos.has(fila.periodo)) continue;
    total[fila.linea] += fila.importe;
  }
  return total;
}

/** La cascada de subtotales de `Importe PL`, calcada.
 *
 *  Las tres lineas que este extracto no tiene valen cero y estan declaradas, no
 *  omitidas: dejan ver que la plantilla las contempla y que el perimetro no las
 *  cubre. La depreciacion por uso y la venta de unidades quedan fuera del
 *  extracto, y el soporte corporativo es el reparto de costes de otras unidades
 *  que el proyecto documenta como fuera de alcance desde la primera etapa. */
export function componer(linea) {
  const ingresos = linea["Ingresos"];
  const costos = linea["Costos Ventas"];
  const gastos = linea["Gastos Adm/Ventas"];
  const depreciacion = linea["Depreciacion"];
  const excepcionales = linea["I/E. Excepcionales"];
  const financieros = linea["I/E. Financieros"];
  const tipoCambio = linea["Tipo de Cambio"];

  const depreciacionUso = 0;
  const ventaUnidades = 0;
  const soporte = 0;

  const bruta = ingresos + costos;
  const operativa = bruta + gastos + depreciacion + depreciacionUso + excepcionales;
  const netaSinVenta = operativa + financieros;
  const netaNegocio = netaSinVenta + ventaUnidades;
  const antesTC = netaNegocio + soporte;
  const netaTotal = antesTC + tipoCambio;
  const ebitda = operativa - depreciacion - depreciacionUso;

  return {
    ingresos, costos, gastos, depreciacion, depreciacionUso, excepcionales,
    financieros, tipoCambio, ventaUnidades, soporte,
    bruta, operativa, netaSinVenta, netaNegocio, antesTC, netaTotal, ebitda,
  };
}

/** Division protegida: un mes sin facturacion no tiene margen, y cero por
 *  ciento no es lo mismo que indefinido. Es el `DIVIDE` del modelo. */
const dividir = (a, b) => (b ? a / b : null);

function valorDeFila(magnitudes, clave, tipo) {
  if (tipo === "Importe" || tipo === "Subtotal") return magnitudes[clave];
  const base = tipo === "MargenNeto" ? magnitudes.netaNegocio : magnitudes.ingresos;
  return dividir(magnitudes[clave], base);
}

/** Una variacion es favorable cuando sale positiva, tanto en ingresos como en
 *  costes: facturar de mas da una diferencia positiva, y gastar de menos da un
 *  numero negativo mas proximo a cero, que tambien es mayor. El convenio de
 *  signo de SAP hace que la regla sea una sola para todas las lineas. */
function celdaVariacion(fila, actual, comparado, tipo) {
  const hayComparacion = comparado !== null && comparado !== undefined;
  const importe = fila.insertCell();
  const relativo = fila.insertCell();
  const senal = fila.insertCell();

  if (tipo === "Margen" || tipo === "MargenNeto") {
    // Entre dos margenes la diferencia son puntos porcentuales, no soles.
    importe.className = "cifra";
    if (actual === null || !hayComparacion) {
      importe.textContent = "";
      return;
    }
    const puntos = (actual - comparado) * 100;
    importe.textContent = `${puntos >= 0 ? "" : "-"}${dosDecimales(Math.abs(puntos))} pp`;
    importe.classList.add(puntos >= 0 ? "var-bien" : "var-mal");
    return;
  }

  if (!hayComparacion) {
    importe.className = "cifra";
    return;
  }

  const diferencia = actual - comparado;
  importe.className = "cifra";
  importe.textContent = miles(diferencia);

  // Una linea en cero en las dos columnas no tiene variacion que juzgar. Sin
  // esto, las tres lineas que el extracto no cubre salian con semaforo verde,
  // que es peor que no decir nada: afirma que algo va bien donde no hay dato.
  if (Math.abs(actual) < 0.5 && Math.abs(comparado) < 0.5) {
    relativo.className = "cifra";
    relativo.textContent = "—";
    return;
  }

  relativo.className = "cifra";
  const ratio = dividir(diferencia, Math.abs(comparado));
  relativo.textContent = ratio === null ? "—" : porcentaje(ratio);

  const bien = diferencia >= 0;
  importe.classList.add(bien ? "var-bien" : "var-mal");
  relativo.classList.add(bien ? "var-bien" : "var-mal");
  senal.innerHTML = `<span class="semaforo ${bien ? "bien" : "mal"}" aria-hidden="true"></span>`;
  senal.setAttribute("aria-label", bien ? "favorable" : "desfavorable");
}

/**
 * Dibuja el estado de resultados en `tabla`.
 *
 * @param {object} columnas  {actual, presupuesto, anterior} con las magnitudes
 *                           ya compuestas, o null cuando esa columna no aplica.
 * @param {object} rotulos   el encabezado de cada columna.
 */
export function pintarEstadoDeResultados(tabla, columnas, rotulos) {
  tabla.replaceChildren();

  const cabeza = tabla.createTHead();
  const grupos = cabeza.insertRow();
  grupos.className = "grupos";
  const vacio = crear("th", null, "");
  vacio.scope = "col";
  grupos.appendChild(vacio);

  const columnasVisibles = [
    ["actual", rotulos.actual],
    ["presupuesto", rotulos.presupuesto],
    ["anterior", rotulos.anterior],
  ].filter(([clave]) => columnas[clave]);

  const grupoCifras = crear("th", null, "Estado de resultados (miles de soles)");
  grupoCifras.colSpan = columnasVisibles.length;
  grupoCifras.scope = "colgroup";
  grupos.appendChild(grupoCifras);

  const comparaciones = [];
  if (columnas.presupuesto) comparaciones.push(["presupuesto", `Variacion vs ${rotulos.presupuesto}`]);
  if (columnas.anterior) comparaciones.push(["anterior", `Variacion vs ${rotulos.anterior}`]);
  for (const [, titulo] of comparaciones) {
    const th = crear("th", null, titulo);
    th.colSpan = 3;
    th.scope = "colgroup";
    grupos.appendChild(th);
  }

  const encabezados = cabeza.insertRow();
  const primera = crear("th", null, "Linea");
  primera.scope = "col";
  encabezados.appendChild(primera);
  for (const [, titulo] of columnasVisibles) {
    const th = crear("th", null, titulo);
    th.scope = "col";
    encabezados.appendChild(th);
  }
  for (const comparacion of comparaciones) {
    for (const titulo of ["S/. 000", "%", ""]) {
      const th = crear("th", null, titulo);
      th.scope = "col";
      encabezados.appendChild(th);
    }
    void comparacion;
  }

  const cuerpo = tabla.createTBody();
  for (const [etiqueta, tipo, clave] of PLANTILLA) {
    const fila = cuerpo.insertRow();
    if (tipo === "Subtotal") fila.classList.add("subtotal");
    if (tipo === "Margen" || tipo === "MargenNeto") fila.classList.add("margen");

    const nombre = fila.insertCell();
    nombre.textContent = etiqueta;

    const valores = {};
    for (const [clavecol] of columnasVisibles) {
      const magnitudes = columnas[clavecol];
      const valor = valorDeFila(magnitudes, clave, tipo);
      valores[clavecol] = valor;

      const celda = fila.insertCell();
      celda.className = "cifra";
      if (tipo === "Margen" || tipo === "MargenNeto") {
        celda.textContent = valor === null ? "—" : porcentaje(valor);
      } else {
        celda.textContent = miles(valor);
      }
    }

    if (tipo === "Importe" && Math.abs(valores.actual ?? 0) < 0.5) fila.classList.add("cero");

    for (const [clavecol] of comparaciones) {
      celdaVariacion(fila, valores.actual, valores[clavecol], tipo);
    }
  }

  return tabla;
}

/** Resumen de una columna para las tarjetas de cabecera. */
export function resumen(magnitudes) {
  return [
    { etiqueta: "Ingresos", valor: entero(magnitudes.ingresos), pie: "perimetro oficial" },
    { etiqueta: "Utilidad bruta", valor: entero(magnitudes.bruta), pie: "ingresos menos coste de ventas" },
    { etiqueta: "Resultado neto", valor: entero(magnitudes.netaTotal), pie: "suma de las siete lineas" },
    {
      etiqueta: "Margen neto",
      valor: magnitudes.ingresos ? porcentaje(magnitudes.netaTotal / magnitudes.ingresos) : "—",
      pie: "resultado sobre ingresos",
    },
  ];
}
