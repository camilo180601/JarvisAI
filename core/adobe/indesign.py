# -*- coding: utf-8 -*-
"""adobe/indesign.py — operaciones de InDesign (id_*)."""
from __future__ import annotations
from core.adobe_templates import _jsx, _hex_to_rgb, _esc


def id_new_doc(pages: int = 1, margin: float = 12.7, columns: int = 1,
               w_mm: float = 210, h_mm: float = 297) -> str:
    return _jsx({"PAGES": int(pages), "MARGIN": margin, "COLS": int(columns),
                 "WMM": w_mm, "HMM": h_mm}, """
function main(){
  var d = app.documents.add();
  d.documentPreferences.pageWidth = WMM + "mm";
  d.documentPreferences.pageHeight = HMM + "mm";
  d.documentPreferences.pagesPerDocument = PAGES;
  d.marginPreferences.top = MARGIN + "mm";
  d.marginPreferences.bottom = MARGIN + "mm";
  d.marginPreferences.left = MARGIN + "mm";
  d.marginPreferences.right = MARGIN + "mm";
  d.marginPreferences.columnCount = COLS;
  return "OK: documento de " + PAGES + " página(s) creado";
}""")


def id_place(content: str, is_image: bool) -> str:
    return _jsx({"CONTENT": content, "IS_IMAGE": bool(is_image)}, """
function main(){
  if (app.documents.length === 0) app.documents.add();
  var d = app.activeDocument;
  var page = d.pages[0];
  var b = page.bounds; // [y1,x1,y2,x2]
  var m = 36;
  var frame = page.textFrames.add();
  frame.geometricBounds = [b[0]+m, b[1]+m, b[2]-m, b[3]-m];
  if (IS_IMAGE){
    var f = new File(CONTENT);
    if (!f.exists) return "ERROR: no existe la imagen " + CONTENT;
    var rect = page.rectangles.add();
    rect.geometricBounds = [b[0]+m, b[1]+m, b[2]-m, b[3]-m];
    rect.place(f);
    rect.fit(FitOptions.PROPORTIONALLY);
    return "OK: imagen colocada";
  } else {
    frame.contents = CONTENT;
    return "OK: texto colocado";
  }
}""")


def id_page_numbers() -> str:
    return _jsx({}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var master = d.masterSpreads[0];
  for (var p=0; p<master.pages.length; p++){
    var pg = master.pages[p];
    var b = pg.bounds;
    var tf = pg.textFrames.add();
    tf.geometricBounds = [b[2]-30, b[1]+36, b[2]-12, b[3]-36];
    tf.insertionPoints[0].contents = SpecialCharacters.AUTO_PAGE_NUMBER;
    tf.texts[0].justification = Justification.CENTER_ALIGN;
  }
  return "OK: numeración de páginas agregada (en la página maestra)";
}""")


def id_find_replace(find: str, replace: str) -> str:
    return _jsx({"FIND": find, "REPL": replace}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  app.findTextPreferences = NothingEnum.NOTHING;
  app.changeTextPreferences = NothingEnum.NOTHING;
  app.findTextPreferences.findWhat = FIND;
  app.changeTextPreferences.changeTo = REPL;
  var changed = app.activeDocument.changeText();
  app.findTextPreferences = NothingEnum.NOTHING;
  app.changeTextPreferences = NothingEnum.NOTHING;
  return "OK: " + changed.length + " reemplazo(s)";
}""")


def id_step_repeat(rows: int = 3, cols: int = 3, gap: float = 5) -> str:
    """Step & repeat: grilla de copias de la selección (rows x cols)."""
    return _jsx({"ROWS": int(rows), "COLS": int(cols), "GAP": float(gap)}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  var doc = app.activeDocument;
  doc.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.POINTS;
  doc.viewPreferences.verticalMeasurementUnits = MeasurementUnits.POINTS;
  var sel = doc.selection;
  if (!sel || sel.length < 1) return "ERROR: seleccioná un objeto.";
  var item = sel[0];
  var b = item.geometricBounds;            // [y1,x1,y2,x2]
  var w = b[3]-b[1], h = b[2]-b[0];
  var n = 0;
  for (var r=0; r<ROWS; r++){
    for (var c=0; c<COLS; c++){
      if (r===0 && c===0) continue;
      var dup = item.duplicate();
      dup.move(undefined, [(w+GAP)*c, (h+GAP)*r]);
      n++;
    }
  }
  return "OK: step&repeat " + (ROWS*COLS) + " copias";
}""")


def id_text_frame(text: str = "", x: float = 20, y: float = 20,
                  w: float = 170, h: float = 60, size: float = 18) -> str:
    """Crea un marco de texto en la página activa de InDesign (medidas en mm)."""
    return _jsx({"TXT": text, "X": float(x), "Y": float(y),
                 "W": float(w), "H": float(h), "SZ": float(size)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var page = app.activeWindow.activePage;
  var tf = page.textFrames.add();
  tf.geometricBounds = [Y, X, Y+H, X+W];   // [y1, x1, y2, x2]
  tf.contents = TXT;
  try { tf.texts[0].pointSize = SZ; } catch(e){}
  return "OK: marco de texto agregado";
}""")


def id_table(rows: int = 3, cols: int = 3, x: float = 20, y: float = 20,
             w: float = 170, h: float = 80) -> str:
    """Crea una tabla (rows x cols) dentro de un marco de texto en InDesign."""
    return _jsx({"R": int(rows), "C": int(cols), "X": float(x), "Y": float(y),
                 "W": float(w), "H": float(h)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var page = app.activeWindow.activePage;
  var tf = page.textFrames.add();
  tf.geometricBounds = [Y, X, Y+H, X+W];
  var t = tf.insertionPoints[0].tables.add();
  t.bodyRowCount = R;
  t.columnCount = C;
  return "OK: tabla " + R + "x" + C + " creada";
}""")


def id_rectangle(x: float = 20, y: float = 20, w: float = 80, h: float = 50,
                 hex_color: str = "#1e90ff") -> str:
    """Dibuja un rectángulo de color en la página activa de InDesign (mm)."""
    return _jsx({"X": float(x), "Y": float(y), "W": float(w), "H": float(h),
                 "FILL": _hex_to_rgb(hex_color)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var page = app.activeWindow.activePage;
  var r = page.rectangles.add();
  r.geometricBounds = [Y, X, Y+H, X+W];
  var c = d.colors.add();
  c.model = ColorModel.PROCESS; c.space = ColorSpace.RGB;
  c.colorValue = [FILL[0], FILL[1], FILL[2]];
  r.fillColor = c;
  return "OK: rectángulo de color agregado";
}""")


_ID_CORNER = {
    "rounded": "ROUNDED_CORNER", "redondeada": "ROUNDED_CORNER", "redondeadas": "ROUNDED_CORNER",
    "beveled": "BEVEL_CORNER", "bisel": "BEVEL_CORNER", "biselada": "BEVEL_CORNER",
    "inverse": "INVERSE_ROUNDED_CORNER", "inset": "INSET_CORNER", "fancy": "FANCY_CORNER",
}


def id_corner_options(radius: float = 5, style: str = "rounded") -> str:
    """Esquinas (redondeadas/biseladas/etc.) a la selección o al último rectángulo en InDesign."""
    sty = _ID_CORNER.get((style or "").lower(), "ROUNDED_CORNER")
    return _jsx({"RAD": float(radius), "STY": sty}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var items = (d.selection && d.selection.length) ? d.selection : null;
  if (!items) {
    var page = app.activeWindow.activePage;
    if (page.rectangles.length) items = [page.rectangles[-1]];
  }
  if (!items || !items.length) return "ERROR: seleccioná un marco o dibujá un rectángulo primero.";
  var enumv = CornerOptions[STY];
  var n = 0, i;
  for (i = 0; i < items.length; i++) {
    var it = items[i];
    try {
      it.topLeftCornerOption = enumv; it.topRightCornerOption = enumv;
      it.bottomLeftCornerOption = enumv; it.bottomRightCornerOption = enumv;
      it.topLeftCornerRadius = RAD; it.topRightCornerRadius = RAD;
      it.bottomLeftCornerRadius = RAD; it.bottomRightCornerRadius = RAD;
      n++;
    } catch(e){}
  }
  if (n === 0) return "ERROR: no pude aplicar esquinas (¿el objeto soporta esquinas?).";
  return "OK: esquinas " + STY + " (radio " + RAD + ") en " + n;
}""")


def id_oval(x: float = 20, y: float = 20, w: float = 60, h: float = 60,
            hex_color: str = "#1e90ff") -> str:
    """Dibuja una elipse de color en la página activa de InDesign (mm)."""
    return _jsx({"X": float(x), "Y": float(y), "W": float(w), "H": float(h),
                 "FILL": _hex_to_rgb(hex_color)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var page = app.activeWindow.activePage;
  var o = page.ovals.add();
  o.geometricBounds = [Y, X, Y+H, X+W];
  var c = d.colors.add();
  c.model = ColorModel.PROCESS; c.space = ColorSpace.RGB;
  c.colorValue = [FILL[0], FILL[1], FILL[2]];
  o.fillColor = c;
  return "OK: elipse de color agregada";
}""")


def id_polygon(x: float = 20, y: float = 20, w: float = 60, h: float = 60,
               sides: int = 6, star_inset: float = 0, hex_color: str = "#1e90ff") -> str:
    """Polígono (o estrella si star_inset>0) de color en InDesign. star_inset = % de inserción de puntas."""
    return _jsx({"X": float(x), "Y": float(y), "W": float(w), "H": float(h),
                 "SIDES": int(sides), "INSET": float(star_inset), "FILL": _hex_to_rgb(hex_color)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  try { d.polygonPreferences.numberOfSides = SIDES; d.polygonPreferences.insetPercentage = INSET; } catch(ep){}
  var page = app.activeWindow.activePage;
  var p = page.polygons.add();
  p.geometricBounds = [Y, X, Y+H, X+W];
  var c = d.colors.add();
  c.model = ColorModel.PROCESS; c.space = ColorSpace.RGB;
  c.colorValue = [FILL[0], FILL[1], FILL[2]];
  p.fillColor = c;
  return "OK: polígono de " + SIDES + " lados" + (INSET > 0 ? " (estrella)" : "");
}""")


def id_drop_shadow(opacity: float = 60, offset: float = 2, size: float = 2) -> str:
    """Sombra paralela a la selección (o al último rectángulo) en InDesign. Medidas en mm."""
    return _jsx({"OP": float(opacity), "OFF": float(offset), "SZ": float(size)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var items = (d.selection && d.selection.length) ? d.selection : null;
  if (!items) {
    var page = app.activeWindow.activePage;
    if (page.rectangles.length) items = [page.rectangles[-1]];
  }
  if (!items || !items.length) return "ERROR: seleccioná un objeto o dibujá uno primero.";
  var n = 0, i;
  for (i = 0; i < items.length; i++) {
    try {
      var ds = items[i].transparencySettings.dropShadowSettings;
      ds.mode = ShadowMode.DROP;
      ds.opacity = OP; ds.xOffset = OFF; ds.yOffset = OFF; ds.size = SZ;
      n++;
    } catch(e){}
  }
  if (n === 0) return "ERROR: no pude aplicar la sombra.";
  return "OK: sombra en " + n + " objeto(s)";
}""")


def id_image_grid(folder: str, cols: int = 3, margin: float = 12,
                  gap: float = 4, limit: int = 30) -> str:
    """Arma una grilla (contact sheet) con las imágenes de una carpeta en la página activa de InDesign."""
    return _jsx({"DIR": folder, "COLS": int(cols), "MARGIN": float(margin),
                 "GAP": float(gap), "LIMIT": int(limit)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var folder = new Folder(DIR);
  if (!folder.exists) return "ERROR: no existe la carpeta " + DIR;
  var files = folder.getFiles(/\\.(jpe?g|png|tiff?|psd|pdf|eps|ai|gif)$/i);
  if (!files.length) return "ERROR: no hay imágenes en la carpeta.";
  if (files.length > LIMIT) files = files.slice(0, LIMIT);
  var page = app.activeWindow.activePage;
  var b = page.bounds;  // [y1, x1, y2, x2]
  var pageW = b[3]-b[1], pageH = b[2]-b[0];
  var cols = COLS, rows = Math.ceil(files.length / cols);
  var cw = (pageW - 2*MARGIN - (cols-1)*GAP) / cols;
  var ch = (pageH - 2*MARGIN - (rows-1)*GAP) / rows;
  var n = 0, i;
  for (i = 0; i < files.length; i++) {
    var r = Math.floor(i/cols), c = i % cols;
    var x = b[1] + MARGIN + c*(cw+GAP);
    var y = b[0] + MARGIN + r*(ch+GAP);
    var fr = page.rectangles.add();
    fr.geometricBounds = [y, x, y+ch, x+cw];
    try {
      fr.place(files[i]);
      fr.fit(FitOptions.PROPORTIONALLY);
      fr.fit(FitOptions.CENTER_CONTENT);
      n++;
    } catch(e){}
  }
  return "OK: " + n + " imágenes en grilla " + cols + "x" + rows;
}""")


def id_line(x1: float = 20, y1: float = 20, x2: float = 120, y2: float = 80,
            hex_color: str = "#000000", width: float = 1) -> str:
    """Dibuja una línea gráfica en la página activa de InDesign (mm)."""
    return _jsx({"X1": float(x1), "Y1": float(y1), "X2": float(x2), "Y2": float(y2),
                 "FILL": _hex_to_rgb(hex_color), "W": float(width)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var page = app.activeWindow.activePage;
  var gl = page.graphicLines.add();
  gl.geometricBounds = [Y1, X1, Y2, X2];
  gl.strokeWeight = W;
  var c = d.colors.add();
  c.model = ColorModel.PROCESS; c.space = ColorSpace.RGB;
  c.colorValue = [FILL[0], FILL[1], FILL[2]];
  gl.strokeColor = c;
  return "OK: línea agregada";
}""")


def id_gradient(hex_a: str = "#1e90ff", hex_b: str = "#ffffff", gtype: str = "linear") -> str:
    """Aplica un degradado a la selección (o último rectángulo) en InDesign."""
    return _jsx({"A": _hex_to_rgb(hex_a), "B": _hex_to_rgb(hex_b),
                 "TYPE": (gtype or "linear").lower()}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var items = (d.selection && d.selection.length) ? d.selection : null;
  if (!items) {
    var page = app.activeWindow.activePage;
    if (page.rectangles.length) items = [page.rectangles[-1]];
  }
  if (!items || !items.length) return "ERROR: seleccioná un objeto o dibujá uno primero.";
  var g = d.gradients.add();
  g.type = (TYPE === "radial") ? GradientType.RADIAL : GradientType.LINEAR;
  var c1 = d.colors.add(); c1.model = ColorModel.PROCESS; c1.space = ColorSpace.RGB; c1.colorValue = [A[0], A[1], A[2]];
  var c2 = d.colors.add(); c2.model = ColorModel.PROCESS; c2.space = ColorSpace.RGB; c2.colorValue = [B[0], B[1], B[2]];
  var st = g.gradientStops;
  st[0].stopColor = c1; st[st.length-1].stopColor = c2;
  var n = 0, i;
  for (i = 0; i < items.length; i++) { try { items[i].fillColor = g; n++; } catch(e){} }
  if (n === 0) return "ERROR: no pude aplicar el degradado.";
  return "OK: degradado " + TYPE + " en " + n + " objeto(s)";
}""")


def id_add_pages(count: int = 1) -> str:
    """Agrega N páginas al documento de InDesign."""
    return _jsx({"N": int(count)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument, i;
  for (i = 0; i < N; i++) d.pages.add();
  return "OK: " + N + " página(s) agregada(s) (total " + d.pages.length + ")";
}""")


def id_guides(horizontals: list | None = None, verticals: list | None = None) -> str:
    """Agrega guías de regla en la página activa de InDesign (posiciones en mm)."""
    return _jsx({"HG": [float(v) for v in (horizontals or [])],
                 "VG": [float(v) for v in (verticals or [])]}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var page = app.activeWindow.activePage;
  var n = 0, i;
  for (i = 0; i < HG.length; i++) { page.guides.add(undefined, {orientation: HorizontalOrVertical.HORIZONTAL, location: HG[i]}); n++; }
  for (i = 0; i < VG.length; i++) { page.guides.add(undefined, {orientation: HorizontalOrVertical.VERTICAL, location: VG[i]}); n++; }
  if (n === 0) return "ERROR: dame posiciones (horizontals y/o verticals).";
  return "OK: " + n + " guías agregadas";
}""")


def id_outline_text() -> str:
    """Convierte el texto a curvas en InDesign (selección, o todos los marcos de la página)."""
    return _jsx({}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var items = (d.selection && d.selection.length) ? d.selection : null;
  if (!items) {
    var page = app.activeWindow.activePage;
    items = [];
    var k; for (k = 0; k < page.textFrames.length; k++) items.push(page.textFrames[k]);
  }
  if (!items || !items.length) return "ERROR: no hay texto para convertir.";
  var n = 0, i;
  for (i = 0; i < items.length; i++) {
    try { items[i].createOutlines(false); n++; } catch(e){}
  }
  if (n === 0) return "ERROR: no pude convertir (¿hay marcos de texto?).";
  return "OK: texto convertido a curvas (" + n + ")";
}""")


_ID_JUST = {"left": "LEFT_ALIGN", "izquierda": "LEFT_ALIGN", "center": "CENTER_ALIGN", "centro": "CENTER_ALIGN",
            "right": "RIGHT_ALIGN", "derecha": "RIGHT_ALIGN", "justify": "LEFT_JUSTIFIED", "justificado": "LEFT_JUSTIFIED"}


def _id_text_targets():
    """JS: arma 'items' = textos seleccionados o el último marco de texto de la página."""
    return """
  var d = app.activeDocument;
  var targets = [];
  if (d.selection && d.selection.length) {
    var s; for (s = 0; s < d.selection.length; s++) {
      var sel = d.selection[s];
      if (sel.hasOwnProperty("texts")) targets.push(sel.texts[0]);
      else if (sel.constructor.name === "Text" || sel.constructor.name === "InsertionPoint") targets.push(sel.parentStory.texts[0]);
    }
  }
  if (!targets.length) {
    var page = app.activeWindow.activePage;
    if (page.textFrames.length) targets.push(page.textFrames[-1].texts[0]);
  }
"""


def id_font(font: str | None = None, size: float = 0, tracking: float | None = None,
            leading: float = 0) -> str:
    """Aplica fuente/tamaño/tracking/interlineado al texto seleccionado (o último marco) en InDesign."""
    return _jsx({"FONT": font, "SZ": float(size), "TRACK": (None if tracking is None else float(tracking)),
                 "LEAD": float(leading)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
""" + _id_text_targets() + """
  if (!targets.length) return "ERROR: no hay texto.";
  var n = 0, i;
  for (i = 0; i < targets.length; i++) {
    var t = targets[i];
    if (FONT) { try { t.appliedFont = FONT; } catch(e){} }
    if (SZ > 0) t.pointSize = SZ;
    if (TRACK !== null) t.tracking = TRACK;
    if (LEAD > 0) t.leading = LEAD;
    n++;
  }
  return "OK: tipografía aplicada (" + n + ")";
}""")


def id_text_align(align: str = "left") -> str:
    """Alineación de párrafo (left/center/right/justify) del texto seleccionado en InDesign."""
    j = _ID_JUST.get((align or "").lower(), "LEFT_ALIGN")
    return _jsx({"J": j}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
""" + _id_text_targets() + """
  if (!targets.length) return "ERROR: no hay texto.";
  var n = 0, i;
  for (i = 0; i < targets.length; i++) { targets[i].justification = Justification[J]; n++; }
  return "OK: alineación " + J + " (" + n + ")";
}""")


def id_paragraph_style(name: str = "Cuerpo", font: str | None = None, size: float = 0,
                       leading: float = 0, align: str = "left", hex_color: str | None = None) -> str:
    """Crea (si no existe) y aplica un estilo de párrafo en InDesign."""
    j = _ID_JUST.get((align or "").lower(), "LEFT_ALIGN")
    return _jsx({"NAME": name, "FONT": font, "SZ": float(size), "LEAD": float(leading),
                 "J": j, "COLOR": (_hex_to_rgb(hex_color) if hex_color else None)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var ps = d.paragraphStyles.itemByName(NAME);
  if (!ps.isValid) ps = d.paragraphStyles.add({name: NAME});
  if (FONT) { try { ps.appliedFont = FONT; } catch(e){} }
  if (SZ > 0) ps.pointSize = SZ;
  if (LEAD > 0) ps.leading = LEAD;
  ps.justification = Justification[J];
  if (COLOR) {
    var c = d.colors.add(); c.model = ColorModel.PROCESS; c.space = ColorSpace.RGB;
    c.colorValue = [COLOR[0], COLOR[1], COLOR[2]];
    ps.fillColor = c;
  }
""" + _id_text_targets() + """
  var n = 0, i;
  for (i = 0; i < targets.length; i++) { try { targets[i].appliedParagraphStyle = ps; n++; } catch(e){} }
  return "OK: estilo '" + NAME + "' creado" + (n ? " y aplicado (" + n + ")" : "");
}""")


def id_text_columns(count: int = 2, gutter: float = 4) -> str:
    """Define columnas en el marco de texto seleccionado (o el último) en InDesign."""
    return _jsx({"COLS": int(count), "GUT": float(gutter)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var frames = [];
  if (d.selection && d.selection.length) {
    var s; for (s = 0; s < d.selection.length; s++) { if (d.selection[s].hasOwnProperty("textFramePreferences")) frames.push(d.selection[s]); }
  }
  if (!frames.length) {
    var page = app.activeWindow.activePage;
    if (page.textFrames.length) frames.push(page.textFrames[-1]);
  }
  if (!frames.length) return "ERROR: seleccioná un marco de texto.";
  var n = 0, i;
  for (i = 0; i < frames.length; i++) {
    frames[i].textFramePreferences.textColumnCount = COLS;
    frames[i].textFramePreferences.textColumnGutter = GUT;
    n++;
  }
  return "OK: " + COLS + " columnas en " + n + " marco(s)";
}""")


def id_bullets(mode: str = "bullet") -> str:
    """Aplica viñetas o numeración a los párrafos del texto seleccionado (o último marco) en InDesign."""
    lt = {"bullet": "BULLET_LIST", "vineta": "BULLET_LIST", "viñeta": "BULLET_LIST",
          "number": "NUMBERED_LIST", "numero": "NUMBERED_LIST", "número": "NUMBERED_LIST",
          "none": "NO_LIST", "ninguno": "NO_LIST"}.get((mode or "").lower(), "BULLET_LIST")
    return _jsx({"LT": lt}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
""" + _id_text_targets() + """
  if (!targets.length) return "ERROR: no hay texto.";
  var n = 0, i;
  for (i = 0; i < targets.length; i++) {
    try { targets[i].bulletsAndNumberingListType = ListType[LT]; n++; } catch(e){}
  }
  if (n === 0) return "ERROR: no pude aplicar la lista.";
  return "OK: lista " + LT + " (" + n + ")";
}""")


def id_fit(mode: str = "content_to_frame") -> str:
    """Ajusta marco↔contenido en InDesign: content_to_frame | frame_to_content | proportional | fill | center."""
    fit_map = {
        "content_to_frame": "CONTENT_TO_FRAME", "frame_to_content": "FRAME_TO_CONTENT",
        "proportional": "PROPORTIONALLY", "proporcional": "PROPORTIONALLY",
        "fill": "FILL_PROPORTIONALLY", "center": "CENTER_CONTENT",
    }
    fo = fit_map.get((mode or "").lower(), "CONTENT_TO_FRAME")
    return _jsx({"FO": fo}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  if (!d.selection || !d.selection.length) return "ERROR: seleccioná un marco.";
  var n = 0, i;
  for (i = 0; i < d.selection.length; i++) {
    try { d.selection[i].fit(FitOptions[FO]); n++; } catch(e){}
  }
  if (n === 0) return "ERROR: no pude ajustar (¿seleccionaste un marco con contenido?).";
  return "OK: ajustado (" + FO + ") en " + n;
}""")


def id_master_page(name: str = "B-Master", margin: float = 12.7) -> str:
    """Crea una página maestra (master spread) en InDesign con un marco de texto guía."""
    return _jsx({"NAME": name, "MARGIN": float(margin)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var m;
  var parts = NAME.split("-");
  var prefix = (parts.length > 1) ? parts[0] : "B";
  var title = (parts.length > 1) ? parts.slice(1).join("-") : NAME;
  m = d.masterSpreads.add();
  try { m.namePrefix = prefix; m.baseName = title; } catch(e){}
  return "OK: página maestra '" + NAME + "' creada";
}""")


def id_apply_master(master_name: str | None = None, page_index: int = -1) -> str:
    """Aplica una página maestra a una página (por índice; -1 = todas)."""
    return _jsx({"MNAME": master_name, "PIDX": int(page_index)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var master = null, i;
  if (MNAME) {
    for (i = 0; i < d.masterSpreads.length; i++) {
      var ms = d.masterSpreads[i];
      if ((ms.namePrefix + "-" + ms.baseName) === MNAME || ms.baseName === MNAME || ms.name === MNAME) { master = ms; break; }
    }
    if (!master) return "ERROR: no encontré la maestra '" + MNAME + "'";
  } else {
    if (d.masterSpreads.length === 0) return "ERROR: no hay páginas maestras.";
    master = d.masterSpreads[d.masterSpreads.length-1];
  }
  var n = 0;
  if (PIDX < 0) { for (i = 0; i < d.pages.length; i++) { d.pages[i].appliedMaster = master; n++; } }
  else { if (PIDX >= d.pages.length) return "ERROR: la página " + PIDX + " no existe."; d.pages[PIDX].appliedMaster = master; n = 1; }
  return "OK: maestra aplicada a " + n + " página(s)";
}""")


def id_text_wrap(mode: str = "bounding", offset: float = 3) -> str:
    """Ceñido de texto (text wrap) a la selección o último objeto: bounding | object | none. offset en mm."""
    tw = {"bounding": "BOUNDING_BOX_TEXT_WRAP", "object": "CONTOUR", "contour": "CONTOUR",
          "jump": "JUMP_OBJECT_TEXT_WRAP", "none": "NONE", "ninguno": "NONE"}.get((mode or "").lower(), "BOUNDING_BOX_TEXT_WRAP")
    return _jsx({"TW": tw, "OFF": float(offset)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var items = (d.selection && d.selection.length) ? d.selection : null;
  if (!items) {
    var page = app.activeWindow.activePage;
    var all = []; var k;
    for (k = 0; k < page.rectangles.length; k++) all.push(page.rectangles[k]);
    for (k = 0; k < page.ovals.length; k++) all.push(page.ovals[k]);
    if (all.length) items = [all[all.length-1]];
  }
  if (!items || !items.length) return "ERROR: seleccioná un objeto.";
  var n = 0, i;
  for (i = 0; i < items.length; i++) {
    try {
      var tw = items[i].textWrapPreferences;
      tw.textWrapMode = TextWrapModes[TW];
      if (TW !== "NONE") tw.textWrapOffset = [OFF, OFF, OFF, OFF];
      n++;
    } catch(e){}
  }
  if (n === 0) return "ERROR: no pude aplicar el ceñido.";
  return "OK: ceñido de texto " + TW + " en " + n;
}""")


def id_object_style(name: str = "Caja", fill_hex: str | None = None, stroke_hex: str | None = None,
                    stroke_weight: float = 0) -> str:
    """Crea (si no existe) y aplica un estilo de objeto a la selección en InDesign."""
    return _jsx({"NAME": name, "FILL": (_hex_to_rgb(fill_hex) if fill_hex else None),
                 "STROKE": (_hex_to_rgb(stroke_hex) if stroke_hex else None), "SW": float(stroke_weight)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var os = d.objectStyles.itemByName(NAME);
  if (!os.isValid) os = d.objectStyles.add({name: NAME});
  if (FILL) { var cf = d.colors.add(); cf.model = ColorModel.PROCESS; cf.space = ColorSpace.RGB; cf.colorValue = [FILL[0],FILL[1],FILL[2]]; os.fillColor = cf; }
  if (STROKE) { var cs = d.colors.add(); cs.model = ColorModel.PROCESS; cs.space = ColorSpace.RGB; cs.colorValue = [STROKE[0],STROKE[1],STROKE[2]]; os.strokeColor = cs; }
  if (SW > 0) os.strokeWeight = SW;
  var n = 0, i;
  if (d.selection && d.selection.length) {
    for (i = 0; i < d.selection.length; i++) { try { d.selection[i].appliedObjectStyle = os; n++; } catch(e){} }
  }
  return "OK: estilo de objeto '" + NAME + "' creado" + (n ? " y aplicado (" + n + ")" : "");
}""")


def id_place_text_file(path: str, x: float = 20, y: float = 20, w: float = 170, h: float = 200) -> str:
    """Coloca un archivo de texto (.txt/.rtf/.docx) en un marco de InDesign (mm)."""
    return _jsx({"PATH": path, "X": float(x), "Y": float(y), "W": float(w), "H": float(h)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var f = new File(PATH);
  if (!f.exists) return "ERROR: no existe " + PATH;
  var d = app.activeDocument;
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var page = app.activeWindow.activePage;
  var tf = page.textFrames.add();
  tf.geometricBounds = [Y, X, Y+H, X+W];
  tf.place(f);
  return "OK: archivo de texto colocado";
}""")


def id_thread_frames() -> str:
    """Hila (encadena) los marcos de texto de la página activa en orden, para que el texto fluya."""
    return _jsx({}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var page = app.activeWindow.activePage;
  var frames = page.textFrames;
  if (frames.length < 2) return "ERROR: hacen falta 2+ marcos de texto en la página.";
  var n = 0, i;
  for (i = 0; i < frames.length - 1; i++) {
    try { frames[i].nextTextFrame = frames[i+1]; n++; } catch(e){}
  }
  if (n === 0) return "ERROR: no pude hilar los marcos.";
  return "OK: " + (n+1) + " marcos hilados";
}""")


def id_layer(name: str = "Capa", hex_color: str | None = None) -> str:
    """Crea (si no existe) una capa en InDesign, con color de capa opcional."""
    return _jsx({"NAME": name, "COLOR": (_hex_to_rgb(hex_color) if hex_color else None)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var lyr = d.layers.itemByName(NAME);
  if (!lyr.isValid) lyr = d.layers.add({name: NAME});
  if (COLOR) { try { lyr.layerColor = [COLOR[0], COLOR[1], COLOR[2]]; } catch(e){} }
  return "OK: capa '" + NAME + "' lista";
}""")


def id_toc(style_name: str = "Cuerpo", title: str = "Contenido") -> str:
    """Genera una tabla de contenido en InDesign a partir de un estilo de párrafo existente."""
    return _jsx({"STYLE": style_name, "TITLE": title}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var ps = d.paragraphStyles.itemByName(STYLE);
  if (!ps.isValid) return "ERROR: no existe el estilo de párrafo '" + STYLE + "'.";
  var tocStyle;
  try { tocStyle = d.tocStyles.add(); } catch(e){ return "ERROR: " + e.toString(); }
  tocStyle.title = TITLE;
  try {
    var entry = tocStyle.tocStyleEntries.add();
    entry.styleReference = ps;
  } catch(e2){}
  d.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  d.viewPreferences.verticalMeasurementUnits = MeasurementUnits.MILLIMETERS;
  var page = d.pages.add(LocationOptions.AT_BEGINNING);
  var b = page.bounds;  // [y1,x1,y2,x2]
  var story;
  try { story = d.createTOC(tocStyle, true, undefined, [b[1]+12, b[0]+12]); }
  catch(e){
    var tf = page.textFrames.add();
    tf.geometricBounds = [b[0]+12, b[1]+12, b[2]-12, b[3]-12];
    try { story = d.createTOC(tocStyle, true, undefined, tf); }
    catch(e2){ return "ERROR: createTOC (" + e2.toString() + ")"; }
  }
  return "OK: tabla de contenido generada (estilo '" + STYLE + "')";
}""")

