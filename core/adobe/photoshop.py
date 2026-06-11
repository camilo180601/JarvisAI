# -*- coding: utf-8 -*-
"""adobe/photoshop.py — operaciones de Photoshop (ps_*)."""
from __future__ import annotations
from core.adobe_templates import _jsx, _hex_to_rgb, _esc


def ps_new_doc(w: int = 1920, h: int = 1080, res: int = 72) -> str:
    return _jsx({"W": int(w), "H": int(h), "RES": int(res)}, """
function main(){
  app.documents.add(UnitValue(W,"px"), UnitValue(H,"px"), RES, "JARVIS", NewDocumentMode.RGB);
  return "OK: documento " + W + "x" + H + " creado";
}""")


def ps_resize(max_side: int | None, w: int | None, h: int | None) -> str:
    return _jsx({"MAX": max_side, "W": w, "H": h}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  app.displayDialogs = DialogModes.NO;
  var d = app.activeDocument;
  var cw = d.width.as("px"), ch = d.height.as("px");
  var nw = cw, nh = ch;
  if (MAX !== null){ var s = MAX/Math.max(cw,ch); if (s<1){ nw=cw*s; nh=ch*s; } }
  else { if (W!==null) nw=W; if (H!==null) nh=H; }
  d.resizeImage(UnitValue(nw,"px"), UnitValue(nh,"px"), d.resolution, ResampleMethod.BICUBICSHARPER);
  return "OK: redimensionado a " + Math.round(nw) + "x" + Math.round(nh);
}""")


def ps_crop(box: list) -> str:
    return _jsx({"BOX": [int(x) for x in box]}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  app.activeDocument.crop(BOX);
  return "OK: recortado";
}""")


def ps_adjust(kind: str, value: float = 0) -> str:
    return _jsx({"KIND": kind.lower(), "VAL": value}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  app.displayDialogs = DialogModes.NO;
  var lyr = app.activeDocument.activeLayer;
  if (KIND==="bw"||KIND==="grayscale"||KIND==="blanco_negro") lyr.desaturate();
  else if (KIND==="brightness"||KIND==="brillo") lyr.adjustBrightnessContrast(VAL, 0);
  else if (KIND==="contrast"||KIND==="contraste") lyr.adjustBrightnessContrast(0, VAL);
  else if (KIND==="blur"||KIND==="desenfoque") lyr.applyGaussianBlur(VAL>0?VAL:5);
  else if (KIND==="sharpen"||KIND==="enfoque") lyr.applySharpen();
  else return "ERROR: ajuste '" + KIND + "' no soportado";
  return "OK: ajuste " + KIND + " aplicado";
}""")


def ps_text_layer(text: str, size: float = 72, fill_hex: str = "#000000") -> str:
    return _jsx({"TEXT": text, "SIZE": size, "FILL": _hex_to_rgb(fill_hex)}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var lyr = d.artLayers.add();
  lyr.kind = LayerKind.TEXT;
  var t = lyr.textItem;
  t.contents = TEXT;
  t.size = SIZE;
  var c = new SolidColor(); c.rgb.red=FILL[0]; c.rgb.green=FILL[1]; c.rgb.blue=FILL[2];
  t.color = c;
  t.position = [d.width.as("px")*0.1, d.height.as("px")*0.5];
  return "OK: capa de texto agregada";
}""")


def ps_flatten() -> str:
    return _jsx({}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  app.activeDocument.flatten();
  return "OK: documento aplanado";
}""")


def ps_export_layers(dest_dir: str) -> str:
    return _jsx({"DIR": dest_dir}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  app.displayDialogs = DialogModes.NO;
  var d = app.activeDocument;
  var folder = new Folder(DIR); if (!folder.exists) folder.create();
  var opts = new ExportOptionsSaveForWeb(); opts.format = SaveDocumentType.PNG; opts.PNG8 = false;
  // ocultar todas
  for (var i=0;i<d.artLayers.length;i++){ try { d.artLayers[i].visible = false; } catch(e){} }
  var n = 0;
  for (var j=0;j<d.artLayers.length;j++){
    var L = d.artLayers[j];
    try {
      L.visible = true;
      var name = L.name.replace(/[^\\w-]/g,"_");
      d.exportDocument(new File(DIR + "/" + name + ".png"), ExportType.SAVEFORWEB, opts);
      L.visible = false; n++;
    } catch(e){}
  }
  return "OK: " + n + " capa(s) exportadas a " + DIR;
}""")


def ps_filter(kind: str, amount: float = 0, angle: float = 0) -> str:
    """Aplica un filtro a la capa activa: blur | motion | sharpen | noise | pixelate."""
    return _jsx({"KIND": kind.lower(), "AMOUNT": float(amount), "ANGLE": float(angle)}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  app.displayDialogs = DialogModes.NO;
  var L = app.activeDocument.activeLayer;
  if (KIND==="blur"||KIND==="desenfoque") L.applyGaussianBlur(AMOUNT>0?AMOUNT:8);
  else if (KIND==="motion"||KIND==="movimiento") L.applyMotionBlur(ANGLE, AMOUNT>0?AMOUNT:25);
  else if (KIND==="sharpen"||KIND==="enfoque") L.applySharpen();
  else if (KIND==="noise"||KIND==="ruido") L.applyAddNoise(AMOUNT>0?AMOUNT:12, NoiseDistribution.GAUSSIAN, false);
  else if (KIND==="pixelate"||KIND==="pixelar") L.applyPixelate(AMOUNT>0?AMOUNT:8);
  else return "ERROR: filtro '" + KIND + "' no soportado (blur|motion|sharpen|noise|pixelate)";
  return "OK: filtro " + KIND + " aplicado";
}""")


def ps_adjust2(kind: str, value: float = 0) -> str:
    """Ajustes extra de Photoshop: invert | posterize | threshold."""
    return _jsx({"KIND": kind.lower(), "VAL": float(value)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.displayDialogs=DialogModes.NO;
  var L=app.activeDocument.activeLayer;
  if (KIND==="invert"||KIND==="invertir") L.invert();
  else if (KIND==="posterize"||KIND==="posterizar") L.posterize(VAL>1?VAL:4);
  else if (KIND==="threshold"||KIND==="umbral") L.threshold(VAL>0?VAL:128);
  else return "ERROR: ajuste '"+KIND+"' no soportado (invert|posterize|threshold)";
  return "OK: "+KIND+" aplicado";
}""")


def ps_canvas(mode: str = "trim", width: int | None = None, height: int | None = None) -> str:
    """Lienzo de Photoshop: trim (recorta transparente) | resize (redimensiona el lienzo)."""
    return _jsx({"MODE": mode.lower(), "W": width, "H": height}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.displayDialogs=DialogModes.NO;
  var d=app.activeDocument;
  if (MODE==="trim"||MODE==="recortar"){ d.trim(TrimType.TRANSPARENT); return "OK: lienzo recortado"; }
  if (MODE==="resize"||MODE==="redimensionar"){
    var w=(W!==null)?W:d.width.as("px"), h=(H!==null)?H:d.height.as("px");
    d.resizeCanvas(UnitValue(w,"px"), UnitValue(h,"px"), AnchorPosition.MIDDLECENTER);
    return "OK: lienzo a "+w+"x"+h;
  }
  return "ERROR: mode trim | resize";
}""")


def ps_rotate_canvas(degrees: float = 90) -> str:
    """Rota el lienzo de Photoshop N grados."""
    return _jsx({"DEG": float(degrees)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.activeDocument.rotateCanvas(DEG);
  return "OK: lienzo rotado "+DEG+"°";
}""")


def ps_fill(hex_color: str = "#ffffff") -> str:
    """Rellena la capa activa (o la selección) con un color sólido."""
    return _jsx({"COL": _hex_to_rgb(hex_color)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.displayDialogs=DialogModes.NO;
  var d=app.activeDocument;
  var col=new SolidColor(); col.rgb.red=COL[0]; col.rgb.green=COL[1]; col.rgb.blue=COL[2];
  var hadSel=true;
  try { var b=d.selection.bounds; } catch(e){ hadSel=false; }
  if (!hadSel) d.selection.selectAll();
  d.selection.fill(col);
  d.selection.deselect();
  return "OK: relleno aplicado";
}""")


def ps_layer_style(kind: str = "drop_shadow", hex_color: str = "#000000",
                   size: float = 10, opacity: float = 75, angle: float = 120,
                   distance: float = 8) -> str:
    """Estilo de capa en Photoshop: drop_shadow (sombra) | stroke (borde) | glow (resplandor)."""
    return _jsx({"KIND": kind.lower(), "COL": _hex_to_rgb(hex_color), "SZ": float(size),
                 "OP": float(opacity), "ANG": float(angle), "DST": float(distance)}, """
function cid(s){ return charIDToTypeID(s); }
function colorDesc(){ var c=new ActionDescriptor();
  c.putDouble(cid("Rd  "),COL[0]); c.putDouble(cid("Grn "),COL[1]); c.putDouble(cid("Bl  "),COL[2]); return c; }
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.displayDialogs=DialogModes.NO;
  var desc=new ActionDescriptor();
  var ref=new ActionReference();
  ref.putProperty(cid("Prpr"),cid("Lefx"));
  ref.putEnumerated(cid("Lyr "),cid("Ordn"),cid("Trgt"));
  desc.putReference(cid("null"),ref);
  var lfx=new ActionDescriptor();
  lfx.putUnitDouble(cid("Scl "),cid("#Prc"),100);
  if (KIND==="drop_shadow"||KIND==="sombra"){
    var ds=new ActionDescriptor();
    ds.putBoolean(cid("enab"),true);
    ds.putEnumerated(cid("Md  "),cid("BlnM"),cid("Mltp"));
    ds.putObject(cid("Clr "),cid("RGBC"),colorDesc());
    ds.putUnitDouble(cid("Opct"),cid("#Prc"),OP);
    ds.putBoolean(cid("uglg"),true);
    ds.putUnitDouble(cid("lagl"),cid("#Ang"),ANG);
    ds.putUnitDouble(cid("Dstn"),cid("#Pxl"),DST);
    ds.putUnitDouble(cid("blur"),cid("#Pxl"),SZ);
    lfx.putObject(cid("DrSh"),cid("DrSh"),ds);
  } else if (KIND==="stroke"||KIND==="borde"){
    var fx=new ActionDescriptor();
    fx.putBoolean(cid("enab"),true);
    fx.putEnumerated(cid("Styl"),cid("FStl"),cid("OutF"));
    fx.putEnumerated(cid("PntT"),cid("FrFl"),cid("SClr"));
    fx.putUnitDouble(cid("Opct"),cid("#Prc"),100);
    fx.putUnitDouble(cid("Sz  "),cid("#Pxl"),SZ);
    fx.putObject(cid("Clr "),cid("RGBC"),colorDesc());
    lfx.putObject(cid("FrFX"),cid("FrFX"),fx);
  } else if (KIND==="glow"||KIND==="resplandor"){
    var og=new ActionDescriptor();
    og.putBoolean(cid("enab"),true);
    og.putEnumerated(cid("Md  "),cid("BlnM"),cid("Scrn"));
    og.putUnitDouble(cid("Opct"),cid("#Prc"),OP);
    og.putObject(cid("Clr "),cid("RGBC"),colorDesc());
    og.putUnitDouble(cid("blur"),cid("#Pxl"),SZ);
    lfx.putObject(cid("OrGl"),cid("OrGl"),og);
  } else return "ERROR: estilo '"+KIND+"' (drop_shadow|stroke|glow)";
  desc.putObject(cid("T   "),cid("Lefx"),lfx);
  executeAction(cid("setd"),desc,DialogModes.NO);
  return "OK: estilo "+KIND+" aplicado";
}""")


def ps_place(image_path: str) -> str:
    """Coloca una imagen como capa (objeto inteligente) en el documento de Photoshop."""
    return _jsx({"PATH": image_path}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento (creá uno primero).";
  var f = new File(PATH);
  if (!f.exists) return "ERROR: no existe " + PATH;
  app.displayDialogs=DialogModes.NO;
  var desc=new ActionDescriptor();
  desc.putPath(charIDToTypeID("null"), f);
  desc.putEnumerated(charIDToTypeID("FTcs"), charIDToTypeID("QCSt"), charIDToTypeID("Qcsa"));
  executeAction(charIDToTypeID("Plc "), desc, DialogModes.NO);
  return "OK: imagen colocada como capa";
}""")


_PS_BLEND = {
    "normal": "NORMAL", "multiply": "MULTIPLY", "multiplicar": "MULTIPLY",
    "screen": "SCREEN", "trama": "SCREEN", "overlay": "OVERLAY", "superponer": "OVERLAY",
    "darken": "DARKEN", "oscurecer": "DARKEN", "lighten": "LIGHTEN", "aclarar": "LIGHTEN",
    "softlight": "SOFTLIGHT", "soft_light": "SOFTLIGHT", "luz_suave": "SOFTLIGHT",
    "hardlight": "HARDLIGHT", "hard_light": "HARDLIGHT", "luz_fuerte": "HARDLIGHT",
    "difference": "DIFFERENCE", "diferencia": "DIFFERENCE", "color": "COLOR",
    "luminosity": "LUMINOSITY", "luminosidad": "LUMINOSITY",
    "colordodge": "COLORDODGE", "colorburn": "COLORBURN",
}


def ps_blend_mode(mode: str = "multiply") -> str:
    """Cambia el modo de fusión de la capa activa."""
    bm = _PS_BLEND.get((mode or "").lower().replace(" ", "_"), "NORMAL")
    return _jsx({"BM": bm}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  try { d.activeLayer.blendMode = BlendMode[BM]; }
  catch(e){ return "ERROR: " + e.toString(); }
  return "OK: modo de fusión " + BM;
}""")


def ps_layer_opacity(value: float = 100) -> str:
    """Ajusta la opacidad de la capa activa (0-100)."""
    return _jsx({"V": max(0.0, min(100.0, float(value)))}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  try { if (d.activeLayer.isBackgroundLayer) d.activeLayer.isBackgroundLayer = false; } catch(eb){}
  d.activeLayer.opacity = V;
  return "OK: opacidad " + V + "%";
}""")


def ps_duplicate_layer() -> str:
    """Duplica la capa activa en Photoshop."""
    return _jsx({}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.activeDocument.activeLayer.duplicate();
  return "OK: capa duplicada";
}""")


def ps_new_layer(name: str = "Capa") -> str:
    """Crea una capa nueva vacía en Photoshop."""
    return _jsx({"NM": name}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var l = app.activeDocument.artLayers.add();
  l.name = NM;
  return "OK: capa '" + NM + "' creada";
}""")


def ps_hue_saturation(hue: float = 0, saturation: float = 0, lightness: float = 0) -> str:
    """Ajusta tono/saturación/luminosidad de la capa activa (-180..180 hue, -100..100 resto).
    Vía Action Manager (no hay método DOM para esto)."""
    return _jsx({"H": int(hue), "S": int(saturation), "L": int(lightness)}, """
function cid(s){ return charIDToTypeID(s); }
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.displayDialogs=DialogModes.NO;
  var lyr = app.activeDocument.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (lyr.kind !== LayerKind.NORMAL) { try { lyr.rasterize(RasterizeType.ENTIRELAYER); } catch(er){} }
  var desc = new ActionDescriptor();
  desc.putBoolean(cid("Clrz"), false);
  var list = new ActionList();
  var ch = new ActionDescriptor();
  ch.putEnumerated(cid("Chnl"), cid("Chnl"), cid("Cmps"));
  ch.putInteger(cid("H   "), H);
  ch.putInteger(cid("Strt"), S);
  ch.putInteger(cid("Lght"), L);
  list.putObject(cid("Hst2"), ch);
  desc.putList(cid("Adjs"), list);
  executeAction(cid("HStr"), desc, DialogModes.NO);
  return "OK: tono " + H + " / sat " + S + " / luz " + L;
}""")


def ps_rasterize() -> str:
    """Rasteriza la capa activa (texto/forma/objeto inteligente → píxeles)."""
    return _jsx({}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.activeDocument.activeLayer.rasterize(RasterizeType.ENTIRELAYER);
  return "OK: capa rasterizada";
}""")


def ps_transform_layer(rotate: float = 0, scale: float = 100,
                       dx: float = 0, dy: float = 0) -> str:
    """Rota / escala (%) / mueve (px) la capa activa, desde su centro."""
    return _jsx({"ROT": float(rotate), "SC": float(scale), "DX": float(dx), "DY": float(dy)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var lyr = app.activeDocument.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (SC !== 100) lyr.resize(SC, SC, AnchorPosition.MIDDLECENTER);
  if (ROT !== 0) lyr.rotate(ROT, AnchorPosition.MIDDLECENTER);
  if (DX !== 0 || DY !== 0) lyr.translate(UnitValue(DX,"px"), UnitValue(DY,"px"));
  return "OK: capa transformada (rot " + ROT + ", esc " + SC + "%, mov " + DX + "/" + DY + ")";
}""")


def ps_levels(black: int = 0, white: int = 255, gamma: float = 1.0) -> str:
    """Ajuste de niveles en la capa activa de Photoshop (entrada negro/blanco + gamma)."""
    return _jsx({"BLK": int(black), "WHT": int(white), "GAM": float(gamma)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var lyr = app.activeDocument.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (lyr.kind !== LayerKind.NORMAL) { try { lyr.rasterize(RasterizeType.ENTIRELAYER); } catch(er){} }
  lyr.adjustLevels(BLK, WHT, GAM, 0, 255);
  return "OK: niveles (" + BLK + "/" + GAM + "/" + WHT + ")";
}""")


def ps_color_balance(shadows: list | None = None, midtones: list | None = None,
                     highlights: list | None = None) -> str:
    """Balance de color por sombras/medios/luces. Cada uno: [cian-rojo, magenta-verde, amarillo-azul] (-100..100)."""
    sh = [int(v) for v in (shadows or [0, 0, 0])][:3] or [0, 0, 0]
    mi = [int(v) for v in (midtones or [0, 0, 0])][:3] or [0, 0, 0]
    hi = [int(v) for v in (highlights or [0, 0, 0])][:3] or [0, 0, 0]
    while len(sh) < 3: sh.append(0)
    while len(mi) < 3: mi.append(0)
    while len(hi) < 3: hi.append(0)
    return _jsx({"SH": sh, "MI": mi, "HI": hi}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var lyr = app.activeDocument.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (lyr.kind !== LayerKind.NORMAL) { try { lyr.rasterize(RasterizeType.ENTIRELAYER); } catch(er){} }
  lyr.adjustColorBalance(SH, MI, HI, true);
  return "OK: balance de color aplicado";
}""")


def ps_clipping_mask() -> str:
    """Recorta la capa activa con la capa de abajo (clipping mask)."""
    return _jsx({}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  try { app.activeDocument.activeLayer.grouped = true; }
  catch(e){ return "ERROR: necesitás una capa debajo para recortar (" + e.toString() + ")"; }
  return "OK: capa recortada con la de abajo";
}""")


def ps_flip(target: str = "layer", axis: str = "horizontal") -> str:
    """Voltea la capa activa o el lienzo, horizontal o vertical."""
    return _jsx({"TARGET": (target or "layer").lower(), "AX": (axis or "horizontal").lower()}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  if (TARGET === "canvas" || TARGET === "lienzo") {
    d.flipCanvas(AX === "vertical" ? Direction.VERTICAL : Direction.HORIZONTAL);
    return "OK: lienzo volteado " + AX;
  }
  var lyr = d.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (AX === "vertical") lyr.resize(100, -100, AnchorPosition.MIDDLECENTER);
  else lyr.resize(-100, 100, AnchorPosition.MIDDLECENTER);
  return "OK: capa volteada " + AX;
}""")


def ps_curves(points: list | None = None) -> str:
    """Ajuste de curvas en la capa activa. points = lista de pares [entrada, salida] (0-255).
    Por defecto, una curva en S suave (más contraste)."""
    pts = points or [[0, 0], [64, 48], [128, 128], [192, 208], [255, 255]]
    pts = [[int(a), int(b)] for a, b in pts]
    return _jsx({"PTS": pts}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var lyr = app.activeDocument.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (lyr.kind !== LayerKind.NORMAL) { try { lyr.rasterize(RasterizeType.ENTIRELAYER); } catch(er){} }
  lyr.adjustCurves(PTS);
  return "OK: curvas aplicadas (" + PTS.length + " puntos)";
}""")


def ps_smart_object() -> str:
    """Convierte la capa activa en objeto inteligente (edición no destructiva)."""
    return _jsx({}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.displayDialogs = DialogModes.NO;
  executeAction(stringIDToTypeID("newPlacedLayer"), undefined, DialogModes.NO);
  return "OK: capa convertida en objeto inteligente";
}""")


_PS_PHOTO_FILTER = {"warm": [236, 138, 0], "calido": [236, 138, 0], "cálido": [236, 138, 0],
                    "cool": [0, 181, 255], "frio": [0, 181, 255], "frío": [0, 181, 255]}


def ps_photo_filter(color: str = "warm", density: float = 25) -> str:
    """Filtro de foto (temperatura de color) sobre la capa activa. color = warm|cool|hex.
    Implementado con balance de color (Photo Filter como evento directo no existe en todas las versiones)."""
    rgb = _PS_PHOTO_FILTER.get((color or "").lower(), _hex_to_rgb(color) if color else [236, 138, 0])
    scale = max(0.0, min(100.0, float(density))) / 100.0
    # Ejes del balance: [cian-rojo, magenta-verde, amarillo-azul]. Empujar hacia el color objetivo.
    avg = sum(rgb) / 3.0
    vec = [int(round((c - avg) / 128.0 * 100 * scale)) for c in rgb]
    vec = [max(-100, min(100, v)) for v in vec]
    mid = vec
    sh = [int(v * 0.5) for v in vec]
    hi = [int(v * 0.5) for v in vec]
    return _jsx({"SH": sh, "MI": mid, "HI": hi}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var lyr = app.activeDocument.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (lyr.kind !== LayerKind.NORMAL) { try { lyr.rasterize(RasterizeType.ENTIRELAYER); } catch(er){} }
  lyr.adjustColorBalance(SH, MI, HI, true);
  return "OK: filtro de foto aplicado (tinte)";
}""")


def ps_auto(mode: str = "contrast") -> str:
    """Auto niveles o auto contraste de la capa activa en Photoshop (un clic)."""
    return _jsx({"MODE": (mode or "contrast").lower()}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var lyr = app.activeDocument.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (lyr.kind !== LayerKind.NORMAL) { try { lyr.rasterize(RasterizeType.ENTIRELAYER); } catch(er){} }
  if (MODE === "levels" || MODE === "niveles") lyr.autoLevels();
  else lyr.autoContrast();
  return "OK: auto " + MODE;
}""")


def ps_layer_mask(reveal: bool = True) -> str:
    """Agrega una máscara de capa (reveal=blanco muestra todo, hide=negro oculta todo)."""
    return _jsx({"REVEAL": bool(reveal)}, """
function cid(s){ return charIDToTypeID(s); }
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.displayDialogs = DialogModes.NO;
  var desc = new ActionDescriptor();
  desc.putClass(cid("Nw  "), cid("Chnl"));
  var ref = new ActionReference();
  ref.putEnumerated(cid("Chnl"), cid("Chnl"), cid("Msk "));
  desc.putReference(cid("At  "), ref);
  desc.putEnumerated(cid("Usng"), cid("UsrM"), REVEAL ? cid("RvlA") : cid("HdAl"));
  executeAction(cid("Mk  "), desc, DialogModes.NO);
  return "OK: máscara de capa agregada (" + (REVEAL ? "revelar" : "ocultar") + ")";
}""")


def ps_black_white(tint_hex: str | None = None) -> str:
    """Convierte la capa activa a blanco y negro, con tinte opcional (look duotono)."""
    vec = None
    if tint_hex:
        rgb = _hex_to_rgb(tint_hex)
        avg = sum(rgb) / 3.0
        vec = [max(-100, min(100, int(round((c - avg) / 128.0 * 100)))) for c in rgb]
    return _jsx({"TINT": vec}, """
function cid(s){ return charIDToTypeID(s); }
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.displayDialogs = DialogModes.NO;
  var lyr = app.activeDocument.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (lyr.kind !== LayerKind.NORMAL) { try { lyr.rasterize(RasterizeType.ENTIRELAYER); } catch(er){} }
  // Desaturar vía Hue/Saturation (sat -100): más confiable que desaturate() headless.
  var desc = new ActionDescriptor();
  desc.putBoolean(cid("Clrz"), false);
  var list = new ActionList();
  var ch = new ActionDescriptor();
  ch.putEnumerated(cid("Chnl"), cid("Chnl"), cid("Cmps"));
  ch.putInteger(cid("H   "), 0);
  ch.putInteger(cid("Strt"), -100);
  ch.putInteger(cid("Lght"), 0);
  list.putObject(cid("Hst2"), ch);
  desc.putList(cid("Adjs"), list);
  executeAction(cid("HStr"), desc, DialogModes.NO);
  if (TINT) { lyr.adjustColorBalance(TINT, TINT, TINT, true); }
  return "OK: blanco y negro" + (TINT ? " con tinte" : "");
}""")


def ps_lens_flare(brightness: float = 120) -> str:
    """Aplica un destello de lente (lens flare) al centro de la capa activa."""
    return _jsx({"BR": float(brightness)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var doc = app.activeDocument;
  var lyr = doc.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (lyr.kind !== LayerKind.NORMAL) { try { lyr.rasterize(RasterizeType.ENTIRELAYER); } catch(er){} }
  var w = doc.width.as("px"), h = doc.height.as("px");
  lyr.applyLensFlare(BR, [UnitValue(w/2,"px"), UnitValue(h/2,"px")], LensType.ZOOMLENS);
  return "OK: destello de lente aplicado";
}""")


def ps_distort(kind: str = "twirl", amount: float = 50) -> str:
    """Distorsión sobre la capa activa: twirl | spherize | pinch | ripple."""
    return _jsx({"KIND": (kind or "twirl").lower(), "AMT": float(amount)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var lyr = app.activeDocument.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (lyr.kind !== LayerKind.NORMAL) { try { lyr.rasterize(RasterizeType.ENTIRELAYER); } catch(er){} }
  if (KIND === "twirl" || KIND === "remolino") lyr.applyTwirl(AMT);
  else if (KIND === "spherize" || KIND === "esfera") lyr.applySpherize(AMT, SpherizeMode.NORMAL);
  else if (KIND === "pinch" || KIND === "pellizco") lyr.applyPinch(AMT);
  else if (KIND === "ripple" || KIND === "onda") lyr.applyRipple(AMT, RippleSize.MEDIUM);
  else return "ERROR: distorsión '" + KIND + "' (twirl|spherize|pinch|ripple)";
  return "OK: distorsión " + KIND + " (" + AMT + ")";
}""")


def ps_unsharp(amount: float = 100, radius: float = 1.5, threshold: int = 2) -> str:
    """Enfoque (máscara de enfoque) en la capa activa de Photoshop."""
    return _jsx({"AMT": float(amount), "RAD": float(radius), "THR": int(threshold)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var lyr = app.activeDocument.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (lyr.kind !== LayerKind.NORMAL) { try { lyr.rasterize(RasterizeType.ENTIRELAYER); } catch(er){} }
  lyr.applyUnSharpMask(AMT, RAD, THR);
  return "OK: enfoque aplicado (" + AMT + "%)";
}""")


_PS_JUST = {"left": "LEFT", "izquierda": "LEFT", "center": "CENTER", "centro": "CENTER",
            "right": "RIGHT", "derecha": "RIGHT", "justify": "FULLYJUSTIFIED", "justificado": "FULLYJUSTIFIED"}


def ps_text_styled(text: str = "", size: float = 72, hex_color: str = "#000000",
                   font: str | None = None, tracking: float | None = None, leading: float = 0,
                   align: str = "left", x: float | None = None, y: float | None = None,
                   box: bool = False, box_w: float = 600, box_h: float = 200) -> str:
    """Capa de texto estilizada en Photoshop (fuente, color, tracking, interlineado, alineación, caja opcional)."""
    j = _PS_JUST.get((align or "").lower(), "LEFT")
    return _jsx({"TXT": text, "SZ": float(size), "FILL": _hex_to_rgb(hex_color), "FONT": font,
                 "TRACK": (None if tracking is None else float(tracking)), "LEAD": float(leading),
                 "J": j, "X": (None if x is None else float(x)), "Y": (None if y is None else float(y)),
                 "BOX": bool(box), "BW": float(box_w), "BH": float(box_h)}, """
function main(){
  var doc = (app.documents.length) ? app.activeDocument : app.documents.add(UnitValue(800,"px"), UnitValue(600,"px"), 72);
  app.displayDialogs = DialogModes.NO;
  var lyr = doc.artLayers.add(); lyr.kind = LayerKind.TEXT;
  var ti = lyr.textItem;
  ti.contents = TXT;
  ti.size = SZ;
  var c = new SolidColor(); c.rgb.red=FILL[0]; c.rgb.green=FILL[1]; c.rgb.blue=FILL[2]; ti.color = c;
  if (FONT) { try { ti.font = FONT; } catch(e){} }
  if (TRACK !== null) ti.tracking = TRACK;
  if (LEAD > 0) { ti.useAutoLeading = false; ti.leading = LEAD; }
  try { ti.justification = Justification[J]; } catch(ej){}
  var w = doc.width.as("px"), h = doc.height.as("px");
  if (BOX) { ti.kind = TextType.PARAGRAPHTEXT; ti.width = UnitValue(BW,"px"); ti.height = UnitValue(BH,"px"); }
  var px = (X === null) ? w/2 : X, py = (Y === null) ? h/2 : Y;
  ti.position = [UnitValue(px,"px"), UnitValue(py,"px")];
  return "OK: texto estilizado agregado";
}""")


_PS_WARP = {"arc": "ARC", "arch": "ARCH", "arco": "ARC", "bulge": "BULGE", "abultar": "BULGE",
            "flag": "FLAG", "bandera": "FLAG", "wave": "WAVE", "onda": "WAVE", "fish": "FISH",
            "rise": "RISE", "fisheye": "FISHEYE", "inflate": "INFLATE", "inflar": "INFLATE",
            "squeeze": "SQUEEZE", "twist": "TWIST", "shellupper": "SHELLUPPER", "shelllower": "SHELLLOWER"}


def ps_warp_text(style: str = "arc", bend: float = 0.5) -> str:
    """Deforma el texto de la capa activa en Photoshop. style: arc/flag/wave/fish/rise/bulge/arch/... bend -1..1."""
    st = _PS_WARP.get((style or "").lower(), "ARC")
    return _jsx({"STYLE": st, "BEND": max(-1.0, min(1.0, float(bend)))}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var lyr = app.activeDocument.activeLayer;
  if (lyr.kind !== LayerKind.TEXT) return "ERROR: la capa activa no es de texto.";
  var ti = lyr.textItem;
  ti.warpStyle = WarpStyle[STYLE];
  ti.warpBend = BEND;
  return "OK: texto deformado (" + STYLE + ")";
}""")


def ps_font(font: str | None = None, size: float = 0, tracking: float | None = None,
            leading: float = 0) -> str:
    """Cambia fuente/tamaño/tracking/interlineado de la capa de texto activa en Photoshop."""
    return _jsx({"FONT": font, "SZ": float(size), "TRACK": (None if tracking is None else float(tracking)),
                 "LEAD": float(leading)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var lyr = app.activeDocument.activeLayer;
  if (lyr.kind !== LayerKind.TEXT) return "ERROR: la capa activa no es de texto.";
  var ti = lyr.textItem;
  if (SZ > 0) ti.size = SZ;
  if (FONT) { try { ti.font = FONT; } catch(e){} }
  if (TRACK !== null) ti.tracking = TRACK;
  if (LEAD > 0) { ti.useAutoLeading = false; ti.leading = LEAD; }
  return "OK: tipografía aplicada a la capa de texto";
}""")


def ps_text_align(align: str = "left") -> str:
    """Alineación del párrafo de la capa de texto activa en Photoshop."""
    j = _PS_JUST.get((align or "").lower(), "LEFT")
    return _jsx({"J": j}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var lyr = app.activeDocument.activeLayer;
  if (lyr.kind !== LayerKind.TEXT) return "ERROR: la capa activa no es de texto.";
  lyr.textItem.justification = Justification[J];
  return "OK: alineación " + J;
}""")


def ps_select(kind: str = "all", box: list | None = None, feather: float = 0) -> str:
    """Crea/gestiona una selección en Photoshop: all | none | invert | rect | ellipse.
    box=[left, top, right, bottom] (px) para rect/ellipse."""
    k = (kind or "all").lower()
    bx = [float(v) for v in (box or [0, 0, 100, 100])][:4]
    while len(bx) < 4:
        bx.append(0.0)
    return _jsx({"KIND": k, "BOX": bx, "FEA": float(feather)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var doc = app.activeDocument, sel = doc.selection;
  if (KIND === "all" || KIND === "todo") { sel.selectAll(); }
  else if (KIND === "none" || KIND === "ninguno") { sel.deselect(); return "OK: selección quitada"; }
  else if (KIND === "invert" || KIND === "invertir") { sel.invert(); }
  else {
    var l = BOX[0], t = BOX[1], r = BOX[2], b = BOX[3];
    var region = [[l,t],[r,t],[r,b],[l,b]];
    var type = (KIND === "ellipse" || KIND === "elipse") ? SelectionType.REPLACE : SelectionType.REPLACE;
    if (KIND === "ellipse" || KIND === "elipse") {
      // elipse aproximada por polígono de 48 lados
      var cx=(l+r)/2, cy=(t+b)/2, rx=(r-l)/2, ry=(b-t)/2, poly=[], i;
      for (i=0;i<48;i++){ var a=i/48*2*Math.PI; poly.push([cx+rx*Math.cos(a), cy+ry*Math.sin(a)]); }
      sel.select(poly, SelectionType.REPLACE, FEA, true);
    } else {
      sel.select(region, SelectionType.REPLACE, FEA, true);
    }
    return "OK: selección " + KIND;
  }
  if (FEA > 0) { try { sel.feather(FEA); } catch(e){} }
  return "OK: selección " + KIND;
}""")


def ps_select_color(hex_color: str = "#ffffff", tolerance: int = 32) -> str:
    """Selecciona por rango de color (similar a la varita): toma el color dado con tolerancia."""
    return _jsx({"COL": _hex_to_rgb(hex_color), "TOL": int(tolerance)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var doc = app.activeDocument;
  var c = new SolidColor(); c.rgb.red=COL[0]; c.rgb.green=COL[1]; c.rgb.blue=COL[2];
  doc.selection.selectColorRange ? null : null;
  // colorRange vía DOM no existe; usar magicWand sobre un punto del color no aplica → usar selectColorRange manual:
  try {
    doc.selection.deselect();
  } catch(e){}
  // Aproximación: seleccionar todo y aplicar Color Range por Action Manager
  var idClrR = stringIDToTypeID("colorRange");
  var desc = new ActionDescriptor();
  desc.putInteger(stringIDToTypeID("fuzziness"), TOL);
  var clr = new ActionDescriptor();
  clr.putDouble(charIDToTypeID("Rd  "), COL[0]);
  clr.putDouble(charIDToTypeID("Grn "), COL[1]);
  clr.putDouble(charIDToTypeID("Bl  "), COL[2]);
  desc.putObject(stringIDToTypeID("minimum"), charIDToTypeID("RGBC"), clr);
  executeAction(idClrR, desc, DialogModes.NO);
  return "OK: selección por color (tolerancia " + TOL + ")";
}""")


def ps_content_aware_fill() -> str:
    """Rellena la selección según el contenido (content-aware fill)."""
    return _jsx({}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var doc = app.activeDocument;
  if (doc.selection.bounds === undefined) return "ERROR: hacé una selección primero.";
  app.displayDialogs = DialogModes.NO;
  var idFl = charIDToTypeID("Fl  ");
  var desc = new ActionDescriptor();
  desc.putEnumerated(charIDToTypeID("Usng"), charIDToTypeID("FlCn"), stringIDToTypeID("contentAware"));
  desc.putUnitDouble(charIDToTypeID("Opct"), charIDToTypeID("#Prc"), 100);
  desc.putEnumerated(charIDToTypeID("Md  "), charIDToTypeID("BlnM"), charIDToTypeID("Nrml"));
  executeAction(idFl, desc, DialogModes.NO);
  return "OK: relleno según contenido aplicado";
}""")


def ps_feather_selection(radius: float = 5) -> str:
    """Suaviza (feather) la selección activa en Photoshop."""
    return _jsx({"R": float(radius)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  try { app.activeDocument.selection.feather(R); }
  catch(e){ return "ERROR: hacé una selección primero (" + e.toString() + ")"; }
  return "OK: selección suavizada (" + R + "px)";
}""")


def ps_crop_to_selection() -> str:
    """Recorta el documento a los límites de la selección activa."""
    return _jsx({}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var doc = app.activeDocument;
  var b;
  try { b = doc.selection.bounds; }
  catch(e){ return "ERROR: hacé una selección primero."; }
  doc.crop(b);
  return "OK: recortado a la selección";
}""")


def ps_adjustment_layer(kind: str = "brightness", value: float = 0, value2: float = 0) -> str:
    """Capa de ajuste NO destructiva: brightness (brillo+contraste), levels (gamma), vibrance, blackwhite."""
    k = (kind or "brightness").lower()
    return _jsx({"KIND": k, "V": float(value), "V2": float(value2)}, """
function cid(s){ return charIDToTypeID(s); }
function sid(s){ return stringIDToTypeID(s); }
function makeLayer(typeId, adjDesc){
  var d = new ActionDescriptor();
  var ref = new ActionReference(); ref.putClass(sid("adjustmentLayer"));
  d.putReference(cid("null"), ref);
  var type = new ActionDescriptor();
  type.putObject(cid("Type"), typeId, adjDesc);
  d.putObject(cid("Usng"), sid("adjustmentLayer"), type);
  executeAction(cid("Mk  "), d, DialogModes.NO);
}
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.displayDialogs = DialogModes.NO;
  if (KIND === "brightness" || KIND === "brillo") {
    var a = new ActionDescriptor();
    a.putInteger(sid("brightness"), Math.round(V));
    a.putInteger(cid("Cntr"), Math.round(V2));
    a.putBoolean(sid("useLegacy"), false);
    makeLayer(sid("brightnessEvent"), a);
  } else if (KIND === "vibrance" || KIND === "vibracion") {
    var b = new ActionDescriptor();
    b.putInteger(sid("vibrance"), Math.round(V));
    b.putInteger(cid("Strt"), Math.round(V2));
    makeLayer(sid("vibrance"), b);
  } else if (KIND === "blackwhite" || KIND === "bn") {
    makeLayer(sid("blackAndWhite"), new ActionDescriptor());
  } else if (KIND === "levels" || KIND === "niveles") {
    makeLayer(cid("Lvls"), new ActionDescriptor());
  } else {
    return "ERROR: tipo '" + KIND + "' (brightness|vibrance|blackwhite|levels)";
  }
  return "OK: capa de ajuste " + KIND + " creada";
}""")


def ps_gradient_map(hex_a: str = "#000000", hex_b: str = "#ffffff") -> str:
    """Aplica un mapa de degradado (gradient map) entre dos colores a la capa activa."""
    return _jsx({"A": _hex_to_rgb(hex_a), "B": _hex_to_rgb(hex_b)}, """
function cid(s){ return charIDToTypeID(s); }
function sid(s){ return stringIDToTypeID(s); }
function colorStop(rgb, loc){
  var c = new ActionDescriptor();
  var clr = new ActionDescriptor();
  clr.putDouble(cid("Rd  "), rgb[0]); clr.putDouble(cid("Grn "), rgb[1]); clr.putDouble(cid("Bl  "), rgb[2]);
  c.putObject(cid("Clr "), cid("RGBC"), clr);
  c.putEnumerated(cid("Type"), cid("Clry"), cid("UsrS"));
  c.putInteger(cid("Lctn"), loc);
  c.putInteger(cid("Mdpn"), 50);
  return c;
}
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  app.displayDialogs = DialogModes.NO;
  var lyr = app.activeDocument.activeLayer;
  try { if (lyr.isBackgroundLayer) lyr.isBackgroundLayer = false; } catch(eb){}
  if (lyr.kind !== LayerKind.NORMAL) { try { lyr.rasterize(RasterizeType.ENTIRELAYER); } catch(er){} }
  var grad = new ActionDescriptor();
  grad.putEnumerated(cid("GrdF"), cid("GrdF"), cid("CstS"));
  grad.putDouble(cid("Intr"), 4096);
  var stops = new ActionList();
  stops.putObject(cid("Clrt"), colorStop(A, 0));
  stops.putObject(cid("Clrt"), colorStop(B, 4096));
  grad.putList(cid("Clrs"), stops);
  var trans = new ActionList();
  var t0 = new ActionDescriptor(); t0.putUnitDouble(cid("Opct"), cid("#Prc"), 100); t0.putInteger(cid("Lctn"), 0); t0.putInteger(cid("Mdpn"), 50); trans.putObject(cid("TrnS"), t0);
  var t1 = new ActionDescriptor(); t1.putUnitDouble(cid("Opct"), cid("#Prc"), 100); t1.putInteger(cid("Lctn"), 4096); t1.putInteger(cid("Mdpn"), 50); trans.putObject(cid("TrnS"), t1);
  grad.putList(cid("Trns"), trans);
  var gm = new ActionDescriptor();
  gm.putObject(cid("Grad"), cid("Grdn"), grad);
  executeAction(sid("gradientMapEvent"), gm, DialogModes.NO);
  return "OK: mapa de degradado aplicado";
}""")

