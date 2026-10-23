// Figuras explicativas del sitio. Todas se dibujan aquí en SVG: ninguna es una
// imagen traída de fuera, de modo que heredan el tema claro y oscuro, se leen
// a cualquier tamaño y pesan lo que ocupa su código.
//
// Las que llevan cifras las leen de `cifras.json`, no de constantes escritas a
// mano: un gráfico que afirma algo distinto de la base sería peor que no tener
// gráfico.

import { dosDecimales, lienzo, nodo } from "./comun.js";

const TEXTO = "var(--texto)";

function texto(x, y, contenido, o = {}) {
  return nodo("text", {
    x, y, "font-family": o.familia ?? TEXTO,
    "font-size": o.tamano ?? 12,
    "font-weight": o.peso ?? 400,
    fill: o.color ?? "var(--tinta-media)",
    "text-anchor": o.anclaje ?? "start",
  }, contenido);
}

function caja(svg, { x, y, ancho, alto, titulo, glosa, acento = false, radio = 10 }) {
  svg.appendChild(nodo("rect", {
    x, y, width: ancho, height: alto, rx: radio,
    fill: acento ? "var(--marca-tinte)" : "var(--papel-hundido)",
    stroke: acento ? "var(--marca)" : "var(--linea-fuerte)",
    "stroke-width": acento ? 1.5 : 1,
  }));
  svg.appendChild(texto(x + ancho / 2, y + (glosa ? alto / 2 - 4 : alto / 2 + 5), titulo, {
    tamano: 14, peso: 600, anclaje: "middle",
    color: acento ? "var(--marca)" : "var(--tinta)",
  }));
  if (glosa) {
    svg.appendChild(texto(x + ancho / 2, y + alto / 2 + 16, glosa, {
      tamano: 11.5, anclaje: "middle", color: "var(--tinta-suave)",
    }));
  }
}

function flecha(svg, x1, y1, x2, y2, { discontinua = false } = {}) {
  const atributos = {
    stroke: "var(--linea-fuerte)", "stroke-width": 1.5, fill: "none",
    "stroke-linecap": "round", "stroke-linejoin": "round",
  };
  if (discontinua) atributos["stroke-dasharray"] = "4 4";
  svg.appendChild(nodo("line", { x1, y1, x2, y2, ...atributos }));
  const angulo = Math.atan2(y2 - y1, x2 - x1);
  const punta = 6;
  svg.appendChild(nodo("path", {
    d: `M ${x2 - punta * Math.cos(angulo - 0.45)} ${y2 - punta * Math.sin(angulo - 0.45)} ` +
       `L ${x2} ${y2} ` +
       `L ${x2 - punta * Math.cos(angulo + 0.45)} ${y2 - punta * Math.sin(angulo + 0.45)}`,
    ...atributos, "stroke-dasharray": "none",
  }));
}

/** Las 36 reconciliaciones mensuales contra su banda de tolerancia.
 *
 *  Es el gráfico que sostiene todo el sitio: cada punto es un mes comparado
 *  contra la cifra que la organización ya publica. La banda no es decorativa
 *  -- es la tolerancia derivada del redondeo -- y un punto fuera de ella
 *  detendría la publicación. */
export function reconciliacionPorPeriodo(filas) {
  const ancho = 640, alto = 300;
  const margen = { arriba: 26, derecha: 20, abajo: 46, izquierda: 56 };
  const util = {
    ancho: ancho - margen.izquierda - margen.derecha,
    alto: alto - margen.arriba - margen.abajo,
  };

  const tolerancia = Math.max(...filas.map((f) => f.tolerancia));
  const tope = tolerancia * 1.9;
  const y = (v) => margen.arriba + util.alto / 2 - (v / tope) * (util.alto / 2);
  const paso = util.ancho / filas.length;

  const svg = lienzo(ancho, alto,
    `Diferencia entre el modelo y la maqueta oficial en ${filas.length} periodos, ` +
    "todas dentro de la banda de tolerancia");

  // La banda de tolerancia, primero, para que los puntos queden encima.
  svg.appendChild(nodo("rect", {
    x: margen.izquierda, y: y(tolerancia),
    width: util.ancho, height: y(-tolerancia) - y(tolerancia),
    fill: "var(--favorable)", opacity: 0.1, rx: 4,
  }));
  for (const v of [tolerancia, -tolerancia]) {
    svg.appendChild(nodo("line", {
      x1: margen.izquierda, x2: ancho - margen.derecha, y1: y(v), y2: y(v),
      stroke: "var(--favorable)", "stroke-width": 1, "stroke-dasharray": "5 4", opacity: 0.6,
    }));
  }
  svg.appendChild(nodo("line", {
    x1: margen.izquierda, x2: ancho - margen.derecha, y1: y(0), y2: y(0),
    stroke: "var(--linea-fuerte)", "stroke-width": 1,
  }));

  for (const [v, etiqueta] of [[tolerancia, `+${dosDecimales(tolerancia)}`],
                               [0, "0,00"],
                               [-tolerancia, `−${dosDecimales(tolerancia)}`]]) {
    svg.appendChild(texto(margen.izquierda - 10, y(v) + 4, etiqueta, {
      tamano: 11, anclaje: "end", color: "var(--tinta-suave)",
    }));
  }

  // Un separador por escenario, para que se vea que son tres bloques de doce.
  let anterior = null;
  filas.forEach((fila, i) => {
    const cx = margen.izquierda + paso * (i + 0.5);
    if (anterior !== null && fila.escenario_clave !== anterior) {
      const x = margen.izquierda + paso * i;
      svg.appendChild(nodo("line", {
        x1: x, x2: x, y1: margen.arriba, y2: margen.arriba + util.alto,
        stroke: "var(--linea)", "stroke-width": 1,
      }));
    }
    anterior = fila.escenario_clave;

    svg.appendChild(nodo("line", {
      x1: cx, x2: cx, y1: y(0), y2: y(fila.diferencia),
      stroke: "var(--marca)", "stroke-width": 1, opacity: 0.35,
    }));
    svg.appendChild(nodo("circle", {
      cx, cy: y(fila.diferencia), r: 4,
      fill: "var(--marca)", stroke: "var(--papel-alto)", "stroke-width": 1.5,
    }));
  });

  // Una etiqueta por escenario, centrada bajo su bloque.
  const bloques = new Map();
  filas.forEach((fila, i) => {
    if (!bloques.has(fila.escenario)) bloques.set(fila.escenario, []);
    bloques.get(fila.escenario).push(i);
  });
  for (const [escenario, indices] of bloques) {
    const centro = margen.izquierda + paso * (indices[0] + indices.length / 2);
    svg.appendChild(texto(centro, alto - 22, escenario, {
      tamano: 12, peso: 600, anclaje: "middle", color: "var(--tinta)",
    }));
    svg.appendChild(texto(centro, alto - 7, `${indices.length} periodos`, {
      tamano: 11, anclaje: "middle", color: "var(--tinta-suave)",
    }));
  }
  return svg;
}

/** Las tres capas: quién escribe, quién calcula y quién decide publicar. */
export function tresCapas() {
  const ancho = 840, alto = 250;
  const svg = lienzo(ancho, alto,
    "Tres capas: la IA escribe el proceso, el motor calcula la cifra y el control decide si se publica");
  const anchoCaja = 232, altoCaja = 86, hueco = 72;

  const capas = [
    { titulo: "La IA escribe", glosa: "el proceso", detalle: "código · consultas · pruebas · documentación" },
    { titulo: "El motor calcula", glosa: "la cifra", detalle: "SQL · modelo semántico · aritmética exacta" },
    { titulo: "El control decide", glosa: "si se publica", detalle: "reconciliación · tolerancia derivada", acento: true },
  ];

  capas.forEach((capa, i) => {
    const x = i * (anchoCaja + hueco) + 8;
    caja(svg, { x, y: 56, ancho: anchoCaja, alto: altoCaja, titulo: capa.titulo, glosa: capa.glosa, acento: capa.acento });
    svg.appendChild(texto(x + anchoCaja / 2, 170, capa.detalle, {
      tamano: 11.5, anclaje: "middle", color: "var(--tinta-suave)",
    }));
    if (i < capas.length - 1) {
      flecha(svg, x + anchoCaja + 10, 99, x + anchoCaja + hueco - 10, 99);
    }
  });

  svg.appendChild(texto(8, 28, "Invertir este orden produce un informe fluido que nadie puede defender", {
    tamano: 12.5, color: "var(--tinta-media)",
  }));
  svg.appendChild(nodo("path", {
    d: `M 8 206 L ${ancho - 8} 206`,
    stroke: "var(--linea)", "stroke-width": 1,
  }));
  svg.appendChild(texto(8, 228, "La cifra no la produce nunca quien redacta el proceso.", {
    tamano: 12, color: "var(--tinta-suave)",
  }));
  return svg;
}

/** De la cifra del informe al apunte contable: la cadena de trazabilidad. */
export function trazabilidad() {
  const ancho = 760, alto = 330;
  const svg = lienzo(ancho, alto,
    "Cadena de trazabilidad: del resultado del informe a la linea del P&L, la cuenta, el centro y el apunte contable");

  const niveles = [
    { titulo: "Resultado neto", glosa: "lo que se presenta", ancho: 300 },
    { titulo: "Línea del P&L", glosa: "siete líneas, partición exhaustiva", ancho: 360 },
    { titulo: "Grupo y cuenta contable", glosa: "152 cuentas del plan", ancho: 440 },
    { titulo: "Centro de coste y periodo", glosa: "88 centros × 24 periodos", ancho: 530 },
    { titulo: "Apunte contable", glosa: "428.589 asientos", ancho: 620, acento: true },
  ];

  niveles.forEach((nivel, i) => {
    const x = (ancho - nivel.ancho) / 2;
    const y = i * 62 + 10;
    caja(svg, { x, y, ancho: nivel.ancho, alto: 46, titulo: nivel.titulo, glosa: nivel.glosa, acento: nivel.acento, radio: 8 });
    if (i < niveles.length - 1) flecha(svg, ancho / 2, y + 46, ancho / 2, y + 60);
  });

  svg.appendChild(texto(ancho / 2, alto - 6,
    "Cada nivel suma exactamente el de arriba: no hay un «otros» sin etiquetar",
    { tamano: 12, anclaje: "middle", color: "var(--tinta-suave)" }));
  return svg;
}

/** El criterio para decidir si un reporte merece automatizarse. */
export function criterioAutomatizar() {
  const ancho = 820, alto = 330;
  const svg = lienzo(ancho, alto,
    "Criterio de decision: frecuencia, estabilidad de la definicion y existencia de una cifra de contraste");

  const ejes = [
    { pregunta: "¿Se repite?", si: "Mensual o más", no: "Una vez al año", veredicto: "Sin repetición no hay retorno" },
    { pregunta: "¿Está definido?", si: "La regla es estable", no: "Cambia cada cierre", veredicto: "Automatizar fija la ambigüedad" },
    { pregunta: "¿Hay contra qué cuadrar?", si: "Existe cifra oficial", no: "Nadie la publica", veredicto: "Sin contraste no es un reporte" },
  ];

  ejes.forEach((eje, i) => {
    const y = i * 96 + 14;
    svg.appendChild(texto(8, y + 26, eje.pregunta, { tamano: 14.5, peso: 600, color: "var(--tinta)" }));
    svg.appendChild(texto(8, y + 46, eje.veredicto, { tamano: 11.5, color: "var(--tinta-suave)" }));

    caja(svg, { x: 300, y, ancho: 232, alto: 54, titulo: eje.si, acento: true, radio: 8 });
    caja(svg, { x: 556, y, ancho: 232, alto: 54, titulo: eje.no, radio: 8 });

    if (i < ejes.length - 1) {
      svg.appendChild(nodo("line", {
        x1: 8, x2: ancho - 8, y1: y + 74, y2: y + 74,
        stroke: "var(--linea)", "stroke-width": 1,
      }));
    }
  });

  svg.appendChild(texto(300 + 116, alto - 10, "Automatiza", { tamano: 12, peso: 600, anclaje: "middle", color: "var(--favorable)" }));
  svg.appendChild(texto(556 + 116, alto - 10, "Todavía no", { tamano: 12, peso: 600, anclaje: "middle", color: "var(--tinta-suave)" }));
  return svg;
}

/** Dónde apareció cada fallo y qué lo encontró. */
export function dondeAparecenLosFallos() {
  // Contados sobre la seccion "Lo que salio mal" del repositorio, no
  // estimados: 6 + 4 + 12 + 8 = 30.
  const datos = [
    { capa: "ETL en Python", fallos: 6, quien: "los controles del propio pipeline" },
    { capa: "Capa SQL", fallos: 4, quien: "pruebas que rompen el modelo a propósito" },
    { capa: "Modelo semántico", fallos: 12, quien: "abrir el informe con datos dentro" },
    { capa: "Publicación", fallos: 8, quien: "la auditoría de lo publicable" },
  ];
  const ancho = 760, altoFila = 56;
  const alto = datos.length * altoFila + 30;
  const svg = lienzo(ancho, alto, "Numero de fallos encontrados en cada capa del proyecto y que control los detecto");
  const etiqueta = 210, pie = 240;
  const tope = Math.max(...datos.map((d) => d.fallos));

  datos.forEach((dato, i) => {
    const y = i * altoFila + 12;
    svg.appendChild(texto(0, y + 20, dato.capa, { tamano: 14, peso: 600, color: "var(--tinta)" }));
    svg.appendChild(texto(0, y + 37, dato.quien, { tamano: 11.5, color: "var(--tinta-suave)" }));
    const largo = (dato.fallos / tope) * (ancho - etiqueta - pie);
    svg.appendChild(nodo("rect", {
      x: etiqueta, y: y + 10, width: Math.max(3, largo), height: 20, rx: 4,
      fill: "var(--serie-2)",
    }));
    svg.appendChild(texto(etiqueta + largo + 10, y + 25, `${dato.fallos} fallos`, {
      tamano: 13, peso: 600, color: "var(--tinta)",
    }));
  });

  svg.appendChild(texto(0, alto - 2,
    "Treinta fallos documentados. Casi ninguno lo encontró una revisión: los encontraron los controles.",
    { tamano: 12, color: "var(--tinta-suave)" }));
  return svg;
}

/** Mapa de tareas de finanzas: cuánto las acelera la IA contra cuánto juicio
 *  profesional exigen.
 *
 *  No son datos medidos y la figura lo dice: es un criterio, y su valor está en
 *  que ordena la decisión. Lo que manda es la altura -- cuanto más juicio exige
 *  una tarea, menos se delega, por mucho que la herramienta sepa redactarla con
 *  soltura. */
export function mapaDeTareas() {
  const ancho = 780, alto = 520;
  const margen = { arriba: 46, derecha: 26, abajo: 58, izquierda: 58 };
  const util = {
    ancho: ancho - margen.izquierda - margen.derecha,
    alto: alto - margen.arriba - margen.abajo,
  };
  const px = (v) => margen.izquierda + (v / 100) * util.ancho;
  const py = (v) => margen.arriba + util.alto - (v / 100) * util.alto;

  const svg = lienzo(ancho, alto,
    "Mapa de tareas financieras segun cuanto las acelera la inteligencia artificial y cuanto juicio profesional exigen");

  const cuadrantes = [
    { x: 50, y: 0, etiqueta: "DELEGAR", glosa: "y revisar por muestreo", color: "var(--favorable)" },
    { x: 50, y: 50, etiqueta: "ACELERAR, NUNCA ACEPTAR A CIEGAS", glosa: "", color: "var(--serie-1)" },
    { x: 0, y: 0, etiqueta: "AUTOMATIZAR SIN IA", glosa: "son reglas, no lenguaje", color: "var(--tinta-suave)" },
    { x: 0, y: 50, etiqueta: "NO SE DELEGA", glosa: "aquí responde una persona", color: "var(--desfavorable)" },
  ];
  for (const c of cuadrantes) {
    svg.appendChild(nodo("rect", {
      x: px(c.x), y: py(c.y + 50), width: util.ancho / 2, height: util.alto / 2,
      fill: c.color, opacity: 0.05,
    }));
    svg.appendChild(texto(px(c.x) + 12, py(c.y + 50) + 20, c.etiqueta, {
      tamano: 10.5, peso: 600, color: c.color,
    }));
    if (c.glosa) {
      svg.appendChild(texto(px(c.x) + 12, py(c.y + 50) + 35, c.glosa, {
        tamano: 10.5, color: "var(--tinta-suave)",
      }));
    }
  }

  svg.appendChild(nodo("line", {
    x1: px(50), x2: px(50), y1: margen.arriba, y2: margen.arriba + util.alto,
    stroke: "var(--linea-fuerte)", "stroke-width": 1,
  }));
  svg.appendChild(nodo("line", {
    x1: margen.izquierda, x2: ancho - margen.derecha, y1: py(50), y2: py(50),
    stroke: "var(--linea-fuerte)", "stroke-width": 1,
  }));

  const tareas = [
    { x: 85, y: 10, t: "Consolidar ficheros" },
    { x: 91, y: 22, t: "Dar formato al reporte" },
    { x: 86, y: 34, t: "Escribir fórmulas y consultas" },
    { x: 76, y: 20, t: "Documentar el proceso" },
    { x: 76, y: 62, t: "Redactar el comentario de desviación" },
    { x: 66, y: 76, t: "Buscar anomalías en el detalle" },
    { x: 60, y: 58, t: "Preparar escenarios" },
    { x: 28, y: 88, t: "Definir el perímetro" },
    { x: 17, y: 95, t: "Clasificar una cuenta nueva" },
    { x: 34, y: 70, t: "Decidir si se publica" },
    { x: 15, y: 78, t: "Explicar la cifra al comité" },
    { x: 22, y: 14, t: "Cuadres mecánicos" },
    { x: 34, y: 28, t: "Copiar entre sistemas" },
  ];
  for (const tarea of tareas) {
    const derecha = tarea.x < 55;
    svg.appendChild(nodo("circle", {
      cx: px(tarea.x), cy: py(tarea.y), r: 5,
      fill: "var(--marca)", stroke: "var(--papel-alto)", "stroke-width": 1.5,
    }));
    svg.appendChild(texto(px(tarea.x) + (derecha ? 11 : -11), py(tarea.y) + 4, tarea.t, {
      tamano: 11.5, anclaje: derecha ? "start" : "end", color: "var(--tinta)",
    }));
  }

  svg.appendChild(texto(margen.izquierda, alto - 32, "Poco", { tamano: 11, color: "var(--tinta-suave)" }));
  svg.appendChild(texto(ancho - margen.derecha, alto - 32, "Mucho", { tamano: 11, anclaje: "end", color: "var(--tinta-suave)" }));
  svg.appendChild(texto(ancho / 2, alto - 12, "Cuánto lo acelera la inteligencia artificial", {
    tamano: 12.5, peso: 600, anclaje: "middle", color: "var(--tinta-media)",
  }));
  svg.appendChild(nodo("text", {
    x: 16, y: margen.arriba + util.alto / 2, "font-family": TEXTO, "font-size": 12.5,
    "font-weight": 600, fill: "var(--tinta-media)", "text-anchor": "middle",
    transform: "rotate(-90 16 " + (margen.arriba + util.alto / 2) + ")",
  }, "Cuánto juicio profesional exige"));
  svg.appendChild(texto(margen.izquierda, 24,
    "Criterio propio, no una medición. Lo que decide es la altura: cuanto más arriba, menos se delega.",
    { tamano: 11.5, color: "var(--tinta-suave)" }));
  return svg;
}

/** El recorrido del dato, de la hoja de cálculo al informe publicado. */
export function recorridoDelDato() {
  const etapas = [
    { t: "Hoja de cálculo", g: "el origen", d: "treinta hojas" },
    { t: "Extracción", g: "automática", d: "sin copiar y pegar" },
    { t: "Base de datos", g: "con reglas", d: "rechaza lo mal formado" },
    { t: "Modelo de análisis", g: "y sus medidas", d: "una definición por línea" },
    { t: "Informe", g: "y esta web", d: "publicado y auditable" },
  ];
  const ancho = 900, alto = 196;
  const svg = lienzo(ancho, alto, "Recorrido del dato: hoja de calculo, extraccion, base de datos, modelo e informe");
  const anchoCaja = 150;
  const hueco = (ancho - etapas.length * anchoCaja) / (etapas.length - 1);

  etapas.forEach((etapa, i) => {
    const x = i * (anchoCaja + hueco);
    caja(svg, { x, y: 46, ancho: anchoCaja, alto: 76, titulo: etapa.t, glosa: etapa.g, acento: i === etapas.length - 1 });
    svg.appendChild(texto(x + anchoCaja / 2, 142, etapa.d, {
      tamano: 11, anclaje: "middle", color: "var(--tinta-suave)",
    }));
    if (i < etapas.length - 1) flecha(svg, x + anchoCaja + 6, 84, x + anchoCaja + hueco - 6, 84);
  });
  svg.appendChild(texto(0, 24, "Cada paso tiene que demostrar algo antes de que el siguiente se apoye en él", {
    tamano: 12.5, color: "var(--tinta-media)",
  }));
  svg.appendChild(texto(0, 180, "Si una comprobación no cuadra, el proceso se detiene y dice dónde", {
    tamano: 11.5, color: "var(--tinta-suave)",
  }));
  return svg;
}

/** El cierre antes y después de automatizar la preparación del dato. */
export function antesYDespues() {
  const ancho = 800, alto = 300;
  const svg = lienzo(ancho, alto, "Reparto del trabajo de un cierre antes y despues de automatizar la preparacion del dato");

  const bloques = [
    { t: "Reunir y consolidar", antes: 40, despues: 5 },
    { t: "Cuadrar y corregir", antes: 30, despues: 10 },
    { t: "Dar formato y presentar", antes: 18, despues: 5 },
    { t: "Analizar y explicar", antes: 12, despues: 80 },
  ];
  const colores = ["var(--tinta-suave)", "var(--serie-2)", "var(--linea-fuerte)", "var(--favorable)"];
  const anchoBarra = 92;
  const x1 = 250;
  const x2 = 480;
  const altoTotal = 186;
  const arriba = 70;

  const columnas = [["Antes", "antes", x1], ["Después", "despues", x2]];
  for (const [rotulo, clave, x] of columnas) {
    svg.appendChild(texto(x + anchoBarra / 2, arriba - 14, rotulo, {
      tamano: 13, peso: 600, anclaje: "middle", color: "var(--tinta)",
    }));
    let y = arriba;
    bloques.forEach((bloque, i) => {
      const altura = (bloque[clave] / 100) * altoTotal;
      svg.appendChild(nodo("rect", {
        x, y, width: anchoBarra, height: Math.max(2, altura - 2), rx: 3, fill: colores[i],
      }));
      if (altura > 22) {
        svg.appendChild(texto(x + anchoBarra / 2, y + altura / 2 + 4, bloque[clave] + "%", {
          tamano: 11.5, peso: 600, anclaje: "middle",
          color: (i === 1 || i === 3) ? "#fff" : "var(--tinta)",
        }));
      }
      y += altura;
    });
  }

  bloques.forEach((bloque, i) => {
    const y = arriba + 16 + i * 26;
    svg.appendChild(nodo("rect", { x: 0, y: y - 9, width: 11, height: 11, rx: 3, fill: colores[i] }));
    svg.appendChild(texto(18, y, bloque.t, { tamano: 12.5, color: "var(--tinta)" }));
  });

  flecha(svg, x1 + anchoBarra + 16, arriba + altoTotal / 2, x2 - 16, arriba + altoTotal / 2);
  svg.appendChild(texto(0, 24, "El trabajo no desaparece: se desplaza", { tamano: 14.5, peso: 600, color: "var(--tinta)" }));
  svg.appendChild(texto(0, 44, "Reparto ilustrativo del esfuerzo de un cierre mensual, no una medición.", {
    tamano: 11.5, color: "var(--tinta-suave)",
  }));
  svg.appendChild(texto(x2 + anchoBarra + 22, arriba + 44, "Lo que crece", { tamano: 12.5, peso: 600, color: "var(--favorable)" }));
  svg.appendChild(texto(x2 + anchoBarra + 22, arriba + 62, "es justo la parte", { tamano: 11.5, color: "var(--tinta-suave)" }));
  svg.appendChild(texto(x2 + anchoBarra + 22, arriba + 78, "que nadie puede", { tamano: 11.5, color: "var(--tinta-suave)" }));
  svg.appendChild(texto(x2 + anchoBarra + 22, arriba + 94, "delegar", { tamano: 11.5, color: "var(--tinta-suave)" }));
  return svg;
}

/** Qué contiene cada tabla del modelo, para quien entra sin contexto. */
export function queHayEnLasTablas() {
  const ancho = 820, alto = 236;
  const svg = lienzo(ancho, alto, "Las tablas del modelo agrupadas en resultado, prueba y detalle");

  const grupos = [
    { t: "El resultado", g: "lo que se presenta", tablas: ["Escenarios", "P&L oficial", "Detalle mensual"] },
    { t: "La prueba", g: "lo que demuestra que cuadra", tablas: ["Reconciliación", "Ejecución presupuestaria"] },
    { t: "El detalle", g: "dónde se consume el coste", tablas: ["Coste por grupo", "Centros de coste"] },
  ];
  const anchoCaja = 252;
  const hueco = (ancho - grupos.length * anchoCaja) / (grupos.length - 1);

  grupos.forEach((grupo, i) => {
    const x = i * (anchoCaja + hueco);
    svg.appendChild(nodo("rect", {
      x, y: 10, width: anchoCaja, height: 192, rx: 12,
      fill: "var(--papel-hundido)", stroke: "var(--linea-fuerte)", "stroke-width": 1,
    }));
    svg.appendChild(texto(x + 18, 38, grupo.t, { tamano: 15, peso: 600, color: "var(--tinta)" }));
    svg.appendChild(texto(x + 18, 56, grupo.g, { tamano: 11.5, color: "var(--tinta-suave)" }));
    grupo.tablas.forEach((tabla, j) => {
      const y = 78 + j * 38;
      svg.appendChild(nodo("rect", {
        x: x + 18, y, width: anchoCaja - 36, height: 30, rx: 7,
        fill: "var(--papel-alto)", stroke: "var(--marca)", "stroke-width": 1,
      }));
      svg.appendChild(texto(x + anchoCaja / 2, y + 19, tabla, {
        tamano: 12.5, peso: 600, anclaje: "middle", color: "var(--marca)",
      }));
    });
  });
  svg.appendChild(texto(0, alto - 4, "Siete tablas. Cada pestaña de abajo abre una de ellas.", {
    tamano: 12, color: "var(--tinta-suave)",
  }));
  return svg;
}

/** Las cuatro formas de equivocarse al automatizar un reporte financiero.
 *
 *  Es la síntesis de los treinta fallos del caso, pero vale igual para
 *  cualquier proyecto: ninguna de las cuatro es un fallo de la herramienta. */
export function cuatroPatrones() {
  const patrones = [
    {
      t: "El vacío tratado como cero",
      sintoma: "Variaciones contra años que no existen",
      defensa: "Que «no aplica» y «vale cero» se vean distintos",
    },
    {
      t: "El perímetro no comparable",
      sintoma: "Diez meses contra doce de presupuesto",
      defensa: "Recortar siempre al menor de los dos lados",
    },
    {
      t: "La afirmación sin medir",
      sintoma: "«Aquí no se pierde precisión»",
      defensa: "Una comprobación que pueda desmentirla",
    },
    {
      t: "El control en el sitio equivocado",
      sintoma: "Busca nombres y lo filtrado son cifras",
      defensa: "Romperlo a propósito y ver si salta",
    },
  ];

  const ancho = 840, alto = 280;
  const svg = lienzo(ancho, alto,
    "Las cuatro formas de equivocarse al automatizar un reporte financiero, con su sintoma y su defensa");
  const anchoCaja = (ancho - 3 * 16) / 4;

  patrones.forEach((patron, i) => {
    const x = i * (anchoCaja + 16);
    svg.appendChild(nodo("rect", {
      x, y: 36, width: anchoCaja, height: 206, rx: 12,
      fill: "var(--papel-hundido)", stroke: "var(--linea-fuerte)", "stroke-width": 1,
    }));
    svg.appendChild(nodo("circle", {
      cx: x + 26, cy: 64, r: 15, fill: "var(--desfavorable)", opacity: 0.14,
    }));
    svg.appendChild(texto(x + 26, 69, String(i + 1), {
      tamano: 14, peso: 600, anclaje: "middle", color: "var(--desfavorable)",
    }));

    // El título se parte en dos líneas para que quepa en la tarjeta.
    const palabras = patron.t.split(" ");
    const mitad = Math.ceil(palabras.length / 2);
    [palabras.slice(0, mitad).join(" "), palabras.slice(mitad).join(" ")].forEach((linea, j) => {
      svg.appendChild(texto(x + 16, 104 + j * 18, linea, {
        tamano: 13.5, peso: 600, color: "var(--tinta)",
      }));
    });

    svg.appendChild(texto(x + 16, 158, "SE VE COMO", { tamano: 9.5, peso: 600, color: "var(--tinta-suave)" }));
    partir(svg, patron.sintoma, x + 16, 174, anchoCaja - 32, "var(--tinta-media)");

    svg.appendChild(texto(x + 16, 206, "SE EVITA ASÍ", { tamano: 9.5, peso: 600, color: "var(--favorable)" }));
    partir(svg, patron.defensa, x + 16, 222, anchoCaja - 32, "var(--tinta-media)");
  });

  svg.appendChild(texto(0, 22, "Ninguna es un fallo de la herramienta: las cuatro son decisiones humanas que la herramienta ejecuta muy deprisa", {
    tamano: 12, color: "var(--tinta-suave)",
  }));
  svg.appendChild(texto(0, alto - 4, "Síntesis de los treinta fallos documentados en este proyecto.", {
    tamano: 11.5, color: "var(--tinta-suave)",
  }));
  return svg;
}

/** Parte un texto en líneas que quepan en el ancho dado. */
function partir(svg, contenido, x, y, anchoMaximo, color) {
  const porLinea = Math.floor(anchoMaximo / 5.9);
  const palabras = contenido.split(" ");
  const lineas = [];
  let actual = "";
  for (const palabra of palabras) {
    if ((actual + " " + palabra).trim().length > porLinea) {
      lineas.push(actual.trim());
      actual = palabra;
    } else {
      actual += " " + palabra;
    }
  }
  if (actual.trim()) lineas.push(actual.trim());
  lineas.slice(0, 3).forEach((linea, i) => {
    svg.appendChild(texto(x, y + i * 14, linea, { tamano: 11.5, color }));
  });
}
