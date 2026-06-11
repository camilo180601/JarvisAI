"""
adobe_templates.py — Plantillas ExtendScript curadas (no generadas por Gemini).

Para operaciones donde la API de Adobe es oscura o frágil (ej: Image Trace),
un script probado a mano es más confiable que pedirle uno a un LLM cada vez.
"""
from __future__ import annotations
import json

# Presets de Image Trace → substrings para matchear contra app.tracingPresetsList
# (la lista viene localizada, por eso buscamos en español E inglés).
TRACE_PRESETS = {
    "default":             ["por defecto", "predeterminado", "[default]", "default"],
    "high_fidelity_photo": ["alta fidelidad", "high fidelity"],
    "low_fidelity_photo":  ["baja fidelidad", "low fidelity"],
    "3_colors":            ["3 colores", "3 colors"],
    "6_colors":            ["6 colores", "6 colors"],
    "16_colors":           ["16 colores", "16 colors"],
    "shades_of_gray":      ["tonos de gris", "escala de grises", "shades of gray", "grayscale"],
    "black_and_white":     ["blanco y negro", "black and white", "logotipo en blanco"],
    "sketched_art":        ["boceto", "sketched"],
    "silhouettes":         ["silueta", "silhouette"],
    "line_art":            ["ilustracion de lineas", "ilustración de líneas", "líneas", "lineas", "line art"],
    "technical_drawing":   ["dibujo tecnico", "dibujo técnico", "technical drawing"],
}

# Estos presets ya producen relleno/color → no forzar el modo "trazo" (outline) por defecto.
_FILLED_PRESETS = {"high_fidelity_photo", "low_fidelity_photo", "3_colors", "6_colors",
                   "16_colors", "shades_of_gray"}


def preset_is_filled(preset: str | None) -> bool:
    return bool(preset) and preset.lower() in _FILLED_PRESETS


def _esc(path: str) -> str:
    """Escapa un path para incrustarlo en un string literal de ExtendScript."""
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _jsx(config: dict, body: str) -> str:
    """
    Arma un script: declara las vars de config con json.dumps (literales JS válidos:
    true/false/null, arrays, strings escapados) + el cuerpo JS plano (sin escapar llaves).
    El cuerpo debe terminar definiendo la última expresión como resultado.
    """
    header = "\n".join(f"var {k} = {json.dumps(v)};" for k, v in config.items())
    wrapper = "\nvar __r; try { __r = main(); } catch (e) { __r = 'ERROR: ' + e.toString(); } __r;\n"
    return header + "\n" + body + wrapper


def _hex_to_rgb(h: str) -> list[int]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)]
    except Exception:
        return [0, 0, 0]


# ───────────────────────── EXPORT (cross-app) ─────────────────────────

def illustrator_export(fmt: str, dest_base: str, dest_full: str, scale: float = 1.0) -> str:
    body = """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento abierto en Illustrator.";
  var doc = app.activeDocument;
  var res;
  if (FMT === "svg") {
    doc.exportFile(new File(DEST_BASE), ExportType.SVG, new ExportOptionsSVG());
    res = DEST_BASE + ".svg";
  } else if (FMT === "pdf") {
    doc.saveAs(new File(DEST_FULL), new PDFSaveOptions());
    res = DEST_FULL;
  } else if (FMT === "jpg" || FMT === "jpeg") {
    var oj = new ExportOptionsJPEG();
    oj.horizontalScale = SCALE * 100; oj.verticalScale = SCALE * 100;
    oj.qualitySetting = 80; oj.artBoardClipping = true;
    doc.exportFile(new File(DEST_BASE), ExportType.JPEG, oj);
    res = DEST_BASE + ".jpg";
  } else {
    var op = new ExportOptionsPNG24();
    op.horizontalScale = SCALE * 100; op.verticalScale = SCALE * 100;
    op.artBoardClipping = true; op.transparency = true;
    doc.exportFile(new File(DEST_BASE), ExportType.PNG24, op);
    res = DEST_BASE + ".png";
  }
  return "OK: exportado a " + res;
}
"""
    return _jsx({"FMT": fmt.lower(), "DEST_BASE": dest_base, "DEST_FULL": dest_full, "SCALE": scale}, body)


def photoshop_export(fmt: str, dest: str, quality: int = 80) -> str:
    body = """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento abierto en Photoshop.";
  app.displayDialogs = DialogModes.NO;
  var doc = app.activeDocument;
  if (FMT === "pdf") {
    doc.saveAs(new File(DEST), new PDFSaveOptions(), true);
  } else if (FMT === "psd") {
    doc.saveAs(new File(DEST), new PhotoshopSaveOptions(), true);
  } else {
    var o = new ExportOptionsSaveForWeb();
    if (FMT === "jpg" || FMT === "jpeg") { o.format = SaveDocumentType.JPEG; o.quality = QUALITY; }
    else { o.format = SaveDocumentType.PNG; o.PNG8 = false; }
    doc.exportDocument(new File(DEST), ExportType.SAVEFORWEB, o);
  }
  return "OK: exportado a " + DEST;
}
"""
    return _jsx({"FMT": fmt.lower(), "DEST": dest, "QUALITY": int(quality)}, body)


def indesign_export(fmt: str, dest: str) -> str:
    body = """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento abierto en InDesign.";
  var doc = app.activeDocument;
  var f;
  if (FMT === "png") f = ExportFormat.PNG_FORMAT;
  else if (FMT === "jpg" || FMT === "jpeg") f = ExportFormat.JPG;
  else if (FMT === "eps") f = ExportFormat.EPS_TYPE;
  else f = ExportFormat.PDF_TYPE;
  doc.exportFile(f, new File(DEST));
  return "OK: exportado a " + DEST;
}
"""
    return _jsx({"FMT": fmt.lower(), "DEST": dest}, body)


# ───────────────────────── ILLUSTRATOR: recolor + logo ─────────────────────────

def illustrator_recolor(hex_colors: list[str], use_selection: bool = False) -> str:
    colors = [_hex_to_rgb(h) for h in hex_colors] or [[0, 0, 0]]
    body = """
var ci = 0;
function applyColor(item){
  var tn = item.typename;
  if (tn === "PathItem") {
    if (item.filled) {
      var rgb = COLORS[ci % COLORS.length];
      var c = new RGBColor(); c.red = rgb[0]; c.green = rgb[1]; c.blue = rgb[2];
      item.fillColor = c; ci++;
    }
  } else if (tn === "CompoundPathItem") {
    var j; for (j = 0; j < item.pathItems.length; j++) { applyColor(item.pathItems[j]); }
  } else if (tn === "GroupItem") {
    var k; for (k = 0; k < item.pageItems.length; k++) { applyColor(item.pageItems[k]); }
  }
}
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento en Illustrator.";
  var doc = app.activeDocument;
  var items;
  if (USE_SELECTION && doc.selection && doc.selection.length > 0) items = doc.selection;
  else items = doc.pageItems;
  var i; for (i = 0; i < items.length; i++) { applyColor(items[i]); }
  app.redraw();
  return "OK: recoloreado (" + ci + " formas, " + COLORS.length + " colores)";
}
"""
    return _jsx({"COLORS": colors, "USE_SELECTION": use_selection}, body)


def illustrator_text_logo(text: str, font_size: float = 120, fill_hex: str = "#000000",
                          stroke_hex: str | None = None, stroke_width: float = 1.0,
                          font: str | None = None, new_doc: bool = True) -> str:
    body = """
function applyStroke(item, color, wdt){
  var tn = item.typename;
  if (tn === "PathItem") { item.stroked = true; item.strokeColor = color; item.strokeWidth = wdt; }
  else if (tn === "CompoundPathItem") { var j; for (j=0;j<item.pathItems.length;j++){ applyStroke(item.pathItems[j], color, wdt); } }
  else if (tn === "GroupItem") { var k; for (k=0;k<item.pageItems.length;k++){ applyStroke(item.pageItems[k], color, wdt); } }
}
function main(){
  var doc;
  if (NEW_DOC) doc = app.documents.add();
  else { try { doc = app.activeDocument; } catch(e){ doc = app.documents.add(); } }
  var tf = doc.textFrames.add();
  tf.contents = TEXT;
  var ca = tf.textRange.characterAttributes;
  ca.size = SIZE;
  if (FONT) { try { ca.textFont = app.textFonts.getByName(FONT); } catch(ef){} }
  var fc = new RGBColor(); fc.red = FILL[0]; fc.green = FILL[1]; fc.blue = FILL[2];
  ca.fillColor = fc;
  var grp = tf.createOutline();
  if (STROKE) {
    var sc = new RGBColor(); sc.red = STROKE[0]; sc.green = STROKE[1]; sc.blue = STROKE[2];
    applyStroke(grp, sc, STROKE_W);
  }
  var ab = doc.artboards[doc.artboards.getActiveArtboardIndex()];
  var r = ab.artboardRect; var abW = r[2]-r[0]; var abH = r[1]-r[3];
  var vb = grp.visibleBounds; var w = vb[2]-vb[0]; var h = vb[1]-vb[3];
  grp.position = [ r[0] + (abW - w)/2, r[1] - (abH - h)/2 ];
  app.redraw();
  return "OK: logo '" + TEXT + "' creado";
}
"""
    return _jsx({
        "TEXT": text, "SIZE": font_size, "FILL": _hex_to_rgb(fill_hex),
        "STROKE": _hex_to_rgb(stroke_hex) if stroke_hex else None,
        "STROKE_W": stroke_width, "FONT": font, "NEW_DOC": new_doc,
    }, body)


# ───────────────────────── PHOTOSHOP: batch + remove bg ─────────────────────────

def photoshop_batch(in_dir: str, out_dir: str, max_side: int = 1080,
                    fmt: str = "jpg", quality: int = 80) -> str:
    body = """
function main(){
  app.displayDialogs = DialogModes.NO;
  var inF = new Folder(IN_DIR);
  if (!inF.exists) return "ERROR: no existe la carpeta " + IN_DIR;
  var outF = new Folder(OUT_DIR);
  if (!outF.exists) outF.create();
  var files = inF.getFiles();
  var n = 0; var i;
  for (i = 0; i < files.length; i++) {
    var fl = files[i];
    if (!(fl instanceof File)) continue;
    if (!/\\.(jpe?g|png|tiff?|psd|bmp|webp|gif)$/i.test(fl.name)) continue;
    var d;
    try { d = app.open(fl); } catch(eo){ continue; }
    var w = d.width.as("px"); var h = d.height.as("px");
    var mx = Math.max(w, h);
    if (MAX_SIDE > 0 && mx > MAX_SIDE) {
      var s = MAX_SIDE / mx;
      d.resizeImage(UnitValue(w*s, "px"), UnitValue(h*s, "px"), d.resolution, ResampleMethod.BICUBICSHARPER);
    }
    var base = fl.name.replace(/\\.[^\\.]+$/, "");
    var ext = (FMT === "png") ? "png" : "jpg";
    var out = new File(OUT_DIR + "/" + base + "." + ext);
    var o;
    if (FMT === "png") { o = new ExportOptionsSaveForWeb(); o.format = SaveDocumentType.PNG; o.PNG8 = false; }
    else { o = new ExportOptionsSaveForWeb(); o.format = SaveDocumentType.JPEG; o.quality = QUALITY; }
    d.exportDocument(out, ExportType.SAVEFORWEB, o);
    d.close(SaveOptions.DONOTSAVECHANGES);
    n++;
  }
  return "OK: " + n + " imagenes procesadas en " + OUT_DIR;
}
"""
    return _jsx({"IN_DIR": in_dir, "OUT_DIR": out_dir, "MAX_SIDE": int(max_side),
                 "FMT": fmt.lower(), "QUALITY": int(quality)}, body)


def photoshop_remove_bg() -> str:
    body = """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento abierto en Photoshop.";
  app.displayDialogs = DialogModes.NO;
  var doc = app.activeDocument;
  try { if (doc.activeLayer.isBackgroundLayer) { doc.activeLayer.isBackgroundLayer = false; } } catch(eb){}
  var idautoCutout = stringIDToTypeID("autoCutout");
  var d = new ActionDescriptor();
  d.putBoolean(stringIDToTypeID("sampleAllLayers"), false);
  executeAction(idautoCutout, d, DialogModes.NO);
  var idMk = charIDToTypeID("Mk  ");
  var dm = new ActionDescriptor();
  dm.putClass(charIDToTypeID("Nw  "), charIDToTypeID("Chnl"));
  var rf = new ActionReference();
  rf.putEnumerated(charIDToTypeID("Chnl"), charIDToTypeID("Chnl"), charIDToTypeID("Msk "));
  dm.putReference(charIDToTypeID("At  "), rf);
  dm.putEnumerated(charIDToTypeID("Usng"), charIDToTypeID("UsrM"), charIDToTypeID("RvlS"));
  executeAction(idMk, dm, DialogModes.NO);
  try { doc.selection.deselect(); } catch(es){}
  return "OK: fondo recortado con mascara de capa";
}
"""
    return _jsx({}, body)


# ───────────────────────── INDESIGN: data merge ─────────────────────────

def indesign_data_merge(records: list[dict], margin: float = 36) -> str:
    body = """
function main(){
  if (RECORDS.length === 0) return "ERROR: el CSV no tiene registros.";
  var doc = app.documents.add();
  doc.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.POINTS;
  doc.viewPreferences.verticalMeasurementUnits = MeasurementUnits.POINTS;
  var i;
  for (i = 0; i < RECORDS.length; i++) {
    var page = (i === 0) ? doc.pages[0] : doc.pages.add();
    var rec = RECORDS[i];
    var b = page.bounds;  // [y1, x1, y2, x2]
    var tf = page.textFrames.add();
    tf.geometricBounds = [b[0] + MARGIN, b[1] + MARGIN, b[2] - MARGIN, b[3] - MARGIN];
    var s = ""; var k;
    for (k in rec) { if (rec.hasOwnProperty(k)) { s += k + ": " + rec[k] + "\\r"; } }
    tf.contents = s;
  }
  return "OK: " + RECORDS.length + " registros maquetados (1 por pagina)";
}
"""
    return _jsx({"RECORDS": records, "MARGIN": margin}, body)


def illustrator_place_trace(image_path: str, outline: bool = True, new_doc: bool = True,
                            keep_image: bool = True, preset: str | None = None,
                            embed: bool = False) -> str:
    """
    Coloca una imagen en un documento, la centra/escala al artboard,
    le aplica Image Trace (calco de imagen) y la expande a vectores.

    outline=True     → trazo (sin relleno, stroke negro). Se ignora si el preset es de color.
    outline=False    → conserva los rellenos del trazado.
    new_doc=True      → documento limpio; False → usa el activo.
    keep_image=True   → conserva la imagen original y deja el resultado ENCIMA.
    preset            → clave de TRACE_PRESETS (ej 'low_fidelity_photo'). None = manual.
    embed=True        → incrusta la imagen conservada en el documento.
    """
    p = _esc(image_path)
    trace_mode = "TracingModeType.TRACINGMODEBLACKANDWHITE" if outline else "TracingModeType.TRACINGMODECOLOR"
    candidates = TRACE_PRESETS.get((preset or "").lower(), [])
    return f'''
var IMG_PATH = "{p}";
var OUTLINE = {"true" if outline else "false"};
var NEW_DOC = {"true" if new_doc else "false"};
var KEEP_IMAGE = {"true" if keep_image else "false"};
var EMBED = {"true" if embed else "false"};
var PRESET_CANDS = {json.dumps(candidates)};

function findPreset(cands) {{
    if (!cands || cands.length === 0) return null;
    var list;
    try {{ list = app.tracingPresetsList; }} catch (e) {{ return null; }}
    if (!list) return null;
    var i, j;
    for (i = 0; i < cands.length; i++) {{
        var c = String(cands[i]).toLowerCase();
        for (j = 0; j < list.length; j++) {{
            if (String(list[j]).toLowerCase().indexOf(c) !== -1) {{ return list[j]; }}
        }}
    }}
    return null;
}}

function stylePaths(item, color) {{
    var tn = item.typename;
    if (tn === "PathItem") {{
        item.filled = false;
        item.stroked = true;
        item.strokeColor = color;
        item.strokeWidth = 0.75;
    }} else if (tn === "CompoundPathItem") {{
        var j;
        for (j = 0; j < item.pathItems.length; j++) {{ stylePaths(item.pathItems[j], color); }}
    }} else if (tn === "GroupItem") {{
        var k;
        for (k = 0; k < item.pageItems.length; k++) {{ stylePaths(item.pageItems[k], color); }}
    }}
}}

function main() {{
    var doc;
    if (NEW_DOC) {{ doc = app.documents.add(); }}
    else {{ try {{ doc = app.activeDocument; }} catch (e) {{ doc = app.documents.add(); }} }}

    var f = new File(IMG_PATH);
    if (!f.exists) {{ return "ERROR: no existe la imagen: " + IMG_PATH; }}

    var placed = doc.placedItems.add();
    placed.file = f;

    // Centrar y escalar al artboard activo (al 80%)
    var ab = doc.artboards[doc.artboards.getActiveArtboardIndex()];
    var r = ab.artboardRect;          // [left, top, right, bottom]
    var abW = r[2] - r[0];
    var abH = r[1] - r[3];
    var iw = placed.width, ih = placed.height;
    if (iw > 0 && ih > 0) {{
        var scale = Math.min(abW / iw, abH / ih) * 0.8;
        if (scale > 0 && scale < 50) {{ placed.width = iw * scale; placed.height = ih * scale; }}
    }}
    placed.position = [r[0] + (abW - placed.width) / 2, r[1] - (abH - placed.height) / 2];

    // Trazamos una copia si hay que conservar la imagen; si no, la imagen misma.
    var target = KEEP_IMAGE ? placed.duplicate() : placed;

    // Image Trace
    var traceArt = target.trace();    // PluginItem
    var tracing = traceArt.tracing;

    var presetName = findPreset(PRESET_CANDS);
    if (presetName !== null) {{
        try {{ tracing.tracingOptions.loadFromPreset(presetName); }} catch (ep) {{ presetName = null; }}
    }}
    if (presetName === null) {{
        // Ajustes manuales si no hubo preset
        try {{ tracing.tracingOptions.tracingMode = {trace_mode}; }} catch (e1) {{}}
        try {{ tracing.tracingOptions.pathFidelity = 90; }} catch (e2) {{}}
        try {{ tracing.tracingOptions.cornerFidelity = 75; }} catch (e3) {{}}
        try {{ tracing.tracingOptions.noiseFidelity = 25; }} catch (e4) {{}}
    }}

    var grp = tracing.expandTracing();   // GroupItem con los paths

    if (OUTLINE) {{
        var black = new RGBColor();
        black.red = 0; black.green = 0; black.blue = 0;
        stylePaths(grp, black);
    }}

    if (KEEP_IMAGE) {{ try {{ grp.zOrder(ZOrderMethod.BRINGTOFRONT); }} catch (ez) {{}} }}

    // Incrustar la imagen conservada al final (evita choques con el motor de calco)
    if (EMBED && KEEP_IMAGE) {{ try {{ placed.embed(); }} catch (ee) {{}} }}

    app.redraw();
    var label = presetName !== null ? presetName : (OUTLINE ? "trazo" : "color");
    return "OK: calco aplicado (" + label + (KEEP_IMAGE ? ", sobre la imagen" : "") + ")";
}}

var __result;
try {{ __result = main(); }} catch (e) {{ __result = "ERROR: " + e.toString(); }}
__result;
'''
