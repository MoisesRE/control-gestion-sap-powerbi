// Panel del estado de resultados: controles, KPIs, la tabla de 31 lineas, el
// grafico mensual y la reconciliacion. Vive en su propio modulo porque lo usa
// el articulo del caso y antes estaba incrustado en la portada; tenerlo en dos
// sitios era garantizar que un dia divergieran.
//
// Espera encontrar en la pagina los elementos: cargando, contenido, ejercicios,
// periodo, vista, aviso-perimetro, kpis, tabla-pl, grafico-mensual,
// tabla-reconciliacion y sello.

import { cargarDatos, compacto, crear, dosDecimales, escalaBonita, lienzo, miles, nodo, porcentaje } from "./comun.js";
import { componer, pintarEstadoDeResultados, resumen, sumarLineas } from "./pl.js";

const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
               "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

const estado = { datos: null, ejercicio: null, periodo: 0, vista: "acumulado" };

function escenario(tipo, ejercicio) {
  return `${tipo}${ejercicio}`;
}

function cobertura(clave) {
  const periodos = estado.datos.pl_oficial
    .filter((f) => f.escenario_clave === clave)
    .map((f) => f.periodo);
  return periodos.length ? Math.max(...periodos) : 0;
}

/** Los periodos que entran en la seleccion, recortados a lo que el real cubre.
 *
 *  **El recorte es la decision que sostiene toda la comparacion.** El real de
 *  2026 cubre diez periodos y su presupuesto los doce: sumar el ejercicio
 *  entero de cada uno y restarlos inventaria una caida de dos meses de
 *  actividad que no se ha producido. Las tres columnas se calculan siempre
 *  sobre el mismo conjunto de meses, de modo que la variacion mide lo que dice
 *  medir.
 *
 *  Con un mes elegido, la vista decide si se mira ese mes solo o el acumulado
 *  desde enero, que son las dos columnas de la plantilla original. */
function periodosSeleccionados() {
  const cubiertos = cobertura(escenario("R", estado.ejercicio));
  if (!estado.periodo) {
    return new Set(Array.from({ length: cubiertos }, (_, i) => i + 1));
  }
  if (estado.vista === "mes") return new Set([estado.periodo]);
  return new Set(Array.from({ length: estado.periodo }, (_, i) => i + 1));
}

function magnitudesDe(clave) {
  const existe = estado.datos.pl_oficial.some((f) => f.escenario_clave === clave);
  if (!existe) return null;
  return componer(sumarLineas(estado.datos.pl_oficial, clave, periodosSeleccionados()));
}

function pintarEjercicios() {
  const ejercicios = [...new Set(estado.datos.pl_oficial.map((f) => f.ejercicio))].sort();
  const caja = document.getElementById("ejercicios");
  caja.replaceChildren();
  for (const ejercicio of ejercicios) {
    const boton = crear("button", null, String(ejercicio));
    boton.type = "button";
    boton.setAttribute("aria-pressed", String(ejercicio === estado.ejercicio));
    boton.addEventListener("click", () => {
      estado.ejercicio = ejercicio;
      pintarTodo();
    });
    caja.appendChild(boton);
  }
}

function pintarPeriodos() {
  const select = document.getElementById("periodo");
  select.replaceChildren();
  const completo = crear("option", null, "Ejercicio completo");
  completo.value = "0";
  select.appendChild(completo);
  MESES.forEach((mes, indice) => {
    const opcion = crear("option", null, mes);
    opcion.value = String(indice + 1);
    select.appendChild(opcion);
  });
  select.value = String(estado.periodo);
}

function pintarVista() {
  for (const boton of document.querySelectorAll("#vista button")) {
    boton.setAttribute("aria-pressed", String(boton.dataset.vista === estado.vista));
    boton.disabled = estado.periodo === 0;
  }
}

/** Explica el recorte cuando el real no cubre el ejercicio entero.
 *
 *  No es una nota al pie opcional: sin ella, un lector que vea "Ppto 2026" por
 *  58,6 millones cuando el presupuesto anual son 71,7 pensaria que la cifra
 *  esta mal. Lo que esta recortado es la comparacion, a proposito. */
function pintarAviso(claveReal) {
  const caja = document.getElementById("aviso-perimetro");
  caja.replaceChildren();
  const cubiertos = cobertura(claveReal);
  const pedido = estado.periodo || 12;
  if (cubiertos >= 12 && pedido <= cubiertos) return;

  const aviso = crear("div", "aviso");
  if (estado.periodo && estado.periodo > cubiertos) {
    aviso.innerHTML =
      `<p><strong>Sin dato real en ${MESES[estado.periodo - 1].toLowerCase()} de ` +
      `${estado.ejercicio}.</strong> El ejercicio cubre ${cubiertos} periodos, de modo ` +
      "que la columna del real sale en cero y la variacion mide el presupuesto entero " +
      "contra nada. Elige un periodo dentro del alcance para que la comparacion " +
      "signifique algo.</p>";
  } else {
    aviso.innerHTML =
      `<p><strong>Comparacion recortada a ${cubiertos} periodos.</strong> El real de ` +
      `${estado.ejercicio} llega hasta ${MESES[cubiertos - 1].toLowerCase()}, y las tres ` +
      "columnas se suman sobre esos mismos meses. Enfrentar diez meses de ejecucion " +
      "contra doce de presupuesto inventaria una caida de actividad que no se ha " +
      "producido: sin el recorte, la ejecucion de ingresos saldria en el 85,6% en lugar " +
      "del 104,8% real.</p>";
  }
  caja.appendChild(aviso);
}

function pintarKpis(magnitudes) {
  const caja = document.getElementById("kpis");
  caja.replaceChildren();
  for (const tarjeta of resumen(magnitudes)) {
    const div = crear("div", "kpi");
    div.appendChild(crear("p", "etiqueta", tarjeta.etiqueta));
    div.appendChild(crear("p", "valor", tarjeta.valor));
    div.appendChild(crear("p", "pie", tarjeta.pie));
    caja.appendChild(div);
  }
}

function pintarMensual(claveReal) {
  const filas = estado.datos.mensual
    .filter((m) => m.escenario_clave === claveReal)
    .sort((a, b) => a.periodo - b.periodo);
  const figura = document.getElementById("grafico-mensual");
  if (!filas.length) { figura.replaceChildren(); return; }

  const ancho = 960, alto = 330;
  const margen = { arriba: 14, derecha: 14, abajo: 32, izquierda: 66 };
  const util = { ancho: ancho - margen.izquierda - margen.derecha, alto: alto - margen.arriba - margen.abajo };

  const tope = escalaBonita(Math.max(
    ...filas.map((f) => Math.max(f.ingresos, f.costes, Math.abs(f.resultado_acumulado)))
  ));
  const y = (v) => margen.arriba + util.alto - (v / tope) * util.alto;
  const paso = util.ancho / filas.length;
  const grosor = Math.min(17, (paso - 10) / 2);

  const svg = lienzo(ancho, alto, `Ingresos, costes y resultado acumulado por periodo en ${claveReal}`);
  for (let i = 0; i <= 4; i++) {
    const v = (tope / 4) * i;
    svg.appendChild(nodo("line", { class: "rejilla-eje", x1: margen.izquierda, x2: ancho - margen.derecha, y1: y(v), y2: y(v) }));
    svg.appendChild(nodo("text", { class: "marca-eje fin", x: margen.izquierda - 10, y: y(v) + 4 }, compacto(v)));
  }

  const base = margen.arriba + util.alto;
  filas.forEach((fila, i) => {
    const centro = margen.izquierda + paso * (i + 0.5);
    svg.appendChild(nodo("rect", { x: centro - grosor - 2, width: grosor, y: y(fila.ingresos), height: Math.max(1, base - y(fila.ingresos)), fill: "var(--serie-1)", rx: 2 }));
    svg.appendChild(nodo("rect", { x: centro + 2, width: grosor, y: y(fila.costes), height: Math.max(1, base - y(fila.costes)), fill: "var(--serie-2)", rx: 2 }));
    svg.appendChild(nodo("text", { class: "marca-eje centro", x: centro, y: alto - 12 }, MESES[fila.periodo - 1].slice(0, 3)));
  });
  svg.appendChild(nodo("line", { class: "linea-eje", x1: margen.izquierda, x2: ancho - margen.derecha, y1: base, y2: base }));

  const puntos = filas.map((f, i) => `${margen.izquierda + paso * (i + 0.5)},${y(f.resultado_acumulado)}`).join(" ");
  svg.appendChild(nodo("polyline", { points: puntos, fill: "none", stroke: "var(--serie-3)", "stroke-width": 2.5, "stroke-linejoin": "round", "stroke-linecap": "round" }));
  const ultima = filas[filas.length - 1];
  svg.appendChild(nodo("circle", { cx: margen.izquierda + paso * (filas.length - 0.5), cy: y(ultima.resultado_acumulado), r: 4.5, fill: "var(--serie-3)", stroke: "var(--papel-alto)", "stroke-width": 2 }));

  figura.replaceChildren(svg);
}

function pintarReconciliacion() {
  const tabla = document.getElementById("tabla-reconciliacion");
  tabla.replaceChildren();
  const cabeza = tabla.createTHead().insertRow();
  for (const titulo of ["Escenario", "Maqueta oficial", "Pipeline", "Diferencia", "Tolerancia", "Veredicto"]) {
    const th = crear("th", null, titulo);
    th.scope = "col";
    cabeza.appendChild(th);
  }
  const cuerpo = tabla.createTBody();
  for (const fila of estado.datos.reconciliacion) {
    const tr = cuerpo.insertRow();
    tr.insertCell().textContent = fila.escenario;
    for (const valor of [fila.maqueta, fila.pipeline, fila.diferencia, fila.tolerancia]) {
      const td = tr.insertCell();
      td.className = "cifra";
      td.textContent = dosDecimales(valor);
    }
    const cuadra = Math.abs(fila.diferencia) <= fila.tolerancia;
    const td = tr.insertCell();
    td.innerHTML = `<span class="semaforo ${cuadra ? "bien" : "mal"}"></span> ${cuadra ? "Cuadra" : "Descuadre"}`;
    td.className = cuadra ? "var-bien" : "var-mal";
  }
}

function pintarTodo() {
  const claveReal = escenario("R", estado.ejercicio);
  const columnas = {
    actual: magnitudesDe(claveReal),
    presupuesto: magnitudesDe(escenario("P", estado.ejercicio)),
    anterior: magnitudesDe(escenario("R", estado.ejercicio - 1)),
  };
  const rotulos = {
    actual: `Real ${estado.ejercicio}`,
    presupuesto: `Ppto ${estado.ejercicio}`,
    anterior: `Real ${estado.ejercicio - 1}`,
  };

  pintarEjercicios();
  pintarVista();
  pintarAviso(claveReal);
  pintarKpis(columnas.actual);
  pintarEstadoDeResultados(document.getElementById("tabla-pl"), columnas, rotulos);
  pintarMensual(claveReal);
}

async function arrancar() {
  estado.datos = await cargarDatos("cifras.json", "cargando");
  if (!estado.datos) return;

  const ejercicios = [...new Set(estado.datos.pl_oficial.map((f) => f.ejercicio))].sort();
  estado.ejercicio = ejercicios[ejercicios.length - 1];

  pintarPeriodos();
  document.getElementById("periodo").addEventListener("change", (e) => {
    estado.periodo = Number(e.target.value);
    pintarTodo();
  });
  for (const boton of document.querySelectorAll("#vista button")) {
    boton.addEventListener("click", () => {
      estado.vista = boton.dataset.vista;
      pintarTodo();
    });
  }

  document.getElementById("contenido").hidden = false;
  pintarTodo();
  pintarReconciliacion();

  const marca = estado.datos.generado_utc;
  document.getElementById("sello").textContent = marca
    ? `Cifras generadas desde PostgreSQL el ${marca.slice(0, 10)} por scripts/generar_cifras_web.py.`
    : "";
}

arrancar();
