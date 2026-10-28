/* Ilustraciones originales para las portadas que tienen texto y espacio
   libre a un lado. Se dibujan en SVG para que sigan nítidas y funcionen sin
   servicios externos, también al abrir la web desde un archivo local. */
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const temas = {
    "analitica-excepciones.html": { tipo: "ranking", grupo: "DEFENDER LAS CIFRAS", titulo: "Alertas priorizadas para revisión", pie: "El análisis señala dónde mirar primero; la evidencia y el criterio profesional resuelven cada caso." },
    "analisis-financiero-ia.html": { tipo: "variacion", grupo: "IA PARA FINANZAS", titulo: "De la variación a la explicación", pie: "La IA puede preparar una hipótesis; el equipo financiero valida el dato y la causa." },
    "calidad-datos-financieros.html": { tipo: "controles", grupo: "DEFENDER LAS CIFRAS", titulo: "Controles antes del cuadre", pie: "Completitud, duplicados, clasificación y periodo se comprueban antes de publicar." },
    "caso.html": { tipo: "flujo", grupo: "CASO APLICADO", titulo: "Del archivo al informe con controles", pie: "El proceso transforma los datos y comprueba el resultado antes de publicarlo." },
    "corregir-error-reporte-publicado.html": { tipo: "incidente", grupo: "GESTIÓN DE INCIDENCIAS", titulo: "Contener, corregir y comunicar", pie: "Una corrección también necesita versión, responsables y confirmación de recepción." },
    "datos.html": { tipo: "modelo", grupo: "MODELO DE DATOS", titulo: "Hechos conectados con dimensiones", pie: "El grano de cada tabla determina cómo se interpretan y agregan los importes." },
    "defender-las-cifras.html": { tipo: "traza", grupo: "DEFENDER LAS CIFRAS", titulo: "Una cifra que se puede reconstruir", pie: "Cada indicador conecta la fuente, la regla de cálculo y la evidencia." },
    "depreciacion-ia.html": { tipo: "depreciacion", grupo: "IA PARA FINANZAS", titulo: "La vida del activo, periodo a periodo", pie: "La IA puede asistir con datos y borradores; el método contable aprobado gobierna el cálculo." },
    "explorador.html": { tipo: "tabla", grupo: "EXPLORADOR DE DATOS", titulo: "Detalle accesible y filtrable", pie: "Las tablas permiten inspeccionar las cifras sin perder su contexto." },
    "fabric-power-bi.html": { tipo: "capas", grupo: "ARQUITECTURA DE DATOS", titulo: "De la plataforma al informe", pie: "Fabric amplía la preparación de datos; Power BI presenta métricas con un modelo compartido." },
    "flujo-caja-ia.html": { tipo: "caja", grupo: "TESORERÍA · ESCENARIOS", titulo: "Caja observada y escenarios", pie: "La estimación ayuda a anticipar necesidades; los supuestos deben seguir visibles." },
    "ia-en-el-cierre.html": { tipo: "variacion", grupo: "IA PARA FINANZAS", titulo: "Análisis, revisión y decisión", pie: "La IA acelera tareas del cierre cuando trabaja con datos delimitados y controles claros." },
    "mcp-power-bi-agentes.html": { tipo: "mcp", grupo: "AGENTES · MCP · POWER BI", titulo: "Un agente conectado con permisos", pie: "MCP ofrece herramientas; el proyecto, los permisos y la revisión determinan qué puede hacer." },
    "medir-automatizacion-financiera.html": { tipo: "medicion", grupo: "MEDICIÓN OPERATIVA", titulo: "Del piloto al seguimiento", pie: "El antes y el después se comparan con métricas, responsable y alertas de operación." },
    "metodo-defender-cifras.html": { tipo: "traza", grupo: "MÉTODO DE CONTROL", titulo: "Una cadena de evidencia", pie: "Cada afirmación financiera necesita una fuente y un control que pueda repetirse." },
    "metodo-ia-en-cierre.html": { tipo: "proceso", grupo: "IA EN EL CIERRE", titulo: "Asistencia con revisión humana", pie: "La IA prepara, las reglas calculan y Finanzas decide qué se publica." },
    "metodo-que-automatizar.html": { tipo: "proceso", grupo: "MÉTODO DE AUTOMATIZACIÓN", titulo: "Un flujo con puertas de control", pie: "Cada etapa demuestra que está lista antes de pasar a la siguiente." },
    "por-que-power-bi-empresas.html": { tipo: "adopcion", grupo: "ADOPCIÓN EMPRESARIAL", titulo: "Un ecosistema que conecta", pie: "La adopción depende de integración, modelos compartidos, distribución y gobierno." },
    "postmortem-errores-reporte-financiero.html": { tipo: "incidente", grupo: "ANÁLISIS DE INCIDENTES", titulo: "Del fallo a una acción preventiva", pie: "El postmortem reconstruye el alcance y convierte la causa en controles verificables." },
    "power-bi-vs-ia.html": { tipo: "comparacion", grupo: "BI E INTELIGENCIA ARTIFICIAL", titulo: "Capacidades que se complementan", pie: "La IA asiste en la creación y consulta; el modelo y el control sostienen el informe." },
    "powerbi.html": { tipo: "flujo", grupo: "POWER BI · DATOS · EMPRESA", titulo: "Del dato al informe confiable", pie: "Fuentes, modelo semántico y visualización: cada capa cumple una función distinta." },
    "preparar-proceso-automatizacion.html": { tipo: "proceso", grupo: "PREPARAR LA AUTOMATIZACIÓN", titulo: "Reglas antes que herramientas", pie: "Mapear entradas, decisiones y excepciones permite automatizar lo que sí está definido." },
    "priorizar-automatizacion-financiera.html": { tipo: "matriz", grupo: "PRIORIZACIÓN", titulo: "Valor, volumen y riesgo", pie: "Una matriz de decisión ayuda a comparar oportunidades; no sustituye el criterio del equipo." },
    "proceso.html": { tipo: "proceso", grupo: "PROCESO AUTOMATIZADO", titulo: "Pasos reproducibles y verificables", pie: "La transformación avanza solo cuando las reglas y las comprobaciones se cumplen." },
    "que-automatizar.html": { tipo: "matriz", grupo: "QUÉ AUTOMATIZAR", titulo: "Elegir el proceso con mejor encaje", pie: "Frecuencia, reglas claras y coste del error orientan el orden de trabajo." },
    "que-puede-salir-mal.html": { tipo: "riesgo", grupo: "RIESGO Y CONTROL", titulo: "Puntos de control del flujo", pie: "Los controles detienen errores antes de que lleguen a una cifra publicada." },
    "refresh-no-es-reporte-listo.html": { tipo: "refresh", grupo: "ACTUALIZACIÓN Y VIGENCIA", titulo: "Estado técnico y corte financiero", pie: "Una actualización exitosa no confirma por sí sola la cobertura ni la vigencia del informe." },
    "revisar-finanzas-antes-publicar.html": { tipo: "controles", grupo: "REVISIÓN FINANCIERA", titulo: "Cuatro preguntas antes de publicar", pie: "Origen, clasificación, medición y presentación deben contar la misma historia." },
    "trazabilidad-cifras-financieras.html": { tipo: "traza", grupo: "EVIDENCIA Y TRAZABILIDAD", titulo: "Del asiento al indicador", pie: "La ruta permite volver del KPI a la regla, la transformación y el soporte original." },
  };

  function svgNodo(nombre, attrs = {}, contenido = "") {
    const el = document.createElementNS(NS, nombre);
    for (const [clave, valor] of Object.entries(attrs)) el.setAttribute(clave, valor);
    if (contenido) el.textContent = contenido;
    return el;
  }

  function agregar(svg, nombre, attrs, contenido) {
    const el = svgNodo(nombre, attrs, contenido);
    svg.appendChild(el);
    return el;
  }

  function texto(svg, x, y, valor, opciones = {}) {
    return agregar(svg, "text", {
      x, y, fill: opciones.color || "var(--tinta-media)",
      "font-family": "var(--texto)", "font-size": opciones.tamano || 12,
      "font-weight": opciones.peso || 500, "text-anchor": opciones.ancla || "middle",
    }, valor);
  }

  function linea(svg, x1, y1, x2, y2, color = "var(--grafico-eje)", ancho = 2, extra = {}) {
    return agregar(svg, "line", { x1, y1, x2, y2, stroke: color, "stroke-width": ancho, ...extra });
  }

  function baseSvg(config, fichero) {
    const svg = svgNodo("svg", {
      class: "portada-svg", viewBox: "0 0 460 230", role: "img",
      "aria-labelledby": `titulo-${fichero} descripcion-${fichero}`,
      preserveAspectRatio: "xMidYMid meet",
    });
    svg.append(
      svgNodo("title", { id: `titulo-${fichero}` }, config.titulo),
      svgNodo("desc", { id: `descripcion-${fichero}` }, config.pie),
    );
    return svg;
  }

  function nodoTarjeta(svg, x, titulo, subtitulo, color = "var(--grafico-superficie)") {
    agregar(svg, "rect", { x, y: 74, width: 112, height: 82, rx: 7, fill: color, stroke: "var(--grafico-rejilla)" });
    agregar(svg, "circle", { cx: x + 56, cy: 96, r: 5, fill: "var(--grafico-serie-4)" });
    texto(svg, x + 56, 124, titulo, { tamano: 12, peso: 650, color: "var(--tinta)" });
    texto(svg, x + 56, 143, subtitulo, { tamano: 10.5 });
  }

  function dibujarFlujo(svg, etiquetas = ["Origen", "Modelo", "Informe"]) {
    linea(svg, 132, 115, 174, 115, "var(--grafico-azul-marca)", 2.5);
    linea(svg, 286, 115, 328, 115, "var(--grafico-cian)", 2.5);
    nodoTarjeta(svg, 20, etiquetas[0], "dato validado");
    nodoTarjeta(svg, 174, etiquetas[1], "regla común", "var(--grafico-serie-2-fondo)");
    nodoTarjeta(svg, 328, etiquetas[2], "lectura clara");
    texto(svg, 230, 194, "RUTA DEL DATO", { tamano: 10, peso: 650, color: "var(--tinta-suave)" });
  }

  function dibujarCapas(svg) {
    const filas = [
      ["Consumo", "informes · decisiones", "var(--grafico-serie-2-fondo)"],
      ["Modelo semántico", "métricas · relaciones", "var(--grafico-superficie)"],
      ["Plataforma de datos", "preparación · gobierno", "var(--grafico-serie-1-fondo)"],
      ["Fuentes", "ERP · archivos · servicios", "var(--grafico-superficie)"],
    ];
    filas.forEach(([a, b, fill], i) => {
      const y = 28 + i * 45;
      agregar(svg, "rect", { x: 68, y, width: 324, height: 34, rx: 5, fill, stroke: "var(--grafico-rejilla)" });
      texto(svg, 150, y + 22, a, { ancla: "start", tamano: 12, peso: 650, color: "var(--tinta)" });
      texto(svg, 370, y + 22, b, { ancla: "end", tamano: 10.5 });
    });
  }

  function dibujarModelo(svg) {
    const dims = [[80, 43, "Periodo"], [380, 43, "Cuenta"], [80, 166, "Centro"], [380, 166, "Escenario"]];
    dims.forEach(([x, y, nombre]) => {
      const cx = x < 200 ? x + 48 : x - 48;
      const cy = y < 100 ? y + 31 : y - 1;
      linea(svg, cx, cy, 230, 115, "var(--grafico-eje)", 1.6);
      agregar(svg, "rect", { x: x - 42, y, width: 84, height: 40, rx: 5, fill: "var(--grafico-superficie)", stroke: "var(--grafico-rejilla)" });
      texto(svg, x, y + 25, nombre, { tamano: 10.5, peso: 600 });
    });
    agregar(svg, "rect", { x: 174, y: 82, width: 112, height: 66, rx: 7, fill: "var(--grafico-azul-fondo)", stroke: "var(--grafico-azul-marca)" });
    texto(svg, 230, 108, "Hechos", { tamano: 13, peso: 700, color: "var(--grafico-azul-marca)" });
    texto(svg, 230, 128, "apunte · mes", { tamano: 9.5 });
  }

  function dibujarComparacion(svg) {
    agregar(svg, "rect", { x: 25, y: 42, width: 158, height: 112, rx: 8, fill: "var(--grafico-superficie)", stroke: "var(--grafico-rejilla)" });
    agregar(svg, "rect", { x: 277, y: 42, width: 158, height: 112, rx: 8, fill: "var(--grafico-serie-2-fondo)", stroke: "var(--grafico-serie-2)" });
    texto(svg, 104, 72, "Power BI", { tamano: 14, peso: 700, color: "var(--tinta)" });
    texto(svg, 356, 72, "IA", { tamano: 14, peso: 700, color: "var(--grafico-serie-2)" });
    [0, 1, 2, 3].forEach(i => agregar(svg, "rect", { x: 50 + i * 27, y: 108 - (i % 2) * 10, width: 15, height: 25 + (i % 2) * 10, rx: 2, fill: i === 3 ? "var(--grafico-serie-1-claro)" : "var(--grafico-serie-1)" }));
    agregar(svg, "circle", { cx: 327, cy: 113, r: 22, fill: "none", stroke: "var(--grafico-serie-2)", "stroke-width": 3 });
    texto(svg, 327, 118, "IA", { tamano: 13, peso: 700, color: "var(--grafico-serie-2)" });
    linea(svg, 184, 98, 270, 98, "var(--grafico-serie-4)", 2.5);
    agregar(svg, "circle", { cx: 230, cy: 98, r: 23, fill: "var(--papel)", stroke: "var(--grafico-eje)" });
    texto(svg, 230, 102, "revisión", { tamano: 10, peso: 650 });
    texto(svg, 230, 192, "MODELO + ASISTENCIA + CRITERIO", { tamano: 10, peso: 650, color: "var(--tinta-suave)" });
  }

  function dibujarMcp(svg) {
    nodoTarjeta(svg, 18, "Agente", "consulta guiada");
    nodoTarjeta(svg, 174, "MCP", "herramientas", "var(--grafico-serie-2-fondo)");
    nodoTarjeta(svg, 330, "Proyecto", "acceso limitado");
    linea(svg, 130, 115, 174, 115, "var(--grafico-serie-1-claro)", 2.5);
    linea(svg, 286, 115, 330, 115, "var(--grafico-cian)", 2.5);
    agregar(svg, "rect", { x: 373, y: 81, width: 18, height: 14, rx: 3, fill: "none", stroke: "var(--tinta-media)", "stroke-width": 1.6 });
    agregar(svg, "path", { d: "M377 81v-4a5 5 0 0 1 10 0v4", fill: "none", stroke: "var(--tinta-media)", "stroke-width": 1.6 });
    texto(svg, 230, 194, "PERMISOS · ENTORNO · REVISIÓN", { tamano: 10, peso: 650, color: "var(--tinta-suave)" });
  }

  function dibujarMatriz(svg) {
    linea(svg, 92, 184, 392, 184, "var(--grafico-eje)", 1.5);
    linea(svg, 92, 184, 92, 34, "var(--grafico-eje)", 1.5);
    linea(svg, 242, 36, 242, 184, "var(--grafico-rejilla)", 1);
    linea(svg, 93, 110, 392, 110, "var(--grafico-rejilla)", 1);
    agregar(svg, "rect", { x: 95, y: 38, width: 145, height: 70, fill: "var(--grafico-azul-fondo)", opacity: ".75" });
    agregar(svg, "circle", { cx: 310, cy: 75, r: 13, fill: "var(--grafico-serie-1)", opacity: ".88" });
    agregar(svg, "circle", { cx: 278, cy: 132, r: 9, fill: "var(--grafico-serie-4)" });
    agregar(svg, "circle", { cx: 164, cy: 145, r: 7, fill: "var(--grafico-eje)" });
    texto(svg, 242, 211, "ESFUERZO →", { tamano: 10, peso: 650, color: "var(--tinta-suave)" });
    const vertical = texto(svg, 45, 108, "VALOR", { tamano: 10, peso: 650, color: "var(--tinta-suave)" });
    vertical.setAttribute("transform", "rotate(-90 45 108)");
    texto(svg, 164, 57, "PRIMERA OPCIÓN", { tamano: 9.5, peso: 650, color: "var(--grafico-serie-1)" });
  }

  function dibujarControles(svg) {
    const filas = ["Origen", "Clasificación", "Medición", "Presentación"];
    filas.forEach((nombre, i) => {
      const y = 32 + i * 43;
      agregar(svg, "rect", { x: 44, y, width: 372, height: 32, rx: 4, fill: i % 2 ? "var(--papel)" : "var(--grafico-superficie)", stroke: "var(--grafico-rejilla)" });
      texto(svg, 66, y + 21, nombre, { ancla: "start", tamano: 11.5, peso: 600 });
      linea(svg, 190, y + 8, 190, y + 25, "var(--grafico-rejilla)", 1);
      texto(svg, 224, y + 21, ["fuente", "periodo", "supuesto", "coherencia"][i], { ancla: "start", tamano: 10.5 });
      agregar(svg, "circle", { cx: 386, cy: y + 16, r: 6, fill: i === 2 ? "var(--grafico-serie-2)" : "var(--grafico-serie-3)" });
    });
  }

  function dibujarTraza(svg) {
    const items = [[52, "Fuente"], [168, "Regla"], [284, "Indicador"], [400, "Evidencia"]];
    items.forEach(([x, nombre], i) => {
      if (i < items.length - 1) linea(svg, x + 14, 104, x + 102, 104, i === 0 ? "var(--grafico-azul-marca)" : i === 1 ? "var(--grafico-cian)" : "var(--grafico-eje)", 2);
      agregar(svg, "circle", { cx: x, cy: 104, r: 20, fill: i === 2 ? "var(--grafico-serie-2-fondo)" : "var(--grafico-superficie)", stroke: i === 2 ? "var(--grafico-serie-2)" : "var(--grafico-eje)", "stroke-width": 1.5 });
      texto(svg, x, 151, nombre, { tamano: 11, peso: 600 });
      texto(svg, x, 171, ["ERP · libro", "cálculo", "KPI", "asiento"][i], { tamano: 9.5, color: "var(--tinta-suave)" });
    });
    texto(svg, 230, 211, "SE PUEDE RECORRER EN AMBOS SENTIDOS", { tamano: 9.5, peso: 650, color: "var(--tinta-suave)" });
  }

  function dibujarTabla(svg) {
    const x0 = 38, y0 = 42, widths = [154, 73, 73, 73];
    let x = x0;
    ["Control", "Filas", "Periodo", "Estado"].forEach((v, i) => {
      agregar(svg, "rect", { x, y: y0, width: widths[i], height: 31, fill: "var(--grafico-superficie)", stroke: "var(--grafico-rejilla)" });
      texto(svg, x + widths[i] / 2, y0 + 20, v, { tamano: 10, peso: 650 }); x += widths[i];
    });
    ["Completitud", "Duplicados", "Clasificación", "Fecha de corte"].forEach((v, row) => {
      let xx = x0; const yy = y0 + 31 + row * 32;
      [v, "OK", row === 2 ? "Revisar" : "OK", row === 2 ? "Abierto" : "OK"].forEach((celda, col) => {
        agregar(svg, "rect", { x: xx, y: yy, width: widths[col], height: 32, fill: row % 2 ? "var(--papel)" : "var(--grafico-superficie)", stroke: "var(--grafico-rejilla)" });
        texto(svg, xx + 9, yy + 20, celda, { ancla: col ? "middle" : "start", tamano: 9.5, peso: col === 3 && row === 2 ? 650 : 500, color: col === 3 && row === 2 ? "var(--grafico-serie-2)" : "var(--tinta-media)" });
        xx += widths[col];
      });
    });
  }

  function dibujarRanking(svg) {
    const nombres = ["Variación", "Duplicado", "Corte", "Cuenta"];
    const largos = [240, 180, 128, 86];
    nombres.forEach((v, i) => {
      const y = 43 + i * 39;
      texto(svg, 40, y + 13, v, { ancla: "start", tamano: 10.5, peso: 550 });
      agregar(svg, "rect", { x: 133, y, width: 270, height: 15, rx: 3, fill: "var(--grafico-superficie)" });
      agregar(svg, "rect", { x: 133, y, width: largos[i], height: 15, rx: 3, fill: i === 0 ? "var(--grafico-serie-2)" : "var(--grafico-serie-1)" });
      agregar(svg, "circle", { cx: 418, cy: y + 7.5, r: 5, fill: i === 0 ? "var(--grafico-serie-2)" : "var(--grafico-eje)" });
    });
    texto(svg, 230, 211, "ORDEN DE REVISIÓN · NO ES UN VEREDICTO", { tamano: 9.5, peso: 650, color: "var(--tinta-suave)" });
  }

  function dibujarLineas(svg, caja = false) {
    [48, 88, 128, 168].forEach(y => linea(svg, 48, y, 414, y, "var(--grafico-rejilla)", 1));
    [70, 150, 230, 310, 390].forEach(x => linea(svg, x, 35, x, 185, "var(--grafico-rejilla)", 1));
    linea(svg, 48, 185, 414, 185, "var(--grafico-eje)", 1.5);
    if (caja) {
      agregar(svg, "path", { d: "M55 78 C110 67 145 102 195 95 S275 83 310 111", fill: "none", stroke: "var(--grafico-serie-1)", "stroke-width": 3, "stroke-linecap": "round" });
      agregar(svg, "path", { d: "M310 111 C345 132 375 99 408 144", fill: "none", stroke: "var(--grafico-serie-2)", "stroke-width": 3, "stroke-dasharray": "7 6", "stroke-linecap": "round" });
      texto(svg, 118, 205, "OBSERVADO", { tamano: 9.5, peso: 650, color: "var(--grafico-serie-1)" });
      texto(svg, 358, 205, "ESCENARIO", { tamano: 9.5, peso: 650, color: "var(--grafico-serie-2)" });
    } else {
      agregar(svg, "path", { d: "M55 151 L105 133 L155 142 L205 92 L255 109 L305 70 L355 94 L408 52", fill: "none", stroke: "var(--grafico-azul-marca)", "stroke-width": 3, "stroke-linejoin": "round", "stroke-linecap": "round" });
      agregar(svg, "circle", { cx: 305, cy: 70, r: 6, fill: "var(--grafico-serie-4)", stroke: "var(--papel)", "stroke-width": 2 });
      texto(svg, 230, 210, "VARIACIÓN IDENTIFICADA · EXPLICACIÓN POR VALIDAR", { tamano: 9.5, peso: 650, color: "var(--tinta-suave)" });
    }
  }

  function dibujarDepreciacion(svg) {
    const altos = [104, 88, 72, 55, 40, 28];
    altos.forEach((alto, i) => {
      const x = 58 + i * 57;
      agregar(svg, "rect", { x, y: 177 - alto, width: 32, height: alto, rx: 3, fill: i < 3 ? "var(--grafico-serie-1)" : "var(--grafico-serie-1-claro)", opacity: i < 3 ? ".92" : ".8" });
      texto(svg, x + 16, 194, `P${i + 1}`, { tamano: 9.5, color: "var(--tinta-suave)" });
    });
    linea(svg, 42, 178, 414, 178, "var(--grafico-eje)", 1.5);
    texto(svg, 230, 220, "VALOR NETO CONTABLE · ESQUEMA", { tamano: 9.5, peso: 650, color: "var(--tinta-suave)" });
  }

  function dibujarIncidente(svg) {
    const items = [[65, "Detectar"], [175, "Contener"], [285, "Corregir"], [395, "Confirmar"]];
    linea(svg, 65, 106, 395, 106, "var(--grafico-eje)", 2);
    items.forEach(([x, nombre], i) => {
      agregar(svg, "circle", { cx: x, cy: 106, r: 18, fill: i === 1 ? "var(--grafico-serie-2-fondo)" : "var(--grafico-superficie)", stroke: i === 1 ? "var(--grafico-serie-2)" : "var(--grafico-serie-1)", "stroke-width": 2 });
      texto(svg, x, 111, `${i + 1}`, { tamano: 11, peso: 700, color: i === 1 ? "var(--grafico-serie-2)" : "var(--grafico-serie-1)" });
      texto(svg, x, 151, nombre, { tamano: 10.5, peso: 600 });
    });
    texto(svg, 230, 196, "VERSIÓN · ALCANCE · RESPONSABLE · CIERRE", { tamano: 9.5, peso: 650, color: "var(--tinta-suave)" });
  }

  function dibujarAdopcion(svg) {
    const nodos = [[92, 84, "ERP"], [230, 55, "Microsoft 365"], [368, 84, "Power BI"], [230, 154, "Equipo"]];
    [[92, 84, 230, 55], [230, 55, 368, 84], [92, 84, 230, 154], [368, 84, 230, 154]].forEach((v, i) => linea(svg, ...v, i === 1 ? "var(--grafico-cian)" : "var(--grafico-eje)", i === 1 ? 2.2 : 1.7));
    nodos.forEach(([x, y, label], i) => {
      agregar(svg, "circle", { cx: x, cy: y, r: i === 1 || i === 2 ? 27 : 22, fill: i === 2 ? "var(--grafico-serie-2-fondo)" : "var(--grafico-superficie)", stroke: i === 2 ? "var(--grafico-serie-2)" : "var(--grafico-eje)" });
      texto(svg, x, y + 4, label, { tamano: label.length > 8 ? 8.7 : 10, peso: 650 });
    });
    texto(svg, 230, 208, "INTEGRACIÓN · DISTRIBUCIÓN · GOBIERNO", { tamano: 9.5, peso: 650, color: "var(--tinta-suave)" });
  }

  function dibujarRefresh(svg) {
    const xs = [74, 181, 288, 395];
    const labels = ["Origen", "Carga", "Corte", "Informe"];
    linea(svg, xs[0], 105, xs[3], 105, "var(--grafico-azul-marca)", 2);
    xs.forEach((x, i) => {
      agregar(svg, "circle", { cx: x, cy: 105, r: 18, fill: i === 2 ? "var(--grafico-serie-2-fondo)" : "var(--grafico-superficie)", stroke: i === 2 ? "var(--grafico-serie-2)" : "var(--grafico-serie-1)", "stroke-width": 1.8 });
      agregar(svg, "circle", { cx: x, cy: 105, r: 5, fill: i === 2 ? "var(--grafico-serie-2)" : "var(--grafico-serie-1)" });
      texto(svg, x, 145, labels[i], { tamano: 10.5, peso: 600 });
    });
    agregar(svg, "rect", { x: 99, y: 174, width: 262, height: 27, rx: 5, fill: "var(--grafico-azul-fondo)", stroke: "var(--grafico-rejilla)" });
    texto(svg, 230, 192, "HORA DE CARGA ≠ FECHA DE LOS DATOS", { tamano: 9.5, peso: 650 });
  }

  function dibujarMedicion(svg) {
    const grupos = [[110, "ANTES", [72, 96, 116]], [350, "DESPUÉS", [39, 55, 62]]];
    grupos.forEach(([centro, nombre, valores], grupo) => {
      texto(svg, centro, 40, nombre, { tamano: 10, peso: 700, color: grupo ? "var(--grafico-serie-3)" : "var(--tinta-suave)" });
      valores.forEach((alto, i) => agregar(svg, "rect", { x: centro - 49 + i * 36, y: 170 - alto, width: 23, height: alto, rx: 2, fill: grupo ? "var(--grafico-serie-3)" : "var(--grafico-eje)", opacity: ".9" }));
      linea(svg, centro - 62, 171, centro + 62, 171, "var(--grafico-eje)", 1.2);
    });
    linea(svg, 185, 113, 271, 113, "var(--grafico-azul-marca)", 2.5);
    texto(svg, 230, 103, "MEDIR", { tamano: 9, peso: 700, color: "var(--grafico-serie-1)" });
    texto(svg, 230, 205, "TIEMPO · ERRORES · REPROCESO", { tamano: 9.5, peso: 650, color: "var(--tinta-suave)" });
  }

  function dibujarProceso(svg) {
    dibujarFlujo(svg, ["Entrada", "Reglas", "Excepción"]);
    agregar(svg, "circle", { cx: 386, cy: 96, r: 8, fill: "var(--grafico-serie-2-fondo)", stroke: "var(--grafico-serie-2)", "stroke-width": 1.5 });
    texto(svg, 386, 100, "!", { tamano: 11, peso: 700, color: "var(--grafico-serie-2)" });
  }

  function dibujar(svg, tipo) {
    switch (tipo) {
      case "capas": return dibujarCapas(svg);
      case "modelo": return dibujarModelo(svg);
      case "comparacion": return dibujarComparacion(svg);
      case "mcp": return dibujarMcp(svg);
      case "matriz": return dibujarMatriz(svg);
      case "controles": return dibujarControles(svg);
      case "traza": return dibujarTraza(svg);
      case "ranking": return dibujarRanking(svg);
      case "variacion": return dibujarLineas(svg);
      case "caja": return dibujarLineas(svg, true);
      case "depreciacion": return dibujarDepreciacion(svg);
      case "incidente": return dibujarIncidente(svg);
      case "adopcion": return dibujarAdopcion(svg);
      case "refresh": return dibujarRefresh(svg);
      case "medicion": return dibujarMedicion(svg);
      case "proceso": return dibujarProceso(svg);
      case "tabla": return dibujarTabla(svg);
      case "riesgo":
        dibujarFlujo(svg, ["Dato", "Control", "Publicación"]);
        agregar(svg, "circle", { cx: 230, cy: 62, r: 11, fill: "var(--grafico-serie-2-fondo)", stroke: "var(--grafico-serie-2)", "stroke-width": 1.5 });
        texto(svg, 230, 66, "!", { tamano: 12, peso: 700, color: "var(--grafico-serie-2)" });
        return;
      default: return dibujarFlujo(svg);
    }
  }

  function montar() {
    const archivo = location.pathname.split("/").pop() || "index.html";
    const config = temas[archivo];
    if (!config) return;
    const portada = document.querySelector(".portada");
    if (!portada || !portada.querySelector("h1")) return;

    // Algunas páginas de método ya reservan una figura en su portada y la
    // completan con módulos. El SVG ligero sirve de respaldo al abrir file://.
    if (portada.classList.contains("portada-grafico")) {
      const figuraExistente = portada.querySelector("figure");
      if (figuraExistente && !figuraExistente.querySelector("svg, img")) {
        const svg = baseSvg(config, archivo.replace(/[^a-z0-9]/gi, "-"));
        dibujar(svg, config.tipo);
        figuraExistente.append(svg);
      }
      return;
    }
    if (portada.querySelector(".portada-visual")) return;

    const textoPortada = document.createElement("div");
    textoPortada.className = "portada-texto";
    for (const hijo of Array.from(portada.children)) textoPortada.append(hijo);

    const lateral = document.createElement("aside");
    lateral.className = "portada-visual";
    const rotulo = document.createElement("p");
    rotulo.className = "rotulo";
    rotulo.textContent = config.grupo;
    const figura = document.createElement("figure");
    const svg = baseSvg(config, archivo.replace(/[^a-z0-9]/gi, "-"));
    dibujar(svg, config.tipo);
    const pie = document.createElement("figcaption");
    pie.textContent = config.pie;
    figura.append(svg, pie);
    lateral.append(rotulo, figura);
    portada.replaceChildren(textoPortada, lateral);
    portada.classList.add("portada-con-visual");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", montar, { once: true });
  else montar();
})();
