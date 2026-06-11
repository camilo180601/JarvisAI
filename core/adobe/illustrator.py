# -*- coding: utf-8 -*-
"""adobe/illustrator.py — operaciones de Illustrator (ai_*)."""
from __future__ import annotations
from core.adobe_templates import _jsx, _hex_to_rgb, _esc


def ai_shape(kind: str, w: float, h: float, fill_hex: str, cx: float | None, cy: float | None) -> str:
    return _jsx({"KIND": kind.lower(), "W": w, "H": h, "FILL": _hex_to_rgb(fill_hex),
                 "CX": cx, "CY": cy}, """
function main(){
  var doc;
  try { doc = app.activeDocument; } catch(e){ doc = app.documents.add(); }
  var ab = doc.artboards[doc.artboards.getActiveArtboardIndex()].artboardRect; // [l,t,r,b]
  var cx = (CX === null) ? (ab[0] + (ab[2]-ab[0])/2) : CX;
  var cy = (CY === null) ? (ab[1] - (ab[1]-ab[3])/2) : CY;
  var top = cy + H/2, left = cx - W/2;
  var item;
  if (KIND === "ellipse" || KIND === "circle" || KIND === "circulo") item = doc.pathItems.ellipse(top, left, W, H);
  else if (KIND === "polygon" || KIND === "poligono") item = doc.pathItems.polygon(cx, cy, W/2, 6);
  else if (KIND === "star" || KIND === "estrella") item = doc.pathItems.star(cx, cy, W/2, W/4, 5);
  else item = doc.pathItems.rectangle(top, left, W, H);
  var c = new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2];
  item.filled = true; item.fillColor = c; item.stroked = false;
  app.redraw();
  return "OK: " + KIND + " creado";
}""")


def ai_outline_text() -> str:
    return _jsx({}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var n = d.textFrames.length;
  for (var i = d.textFrames.length - 1; i >= 0; i--) { d.textFrames[i].createOutline(); }
  app.redraw();
  return "OK: " + n + " texto(s) convertidos a contornos";
}""")


def ai_fit_artboard() -> str:
    return _jsx({}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var idx = d.artboards.getActiveArtboardIndex();
  var vb = d.visibleBounds; // [l,t,r,b] de todo el arte
  d.artboards[idx].artboardRect = vb;
  app.redraw();
  return "OK: mesa de trabajo ajustada al arte";
}""")


def ai_export_artboards(fmt: str, dest_dir: str, scale: float = 1.0) -> str:
    return _jsx({"FMT": fmt.lower(), "DIR": dest_dir, "SCALE": scale}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var folder = new Folder(DIR); if (!folder.exists) folder.create();
  var n = 0;
  for (var i = 0; i < d.artboards.length; i++){
    d.artboards.setActiveArtboardIndex(i);
    var name = d.artboards[i].name.replace(/[^\\w-]/g,"_");
    var base = DIR + "/" + name;
    if (FMT === "svg"){ d.exportFile(new File(base), ExportType.SVG, new ExportOptionsSVG()); }
    else if (FMT === "pdf"){ var p=new PDFSaveOptions(); p.artboardRange=(i+1)+""; d.saveAs(new File(base+".pdf"), p); }
    else {
      var o = (FMT==="jpg"||FMT==="jpeg") ? new ExportOptionsJPEG() : new ExportOptionsPNG24();
      o.horizontalScale = SCALE*100; o.verticalScale = SCALE*100; o.artBoardClipping = true;
      d.exportFile(new File(base), (FMT==="jpg"||FMT==="jpeg")?ExportType.JPEG:ExportType.PNG24, o);
    }
    n++;
  }
  return "OK: " + n + " mesas exportadas a " + DIR;
}""")


def ai_align(how: str) -> str:
    return _jsx({"HOW": how.lower()}, """
function main(){
  var d = app.activeDocument;
  var s = d.selection;
  if (!s || s.length < 2) return "ERROR: seleccioná 2+ objetos para alinear.";
  var L=999999,T=-999999,R=-999999,B=999999, i;
  for (i=0;i<s.length;i++){ var b=s[i].visibleBounds; // [l,t,r,b]
    if(b[0]<L)L=b[0]; if(b[1]>T)T=b[1]; if(b[2]>R)R=b[2]; if(b[3]<B)B=b[3]; }
  var cx=(L+R)/2, cy=(T+B)/2;
  for (i=0;i<s.length;i++){ var it=s[i]; var w=it.width, h=it.height;
    if(HOW==="left") it.left=L;
    else if(HOW==="right") it.left=R-w;
    else if(HOW==="center"||HOW==="hcenter") it.left=cx-w/2;
    else if(HOW==="top") it.top=T;
    else if(HOW==="bottom") it.top=B+h;
    else if(HOW==="middle"||HOW==="vcenter") it.top=cy+h/2;
  }
  app.redraw();
  return "OK: alineado " + HOW;
}""")


def ai_grid(cols: int = 3, gap: float = 20) -> str:
    return _jsx({"COLS": int(cols), "GAP": gap}, """
function main(){
  var d = app.activeDocument;
  var s = d.selection;
  if (!s || s.length < 2) return "ERROR: seleccioná 2+ objetos.";
  var startL = s[0].left, startT = s[0].top, rowH = 0, x = startL, y = startT, col = 0;
  for (var i=0;i<s.length;i++){ var it=s[i];
    it.left = x; it.top = y;
    if (it.height > rowH) rowH = it.height;
    x += it.width + GAP; col++;
    if (col >= COLS){ col=0; x=startL; y -= (rowH + GAP); rowH=0; }
  }
  app.redraw();
  return "OK: " + s.length + " objetos en grilla de " + COLS + " columnas";
}""")


def ai_pathfinder(op: str) -> str:
    cmd = {"unite": "Live Pathfinder Add", "add": "Live Pathfinder Add",
           "minus": "Live Pathfinder Subtract", "subtract": "Live Pathfinder Subtract",
           "intersect": "Live Pathfinder Intersect", "exclude": "Live Pathfinder Exclude",
           "divide": "Live Pathfinder Divide", "trim": "Live Pathfinder Trim",
           "merge": "Live Pathfinder Merge", "crop": "Live Pathfinder Crop",
           "outline": "Live Pathfinder Outline"}.get(op.lower(), "Live Pathfinder Add")
    return _jsx({"CMD": cmd}, """
function main(){
  var d = app.activeDocument;
  if (!d.selection || d.selection.length < 2) return "ERROR: seleccioná 2+ formas.";
  try { app.executeMenuCommand("group"); } catch(e){}
  app.executeMenuCommand(CMD);
  try { app.executeMenuCommand("expandStyle"); } catch(e){}  // algunos modos (divide/trim) no necesitan expandir
  app.redraw();
  return "OK: pathfinder aplicado";
}""")


def ai_pattern(shapes: list, cols: int = 6, rows: int = 6, gap: float = 0.25,
               hex_colors: list | None = None, layout: str = "grid",
               rotate: bool = False, vary: bool = False, angle: float = 0) -> str:
    """Llena la mesa de trabajo con un PATRÓN de figuras trazadas (grid/brick/scatter),
    mezclando formas y colores. layout: grid | brick | scatter. angle = inclinación fija
    en grados de cada figura (si es 0 y rotate=True, rota al azar)."""
    colors = [_hex_to_rgb(h) for h in (hex_colors or ["#1e90ff", "#ff3b30", "#ffd400", "#34c759"])]
    return _jsx({"SHAPES": [s.lower() for s in (shapes or ["ellipse", "rect", "triangle", "star"])],
                 "COLS": int(cols), "ROWS": int(rows), "GAP": float(gap),
                 "COLORS": colors, "LAYOUT": layout.lower(), "ROTATE": bool(rotate),
                 "VARY": bool(vary), "ANGLE": float(angle)}, """
function makeShape(doc, kind, cx, cy, sz){
  var h = sz/2;
  if (kind==="ellipse"||kind==="circle") return doc.pathItems.ellipse(cy+h, cx-h, sz, sz);
  if (kind==="rect"||kind==="square")    return doc.pathItems.rectangle(cy+h, cx-h, sz, sz);
  if (kind==="triangle")                 return doc.pathItems.polygon(cx, cy, h, 3);
  if (kind==="star")                     return doc.pathItems.star(cx, cy, h, h/2.4, 5);
  if (kind==="hexagon"||kind==="polygon")return doc.pathItems.polygon(cx, cy, h, 6);
  return doc.pathItems.ellipse(cy+h, cx-h, sz, sz);
}
function main(){
  var doc; try { doc = app.activeDocument; } catch(e){ doc = app.documents.add(); }
  var ab = doc.artboards[doc.artboards.getActiveArtboardIndex()].artboardRect;
  var L=ab[0], T=ab[1], R=ab[2], B=ab[3];
  var W=R-L, H=T-B, cw=W/COLS, ch=H/ROWS, i=0, made=0;
  for (var r=0; r<ROWS; r++){
    for (var c=0; c<COLS; c++){
      var cx = L + cw*(c+0.5);
      var cy = T - ch*(r+0.5);
      if (LAYOUT==="brick" && (r%2===1)) cx += cw/2;
      if (LAYOUT==="scatter"){ cx += (Math.random()-0.5)*cw*0.6; cy += (Math.random()-0.5)*ch*0.6; }
      var sz = Math.min(cw,ch)*(1-GAP);
      if (VARY) sz *= (0.55 + Math.random()*0.6);
      if (sz < 1) sz = 1;
      var kind = SHAPES[(LAYOUT==="scatter") ? Math.floor(Math.random()*SHAPES.length) : (i%SHAPES.length)];
      var it = makeShape(doc, kind, cx, cy, sz);
      var rgb = COLORS[i%COLORS.length];
      var col = new RGBColor(); col.red=rgb[0]; col.green=rgb[1]; col.blue=rgb[2];
      it.filled=true; it.fillColor=col; it.stroked=false;
      if (ANGLE) it.rotate(ANGLE);
      else if (ROTATE) it.rotate(Math.random()*360);
      i++; made++;
    }
  }
  app.redraw();
  return "OK: patrón de " + made + " figuras (" + LAYOUT + ")";
}""")


def ai_radial_repeat(count: int = 8, around: str = "artboard") -> str:
    """Repite la selección en círculo (mandala): N copias rotadas alrededor del centro."""
    return _jsx({"COUNT": int(count), "AROUND": around.lower()}, """
function main(){
  var doc = app.activeDocument;
  var sel = doc.selection;
  if (!sel || sel.length < 1) return "ERROR: seleccioná al menos un objeto.";
  var L=999999,T=-999999,R=-999999,Bm=999999, k;
  for (k=0;k<sel.length;k++){ var b=sel[k].visibleBounds;
    if(b[0]<L)L=b[0]; if(b[1]>T)T=b[1]; if(b[2]>R)R=b[2]; if(b[3]<Bm)Bm=b[3]; }
  var cx, cy;
  if (AROUND==="selection"){ cx=(L+R)/2; cy=(T+Bm)/2; }
  else { var ab=doc.artboards[doc.artboards.getActiveArtboardIndex()].artboardRect; cx=(ab[0]+ab[2])/2; cy=(ab[1]+ab[3])/2; }
  var n = COUNT;
  for (var i=1;i<n;i++){
    var ang = 360/n*i;
    var m = app.getTranslationMatrix(-cx,-cy);
    m = app.concatenateRotationMatrix(m, ang);
    m = app.concatenateTranslationMatrix(m, cx, cy);
    for (k=0;k<sel.length;k++){ var dup = sel[k].duplicate(); dup.transform(m); }
  }
  app.redraw();
  return "OK: repetición radial x" + n;
}""")


def ai_scatter(count: int = 20, rot: bool = True, scale_var: bool = True) -> str:
    """Esparce N copias de la selección por la mesa, con posición/rotación/escala random."""
    return _jsx({"COUNT": int(count), "ROT": bool(rot), "SVAR": bool(scale_var)}, """
function main(){
  var doc = app.activeDocument;
  var sel = doc.selection;
  if (!sel || sel.length < 1) return "ERROR: seleccioná un objeto para esparcir.";
  var src = sel[0];
  var ab = doc.artboards[doc.artboards.getActiveArtboardIndex()].artboardRect;
  var L=ab[0], T=ab[1], R=ab[2], B=ab[3];
  for (var i=0;i<COUNT;i++){
    var d = src.duplicate();
    d.position = [L + Math.random()*(R-L-d.width), T - Math.random()*(T-B-d.height)];
    if (ROT) d.rotate(Math.random()*360);
    if (SVAR){ var s = 40 + Math.random()*120; d.resize(s, s); }
  }
  app.redraw();
  return "OK: " + COUNT + " copias esparcidas";
}""")


def ai_polygon_of_elements(sides: int = 5, per_side: int = 3, radius: float = 200,
                           image_path: str | None = None, shape_kind: str = "ellipse",
                           size: float = 60, hex_color: str = "#c8821e",
                           tilt: float = 0, spin: float = 0) -> str:
    """Arma un POLÍGONO (pentágono, etc.) hecho de copias de un elemento: una imagen
    (ej: galletas) o una figura trazada, distribuidas en el perímetro. Devuelve un grupo.
    tilt = grados que se inclina CADA elemento; spin = grados que se rota el polígono entero."""
    return _jsx({"SIDES": int(sides), "PER": int(per_side), "RAD": float(radius),
                 "IMG": image_path or "", "KIND": shape_kind.lower(),
                 "SZ": float(size), "COL": _hex_to_rgb(hex_color),
                 "TILT": float(tilt), "SPIN": float(spin)}, """
function makeShape(doc, kind, sz){
  var h = sz/2;
  if (kind==="rect"||kind==="square") return doc.pathItems.rectangle(h, -h, sz, sz);
  if (kind==="triangle") return doc.pathItems.polygon(0, 0, h, 3);
  if (kind==="star") return doc.pathItems.star(0, 0, h, h/2.4, 5);
  if (kind==="hexagon"||kind==="polygon") return doc.pathItems.polygon(0, 0, h, 6);
  return doc.pathItems.ellipse(h, -h, sz, sz);
}
function main(){
  var doc; try { doc = app.activeDocument; } catch(e){ doc = app.documents.add(); }
  var ab = doc.artboards[doc.artboards.getActiveArtboardIndex()].artboardRect;
  var cx=(ab[0]+ab[2])/2, cy=(ab[1]+ab[3])/2;
  var grp = doc.groupItems.add();

  // base: imagen (galletas) o nada (figuras se crean por punto)
  var base = null;
  if (IMG){
    var f = new File(IMG);
    if (!f.exists) return "ERROR: no existe la imagen " + IMG;
    base = doc.placedItems.add(); base.file = f;
    var sc = SZ/Math.max(base.width, base.height); base.width*=sc; base.height*=sc;
  }

  // vértices del polígono regular (arranca arriba) + puntos interpolados por lado
  var pts = [];
  for (var v=0; v<SIDES; v++){
    var a1 = (90 + v*360/SIDES) * Math.PI/180;
    var a2 = (90 + (v+1)*360/SIDES) * Math.PI/180;
    var x1=cx+RAD*Math.cos(a1), y1=cy+RAD*Math.sin(a1);
    var x2=cx+RAD*Math.cos(a2), y2=cy+RAD*Math.sin(a2);
    for (var t=0; t<PER; t++){
      var f2=t/PER;
      pts.push([x1+(x2-x1)*f2, y1+(y2-y1)*f2]);
    }
  }

  for (var i=0; i<pts.length; i++){
    var px=pts[i][0], py=pts[i][1], it;
    if (IMG){ it = base.duplicate(); it.position=[px-it.width/2, py+it.height/2]; }
    else {
      it = makeShape(doc, KIND, SZ);
      var c=new RGBColor(); c.red=COL[0]; c.green=COL[1]; c.blue=COL[2];
      it.filled=true; it.fillColor=c; it.stroked=false;
      it.position=[px-it.width/2, py+it.height/2];
    }
    if (TILT) it.rotate(TILT);   // inclinación de cada elemento
    it.move(grp, ElementPlacement.PLACEATEND);
  }
  if (base){ base.remove(); }
  if (SPIN) grp.rotate(SPIN);     // rotar el polígono entero
  doc.selection = [grp];
  app.redraw();
  return "OK: polígono de " + SIDES + " lados hecho de " + pts.length + " elementos" +
         (TILT? (", inclinados " + TILT + "°"):"") + (SPIN? (", girado " + SPIN + "°"):"") +
         " (seleccionado — repetilo con radial_repeat/pattern)";
}""")


def ai_tile(rows: int = 4, cols: int = 5, gap: float = 20, skip_every: int = 5,
            tilt: float = 0) -> str:
    """Repite la selección en una grilla rows x cols, dejando VACÍA cada `skip_every`
    posición (ej: skip_every=5 → 4 llenos y 1 vacío). tilt = grados que se inclina cada copia."""
    return _jsx({"ROWS": int(rows), "COLS": int(cols), "GAP": float(gap), "SKIP": int(skip_every),
                 "TILT": float(tilt)}, """
function main(){
  var doc = app.activeDocument;
  var sel = doc.selection;
  if (!sel || sel.length < 1) return "ERROR: seleccioná el grupo/figura a teselar.";
  // unir la selección en un grupo base
  var base;
  if (sel.length === 1){ base = sel[0]; }
  else { base = doc.groupItems.add(); for (var k=sel.length-1;k>=0;k--){ sel[k].move(base, ElementPlacement.PLACEATEND); } }
  var w = base.width, h = base.height;
  var x0 = base.position[0], y0 = base.position[1];
  var stepX = w + GAP, stepY = h + GAP;
  var idx = 0, made = 0, empty = 0;
  for (var r=0; r<ROWS; r++){
    for (var c=0; c<COLS; c++){
      idx++;
      var emptySlot = (SKIP > 0 && (idx % SKIP === 0));
      if (r===0 && c===0){ if (emptySlot){ base.remove(); empty++; } continue; } // la base ya está en (0,0)
      if (emptySlot){ empty++; continue; }
      var d = base.duplicate();
      d.position = [x0 + stepX*c, y0 - stepY*r];
      if (TILT) d.rotate(TILT);
      made++;
    }
  }
  if (TILT) base.rotate(TILT);
  app.redraw();
  return "OK: teselado " + (made+1) + " llenos, " + empty + " vacíos (cada " + SKIP + ")" +
         (TILT? (", inclinados " + TILT + "°"):"");
}""")


def ai_gradient(hex_colors: list, gtype: str = "linear", angle: float = 0) -> str:
    """Aplica un GRADIENTE (lineal o radial) a la selección (o a todo si no hay selección)."""
    colors = [_hex_to_rgb(h) for h in (hex_colors or ["#1e90ff", "#ffffff"])]
    if len(colors) < 2:
        colors = colors + colors
    return _jsx({"COLORS": colors, "GTYPE": gtype.lower(), "ANGLE": float(angle)}, """
function applyGrad(item, gc){
  var tn = item.typename;
  if (tn==="PathItem"){ item.filled=true; item.fillColor=gc; }
  else if (tn==="CompoundPathItem"){ var j; for(j=0;j<item.pathItems.length;j++) applyGrad(item.pathItems[j],gc); }
  else if (tn==="GroupItem"){ var k; for(k=0;k<item.pageItems.length;k++) applyGrad(item.pageItems[k],gc); }
}
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var doc = app.activeDocument;
  var grad = doc.gradients.add();
  grad.type = (GTYPE==="radial") ? GradientType.RADIAL : GradientType.LINEAR;
  while (grad.gradientStops.length < COLORS.length) grad.gradientStops.add();
  for (var i=0;i<COLORS.length;i++){
    var st = grad.gradientStops[i];
    st.rampPoint = (COLORS.length===1)?50:(i/(COLORS.length-1))*100;
    st.midPoint = 50;
    var c = new RGBColor(); c.red=COLORS[i][0]; c.green=COLORS[i][1]; c.blue=COLORS[i][2];
    st.color = c;
  }
  var items = (doc.selection && doc.selection.length>0) ? doc.selection : doc.pageItems;
  var n=0;
  for (var k=0;k<items.length;k++){
    var gc = new GradientColor(); gc.gradient = grad;
    try { gc.angle = ANGLE; } catch(e){}
    applyGrad(items[k], gc); n++;
  }
  app.redraw();
  return "OK: gradiente " + GTYPE + " aplicado a " + n + " objeto(s)";
}""")


def ai_stroke(hex_color: str = "#000000", width: float = 1.0, none: bool = False) -> str:
    """Pone (o quita) el TRAZO/contorno a la selección: color + grosor. none=true lo quita."""
    return _jsx({"COL": _hex_to_rgb(hex_color), "W": float(width), "NONE": bool(none)}, """
function applyStroke(item){
  var tn = item.typename;
  if (tn==="PathItem"){
    if (NONE){ item.stroked=false; }
    else { item.stroked=true; var c=new RGBColor(); c.red=COL[0];c.green=COL[1];c.blue=COL[2];
           item.strokeColor=c; item.strokeWidth=W; }
  } else if (tn==="CompoundPathItem"){ var j; for(j=0;j<item.pathItems.length;j++) applyStroke(item.pathItems[j]); }
  else if (tn==="GroupItem"){ var k; for(k=0;k<item.pageItems.length;k++) applyStroke(item.pageItems[k]); }
}
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var doc = app.activeDocument;
  var items = (doc.selection && doc.selection.length>0) ? doc.selection : doc.pageItems;
  for (var k=0;k<items.length;k++) applyStroke(items[k]);
  app.redraw();
  return NONE ? "OK: trazo quitado" : ("OK: trazo aplicado (grosor " + W + ")");
}""")


def ai_opacity(value: float = 100) -> str:
    """Cambia la OPACIDAD (0-100) de la selección (o de todo si no hay selección)."""
    v = max(0, min(100, float(value)))
    return _jsx({"V": v}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var doc = app.activeDocument;
  var items = (doc.selection && doc.selection.length>0) ? doc.selection : doc.pageItems;
  for (var k=0;k<items.length;k++){ try { items[k].opacity = V; } catch(e){} }
  app.redraw();
  return "OK: opacidad al " + V + "%";
}""")


def ai_blend(steps: int = 6) -> str:
    """Transición (blend) entre 2 objetos seleccionados: N copias interpoladas (posición+tamaño)."""
    return _jsx({"STEPS": int(steps)}, """
function main(){
  var d=app.activeDocument, s=d.selection;
  if (!s || s.length!==2) return "ERROR: seleccioná EXACTAMENTE 2 objetos.";
  var a=s[0], b=s[1];
  var ax=a.position[0], ay=a.position[1], bx=b.position[0], by=b.position[1];
  for (var i=1;i<=STEPS;i++){
    var t=i/(STEPS+1);
    var dup=a.duplicate();
    dup.position=[ax+(bx-ax)*t, ay+(by-ay)*t];
    try { var sw=((a.width+(b.width-a.width)*t)/a.width)*100;
          var sh=((a.height+(b.height-a.height)*t)/a.height)*100; dup.resize(sw,sh); } catch(e){}
  }
  app.redraw();
  return "OK: blend de "+STEPS+" pasos";
}""")


def ai_reflect(axis: str = "horizontal") -> str:
    """Espeja (flip) la selección en el eje horizontal o vertical."""
    return _jsx({"AXIS": axis.lower()}, """
function main(){
  var d=app.activeDocument, s=d.selection;
  if (!s || s.length<1) return "ERROR: seleccioná algo.";
  for (var i=0;i<s.length;i++){
    if (AXIS==="vertical"||AXIS==="v") s[i].resize(100,-100);
    else s[i].resize(-100,100);
  }
  app.redraw();
  return "OK: espejado ("+AXIS+")";
}""")


def ai_transform(rotate: float = 0, scale: float = 100) -> str:
    """Rota (grados) y/o escala (%) la selección."""
    return _jsx({"ROT": float(rotate), "SCALE": float(scale)}, """
function main(){
  var d=app.activeDocument, s=d.selection;
  if (!s || s.length<1) return "ERROR: seleccioná algo.";
  for (var i=0;i<s.length;i++){
    if (ROT) s[i].rotate(ROT);
    if (SCALE && SCALE!==100) s[i].resize(SCALE,SCALE);
  }
  app.redraw();
  return "OK: rotado "+ROT+"°, escala "+SCALE+"%";
}""")


def ai_arrange(order: str = "front") -> str:
    """Orden Z de la selección: front | back | forward | backward."""
    z = {"front": "BRINGTOFRONT", "back": "SENDTOBACK", "forward": "BRINGFORWARD",
         "backward": "SENDBACKWARD", "adelante": "BRINGTOFRONT", "atras": "SENDTOBACK"}.get(order.lower(), "BRINGTOFRONT")
    return _jsx({"Z": z}, """
function main(){
  var d=app.activeDocument, s=d.selection;
  if (!s || s.length<1) return "ERROR: seleccioná algo.";
  for (var i=0;i<s.length;i++){ try { s[i].zOrder(ZOrderMethod[Z]); } catch(e){} }
  app.redraw();
  return "OK: orden "+Z;
}""")


def ai_distribute(direction: str = "horizontal") -> str:
    """Distribuye la selección con espaciado parejo (horizontal o vertical)."""
    return _jsx({"DIR": direction.lower()}, """
function main(){
  var d=app.activeDocument, s=[];
  if (!d.selection || d.selection.length<3) return "ERROR: seleccioná 3+ objetos.";
  for (var i=0;i<d.selection.length;i++) s.push(d.selection[i]);
  var horiz = !(DIR==="vertical"||DIR==="v");
  s.sort(function(a,b){ return horiz ? (a.left-b.left) : (b.top-a.top); });
  var first=s[0], last=s[s.length-1];
  if (horiz){
    var span=last.left-first.left, gap=span/(s.length-1);
    for (var i=1;i<s.length-1;i++) s[i].left = first.left + gap*i;
  } else {
    var span2=first.top-last.top, gap2=span2/(s.length-1);
    for (var i=1;i<s.length-1;i++) s[i].top = first.top - gap2*i;
  }
  app.redraw();
  return "OK: distribuido ("+DIR+")";
}""")


def ai_text_on_path(text: str, radius: float = 150, font_size: float = 24,
                    fill_hex: str = "#000000") -> str:
    """Texto sobre un trazo: usa el path seleccionado, o crea un círculo y pone el texto alrededor."""
    return _jsx({"TEXT": text, "RAD": float(radius), "SZ": float(font_size),
                 "FILL": _hex_to_rgb(fill_hex)}, """
function main(){
  var doc; try { doc = app.activeDocument; } catch(e){ doc = app.documents.add(); }
  var path = null;
  if (doc.selection && doc.selection.length>0 && doc.selection[0].typename==="PathItem")
    path = doc.selection[0];
  if (!path){
    var ab=doc.artboards[doc.artboards.getActiveArtboardIndex()].artboardRect;
    var cx=(ab[0]+ab[2])/2, cy=(ab[1]+ab[3])/2;
    path = doc.pathItems.ellipse(cy+RAD, cx-RAD, 2*RAD, 2*RAD);
    path.filled=false; path.stroked=false;
  }
  var tf = doc.textFrames.pathText(path);
  tf.contents = TEXT;
  var ca = tf.textRange.characterAttributes;
  ca.size = SZ;
  var c=new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2];
  ca.fillColor = c;
  app.redraw();
  return "OK: texto sobre el trazo";
}""")


_AI_EFFECT_XML = {
    "round_corners": '<LiveEffect name="Adobe Round Corners"><Dict data="R radius {v} "/></LiveEffect>',
    "esquinas":      '<LiveEffect name="Adobe Round Corners"><Dict data="R radius {v} "/></LiveEffect>',
    "drop_shadow":   '<LiveEffect name="Adobe Drop Shadow"><Dict data="R Opacity 0.75 R XOffset {v} R YOffset {v} R Blur {v} I Color 0 VRgba Color2 [ 4 0.0 0.0 0.0 1.0 ] B Darkness 1 R Darkness2 50 "/></LiveEffect>',
    "sombra":        '<LiveEffect name="Adobe Drop Shadow"><Dict data="R Opacity 0.75 R XOffset {v} R YOffset {v} R Blur {v} I Color 0 VRgba Color2 [ 4 0.0 0.0 0.0 1.0 ] B Darkness 1 R Darkness2 50 "/></LiveEffect>',
    "zigzag":        '<LiveEffect name="Adobe Zig Zag"><Dict data="R Size {v} R Ridges 4 I Points 1 B Relative 0 "/></LiveEffect>',
    "roughen":       '<LiveEffect name="Adobe Roughen"><Dict data="R Size {v} R Detail 10 I Points 0 B Relative 0 "/></LiveEffect>',
    "rugoso":        '<LiveEffect name="Adobe Roughen"><Dict data="R Size {v} R Detail 10 I Points 0 B Relative 0 "/></LiveEffect>',
    "pucker":        '<LiveEffect name="Adobe Pucker-Bloat"><Dict data="R Amount {v} "/></LiveEffect>',
    "feather":       '<LiveEffect name="Adobe Feather"><Dict data="R Radius {v} "/></LiveEffect>',
    "pluma":         '<LiveEffect name="Adobe Feather"><Dict data="R Radius {v} "/></LiveEffect>',
}


def ai_effect(kind: str = "round_corners", amount: float = 12) -> str:
    """Aplica un efecto vivo (editable) a la selección: round_corners, drop_shadow,
    zigzag, roughen, pucker, feather. 'amount' = intensidad (px o, para pucker, fracción)."""
    k = (kind or "").lower()
    xml = _AI_EFFECT_XML.get(k)
    if not xml:
        return _jsx({}, """function main(){ return "ERROR: efecto no soportado"; }""")
    # pucker usa fracción (-1..1); el resto, px (escalados a la unidad interna /72 para corners/shadow)
    v = amount if k in ("pucker",) else amount
    return _jsx({"XML": xml.replace("{v}", str(v))}, """
function tryApply(it){            // applyEffect puede dar 'MRAP' intermitente headless: reintentar
  var k; for (k = 0; k < 6; k++) {
    try { it.applyEffect(XML); return true; } catch(e){ app.redraw(); }
  }
  return false;
}
function main(){
  var d = app.activeDocument;
  app.redraw();
  var sel = (d.selection && d.selection.length) ? d.selection : null;
  if (!sel) return "ERROR: seleccioná al menos un objeto.";
  var n = 0, i;
  for (i = 0; i < sel.length; i++) { if (tryApply(sel[i])) n++; }
  app.redraw();
  if (n === 0) return "ERROR: Illustrator rechazó el efecto (MRAP). Probá de nuevo o usá action=run.";
  return "OK: efecto aplicado a " + n + " objeto(s)";
}""")


def ai_star(points: int = 5, outer: float = 120, inner: float = 55,
            hex_color: str = "#f5b301") -> str:
    """Dibuja una estrella centrada en el artboard con N puntas."""
    return _jsx({"PTS": int(points), "ROUT": float(outer), "RIN": float(inner),
                 "FILL": _hex_to_rgb(hex_color)}, """
function main(){
  var d = app.activeDocument;
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var cx = (ab[0]+ab[2])/2, cy = (ab[1]+ab[3])/2;
  var pts = [], a = -Math.PI/2, step = Math.PI/PTS, i;
  for (i = 0; i < PTS*2; i++) {
    var r = (i % 2 === 0) ? ROUT : RIN;
    pts.push([cx + r*Math.cos(a), cy + r*Math.sin(a)]);
    a += step;
  }
  var p = d.pathItems.add();
  p.setEntirePath(pts);
  p.closed = true;
  var c = new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2];
  p.filled = true; p.fillColor = c; p.stroked = false;
  app.redraw();
  return "OK: estrella de " + PTS + " puntas";
}""")


def ai_spiral(turns: float = 3, radius: float = 150, hex_color: str = "#1e90ff",
              width: float = 2) -> str:
    """Dibuja una espiral (trazo) centrada en el artboard."""
    return _jsx({"TURNS": float(turns), "RAD": float(radius),
                 "FILL": _hex_to_rgb(hex_color), "W": float(width)}, """
function main(){
  var d = app.activeDocument;
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var cx = (ab[0]+ab[2])/2, cy = (ab[1]+ab[3])/2;
  var segs = Math.round(TURNS*36), pts = [], i;
  for (i = 0; i <= segs; i++) {
    var t = (i/segs) * TURNS * 2 * Math.PI;
    var r = RAD * (i/segs);
    pts.push([cx + r*Math.cos(t), cy + r*Math.sin(t)]);
  }
  var p = d.pathItems.add();
  p.setEntirePath(pts);
  p.closed = false; p.filled = false; p.stroked = true;
  var c = new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2];
  p.strokeColor = c; p.strokeWidth = W;
  app.redraw();
  return "OK: espiral de " + TURNS + " vueltas";
}""")


def ai_clip_mask() -> str:
    """Crea una máscara de recorte con la selección (el objeto de arriba recorta a los de abajo)."""
    return _jsx({}, """
function main(){
  var d = app.activeDocument;
  if (!d.selection || d.selection.length < 2) return "ERROR: seleccioná 2+ objetos (el de arriba recorta).";
  app.executeMenuCommand("makeMask");
  app.redraw();
  return "OK: máscara de recorte creada";
}""")


def ai_round_rect(w: float = 200, h: float = 140, radius: float = 25,
                  hex_color: str = "#1e90ff") -> str:
    """Dibuja un rectángulo redondeado centrado en el artboard (primitiva nativa, sin efectos)."""
    return _jsx({"W": float(w), "H": float(h), "RAD": float(radius),
                 "FILL": _hex_to_rgb(hex_color)}, """
function main(){
  var d = app.activeDocument;
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var cx = (ab[0]+ab[2])/2, cy = (ab[1]+ab[3])/2;
  var top = cy + H/2, left = cx - W/2;
  var p = d.pathItems.roundedRectangle(top, left, W, H, RAD, RAD);
  var c = new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2];
  p.filled = true; p.fillColor = c; p.stroked = false;
  app.redraw();
  return "OK: rectángulo redondeado (radio " + RAD + ")";
}""")


def ai_text(text: str = "", x: float | None = None, y: float | None = None,
            size: float = 36, hex_color: str = "#000000") -> str:
    """Agrega texto de punto en una posición del artboard (default: centro)."""
    return _jsx({"TXT": text, "X": (None if x is None else float(x)),
                 "Y": (None if y is None else float(y)), "SZ": float(size),
                 "FILL": _hex_to_rgb(hex_color)}, """
function main(){
  var d = app.activeDocument;
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var px = (X === null) ? (ab[0]+ab[2])/2 : X;
  var py = (Y === null) ? (ab[1]+ab[3])/2 : Y;
  var tf = d.textFrames.pointText([px, py]);
  tf.contents = TXT;
  var ca = tf.textRange.characterAttributes;
  ca.size = SZ;
  var c = new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2];
  ca.fillColor = c;
  app.redraw();
  return "OK: texto agregado";
}""")


def ai_group(ungroup: bool = False) -> str:
    """Agrupa (o desagrupa) la selección en Illustrator."""
    cmd = "ungroup" if ungroup else "group"
    return _jsx({"CMD": cmd}, """
function main(){
  var d = app.activeDocument;
  if (!d.selection || d.selection.length === 0) return "ERROR: no hay selección.";
  app.executeMenuCommand(CMD);
  app.redraw();
  return "OK: " + (CMD === "group" ? "agrupado" : "desagrupado");
}""")


def ai_swatches(hex_colors: list) -> str:
    """Agrega muestras de color (swatches) al documento desde una paleta hex."""
    cols = [_hex_to_rgb(h) for h in (hex_colors or [])]
    return _jsx({"COLS": cols}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  if (!COLS.length) return "ERROR: dame colores (hex).";
  var d = app.activeDocument, n = 0, i;
  for (i = 0; i < COLS.length; i++) {
    var c = new RGBColor(); c.red=COLS[i][0]; c.green=COLS[i][1]; c.blue=COLS[i][2];
    var sw = d.swatches.add(); sw.color = c; n++;
  }
  return "OK: " + n + " muestras agregadas";
}""")


def ai_artboard(w: float = 800, h: float = 600) -> str:
    """Agrega una mesa de trabajo (artboard) nueva al lado de la última."""
    return _jsx({"W": float(w), "H": float(h)}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var last = d.artboards[d.artboards.length-1].artboardRect; // [l,t,r,b]
  var left = last[2] + 30, top = last[1];
  d.artboards.add([left, top, left + W, top - H]);
  return "OK: artboard agregado (" + W + "x" + H + ")";
}""")


_AI_BLEND = {
    "normal": "NORMAL", "multiply": "MULTIPLY", "multiplicar": "MULTIPLY",
    "screen": "SCREEN", "trama": "SCREEN", "overlay": "OVERLAY", "superponer": "OVERLAY",
    "softlight": "SOFTLIGHT", "soft_light": "SOFTLIGHT", "luz_suave": "SOFTLIGHT",
    "hardlight": "HARDLIGHT", "hard_light": "HARDLIGHT", "luz_fuerte": "HARDLIGHT",
    "darken": "DARKEN", "oscurecer": "DARKEN", "lighten": "LIGHTEN", "aclarar": "LIGHTEN",
    "colordodge": "COLORDODGE", "colorburn": "COLORBURN",
    "difference": "DIFFERENCE", "diferencia": "DIFFERENCE", "exclusion": "EXCLUSION",
    "hue": "HUE", "saturation": "SATURATION", "color": "COLOR", "luminosity": "LUMINOSITY",
}


def ai_blend_mode(mode: str = "multiply") -> str:
    """Modo de fusión de transparencia para la selección en Illustrator."""
    bm = _AI_BLEND.get((mode or "").lower().replace(" ", "_"), "NORMAL")
    return _jsx({"BM": bm}, """
function main(){
  var d = app.activeDocument;
  if (!d.selection || !d.selection.length) return "ERROR: seleccioná objetos.";
  var n = 0, i;
  for (i = 0; i < d.selection.length; i++) {
    try { d.selection[i].blendingMode = BlendModes[BM]; n++; } catch(e){}
  }
  app.redraw();
  if (n === 0) return "ERROR: no se pudo aplicar el modo de fusión.";
  return "OK: modo " + BM + " en " + n + " objeto(s)";
}""")


def ai_compound_path() -> str:
    """Crea un trazado compuesto con la selección (formas con huecos: donas, letras caladas)."""
    return _jsx({}, """
function main(){
  var d = app.activeDocument;
  if (!d.selection || d.selection.length < 1) return "ERROR: seleccioná las formas.";
  app.executeMenuCommand("compoundPath");
  app.redraw();
  return "OK: trazado compuesto creado";
}""")


def ai_place_linked(image_path: str, embed: bool = False) -> str:
    """Coloca una imagen en Illustrator (centrada y escalada al artboard) SIN vectorizar."""
    return _jsx({"PATH": image_path, "EMBED": bool(embed)}, """
function main(){
  var d = (app.documents.length) ? app.activeDocument : app.documents.add();
  var f = new File(PATH);
  if (!f.exists) return "ERROR: no existe " + PATH;
  var placed = d.placedItems.add();
  placed.file = f;
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var abW = ab[2]-ab[0], abH = ab[1]-ab[3];
  var iw = placed.width, ih = placed.height;
  if (iw > 0 && ih > 0) { var s = Math.min(abW/iw, abH/ih) * 0.8; if (s > 0 && s < 50) { placed.width = iw*s; placed.height = ih*s; } }
  placed.position = [ab[0] + (abW - placed.width)/2, ab[1] - (abH - placed.height)/2];
  if (EMBED) { try { placed.embed(); } catch(e){} }
  app.redraw();
  return "OK: imagen colocada" + (EMBED ? " (incrustada)" : "");
}""")


def ai_line(x1: float = 100, y1: float = 100, x2: float = 400, y2: float = 400,
            hex_color: str = "#000000", width: float = 2) -> str:
    """Dibuja una línea entre dos puntos en Illustrator."""
    return _jsx({"X1": float(x1), "Y1": float(y1), "X2": float(x2), "Y2": float(y2),
                 "FILL": _hex_to_rgb(hex_color), "W": float(width)}, """
function main(){
  var d = (app.documents.length) ? app.activeDocument : app.documents.add();
  var p = d.pathItems.add();
  p.setEntirePath([[X1, Y1], [X2, Y2]]);
  p.stroked = true; p.filled = false;
  var c = new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2];
  p.strokeColor = c; p.strokeWidth = W;
  app.redraw();
  return "OK: línea creada";
}""")


def ai_dashed_stroke(dashes: list | None = None, hex_color: str | None = None,
                     width: float = 2) -> str:
    """Aplica un contorno discontinuo (guiones) a la selección. dashes ej [6,3]."""
    dl = [float(v) for v in (dashes or [6, 3])]
    return _jsx({"DASHES": dl, "FILL": (_hex_to_rgb(hex_color) if hex_color else None),
                 "W": float(width)}, """
function main(){
  var d = app.activeDocument;
  if (!d.selection || !d.selection.length) return "ERROR: seleccioná objetos.";
  var n = 0, i;
  for (i = 0; i < d.selection.length; i++) {
    var it = d.selection[i];
    try {
      it.stroked = true; it.strokeWidth = W; it.strokeDashes = DASHES;
      if (FILL) { var c = new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2]; it.strokeColor = c; }
      n++;
    } catch(e){}
  }
  app.redraw();
  if (n === 0) return "ERROR: no se pudo aplicar el contorno discontinuo.";
  return "OK: contorno discontinuo en " + n + " objeto(s)";
}""")


def ai_layer(name: str = "Capa", rename: bool = False) -> str:
    """Crea una capa nueva (o renombra la activa) en Illustrator."""
    return _jsx({"NM": name, "RENAME": bool(rename)}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  if (RENAME) { d.activeLayer.name = NM; return "OK: capa renombrada a '" + NM + "'"; }
  var l = d.layers.add(); l.name = NM;
  return "OK: capa '" + NM + "' creada";
}""")


def ai_wave(cycles: float = 3, width: float = 400, amplitude: float = 60,
            hex_color: str = "#9b59b6", stroke_width: float = 2) -> str:
    """Dibuja una onda senoidal (trazo) centrada en el artboard."""
    return _jsx({"CYC": float(cycles), "WIDTH": float(width), "AMP": float(amplitude),
                 "FILL": _hex_to_rgb(hex_color), "WD": float(stroke_width)}, """
function main(){
  var d = app.activeDocument;
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var cx = (ab[0]+ab[2])/2, cy = (ab[1]+ab[3])/2;
  var segs = Math.round(CYC*24), pts = [], i, startx = cx - WIDTH/2;
  for (i = 0; i <= segs; i++) {
    var t = i/segs;
    pts.push([startx + t*WIDTH, cy + AMP*Math.sin(t*CYC*2*Math.PI)]);
  }
  var p = d.pathItems.add();
  p.setEntirePath(pts);
  p.closed = false; p.filled = false; p.stroked = true;
  var c = new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2];
  p.strokeColor = c; p.strokeWidth = WD;
  app.redraw();
  return "OK: onda de " + CYC + " ciclos";
}""")


def ai_color_mode(mode: str = "cmyk") -> str:
    """Convierte el documento de Illustrator a RGB o CMYK (útil para impresión)."""
    return _jsx({"MODE": (mode or "cmyk").lower()}, """
function main(){
  if (app.documents.length===0) return "ERROR: no hay documento.";
  if (MODE === "cmyk") app.executeMenuCommand("doc-color-cmyk");
  else app.executeMenuCommand("doc-color-rgb");
  return "OK: documento en " + MODE.toUpperCase();
}""")


def ai_join() -> str:
    """Une los trazados abiertos seleccionados en Illustrator (Object > Path > Join)."""
    return _jsx({}, """
function main(){
  var d = app.activeDocument;
  if (!d.selection || !d.selection.length) return "ERROR: seleccioná trazados abiertos.";
  app.executeMenuCommand("join");
  app.redraw();
  return "OK: trazados unidos";
}""")


def ai_concentric(rings: int = 6, max_radius: float = 0, hex_color: str = "#2c3e50",
                  width: float = 2) -> str:
    """Dibuja anillos concéntricos (círculos) centrados en el artboard."""
    return _jsx({"RINGS": int(rings), "MAXR": float(max_radius),
                 "FILL": _hex_to_rgb(hex_color), "W": float(width)}, """
function main(){
  var d = app.activeDocument;
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var cx = (ab[0]+ab[2])/2, cy = (ab[1]+ab[3])/2;
  var maxr = (MAXR > 0) ? MAXR : Math.min(ab[2]-ab[0], ab[1]-ab[3]) * 0.45;
  var step = maxr / RINGS;
  var c = new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2];
  var i;
  for (i = RINGS; i >= 1; i--) {
    var r = step * i;
    var e = d.pathItems.ellipse(cy + r, cx - r, r*2, r*2);
    e.filled = false; e.stroked = true; e.strokeColor = c; e.strokeWidth = W;
  }
  app.redraw();
  return "OK: " + RINGS + " anillos concéntricos";
}""")


def ai_sunburst(count: int = 24, radius: float = 0, hex_color: str = "#e67e22",
                width: float = 2) -> str:
    """Dibuja una ráfaga de líneas radiales (sunburst) desde el centro del artboard."""
    return _jsx({"COUNT": int(count), "RAD": float(radius),
                 "FILL": _hex_to_rgb(hex_color), "W": float(width)}, """
function main(){
  var d = app.activeDocument;
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var cx = (ab[0]+ab[2])/2, cy = (ab[1]+ab[3])/2;
  var r = (RAD > 0) ? RAD : Math.min(ab[2]-ab[0], ab[1]-ab[3]) * 0.45;
  var c = new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2];
  var i;
  for (i = 0; i < COUNT; i++) {
    var a = i / COUNT * 2 * Math.PI;
    var p = d.pathItems.add();
    p.setEntirePath([[cx, cy], [cx + r*Math.cos(a), cy + r*Math.sin(a)]]);
    p.filled = false; p.stroked = true; p.strokeColor = c; p.strokeWidth = W;
  }
  app.redraw();
  return "OK: ráfaga de " + COUNT + " líneas";
}""")


def ai_arc(start_angle: float = 0, sweep: float = 180, radius: float = 150,
           hex_color: str = "#16a085", width: float = 3) -> str:
    """Dibuja un arco (porción de círculo) centrado en el artboard. Ángulos en grados."""
    return _jsx({"START": float(start_angle), "SWEEP": float(sweep), "RAD": float(radius),
                 "FILL": _hex_to_rgb(hex_color), "W": float(width)}, """
function main(){
  var d = app.activeDocument;
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var cx = (ab[0]+ab[2])/2, cy = (ab[1]+ab[3])/2;
  var segs = Math.max(2, Math.round(Math.abs(SWEEP)/8));
  var pts = [], i;
  for (i = 0; i <= segs; i++) {
    var ang = (START + SWEEP * (i/segs)) * Math.PI / 180;
    pts.push([cx + RAD*Math.cos(ang), cy + RAD*Math.sin(ang)]);
  }
  var p = d.pathItems.add();
  p.setEntirePath(pts);
  p.closed = false; p.filled = false; p.stroked = true;
  var c = new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2];
  p.strokeColor = c; p.strokeWidth = W;
  app.redraw();
  return "OK: arco de " + SWEEP + "°";
}""")


_AI_JUST = {"left": "LEFT", "izquierda": "LEFT", "center": "CENTER", "centro": "CENTER",
            "right": "RIGHT", "derecha": "RIGHT", "justify": "FULLJUSTIFY", "justificado": "FULLJUSTIFY"}


_AI_FINDFONT = """
function findFont(name){
  try { return app.textFonts.getByName(name); } catch(e){}
  var n = String(name).toLowerCase(), i;
  for (i = 0; i < app.textFonts.length; i++) {
    var f = app.textFonts[i];
    if (String(f.name).toLowerCase().indexOf(n) !== -1 || String(f.family).toLowerCase().indexOf(n) !== -1) return f;
  }
  return null;
}
"""


def ai_area_text(text: str = "", width: float = 300, height: float = 200,
                 size: float = 18, hex_color: str = "#000000") -> str:
    """Crea un texto de área (caja de párrafo) centrado en el artboard de Illustrator."""
    return _jsx({"TXT": text, "WIDTH": float(width), "HEIGHT": float(height),
                 "SZ": float(size), "FILL": _hex_to_rgb(hex_color)}, """
function main(){
  var d = (app.documents.length) ? app.activeDocument : app.documents.add();
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var cx = (ab[0]+ab[2])/2, cy = (ab[1]+ab[3])/2;
  var rect = d.pathItems.rectangle(cy + HEIGHT/2, cx - WIDTH/2, WIDTH, HEIGHT);
  var tf = d.textFrames.areaText(rect);
  tf.contents = TXT;
  var ca = tf.textRange.characterAttributes; ca.size = SZ;
  var c = new RGBColor(); c.red=FILL[0]; c.green=FILL[1]; c.blue=FILL[2]; ca.fillColor = c;
  app.redraw();
  return "OK: texto de área creado";
}""")


def ai_font(font: str | None = None, size: float = 0, tracking: float | None = None,
            leading: float = 0) -> str:
    """Aplica fuente/tamaño/tracking/interlineado a los textos seleccionados en Illustrator."""
    return _jsx({"FONT": font, "SZ": float(size), "TRACK": (None if tracking is None else float(tracking)),
                 "LEAD": float(leading)}, _AI_FINDFONT + """
function main(){
  var d = app.activeDocument;
  // La selección de texto no siempre persiste entre scripts: si no hay, usar todos los textos del doc.
  var items = (d.selection && d.selection.length) ? d.selection : d.textFrames;
  if (!items || !items.length) return "ERROR: no hay textos en el documento.";
  var n = 0, i;
  for (i = 0; i < items.length; i++) {
    var it = items[i];
    if (it.typename !== "TextFrame") continue;
    var ca = it.textRange.characterAttributes;
    if (SZ > 0) ca.size = SZ;
    if (FONT) { var f = findFont(FONT); if (f) ca.textFont = f; }
    if (TRACK !== null) ca.tracking = TRACK;
    if (LEAD > 0) { ca.autoLeading = false; ca.leading = LEAD; }
    n++;
  }
  app.redraw();
  if (n === 0) return "ERROR: no hay textos para aplicar.";
  return "OK: tipografía aplicada a " + n + " texto(s)";
}""")


def ai_text_align(align: str = "left") -> str:
    """Alineación de párrafo (left/center/right/justify) en los textos seleccionados de Illustrator."""
    j = _AI_JUST.get((align or "").lower(), "LEFT")
    return _jsx({"J": j}, """
function main(){
  var d = app.activeDocument;
  var items = (d.selection && d.selection.length) ? d.selection : d.textFrames;
  if (!items || !items.length) return "ERROR: no hay textos en el documento.";
  var n = 0, i;
  for (i = 0; i < items.length; i++) {
    var it = items[i];
    if (it.typename !== "TextFrame") continue;
    it.textRange.paragraphAttributes.justification = Justification[J];
    n++;
  }
  app.redraw();
  if (n === 0) return "ERROR: no hay textos para alinear.";
  return "OK: alineación " + J + " en " + n + " texto(s)";
}""")


def ai_detect_faces(min_size: float = 40, tolerance: float = 0.15) -> str:
    """Detecta las CARAS de un troquel/dieline en Illustrator: busca trazados rectangulares
    cerrados, los mide y los nombra por posición (izquierda/centro/derecha × arriba/medio/abajo).
    Devuelve un JSON con cada cara {id, name, cx, cy, w, h, bounds} para luego colocar arte.
    min_size = lado mínimo (pt) para contar como cara; tolerance = cuán 'rectangular' debe ser.
    """
    return _jsx({"MIN": float(min_size), "TOL": float(tolerance)}, """
function isRectish(it, tol){
  // un path cuenta como cara si tiene ~4 vértices y bounds tipo rectángulo
  try {
    if (it.typename !== "PathItem") return false;
    if (!it.closed) return false;
    var n = it.pathPoints.length;
    if (n < 4 || n > 8) return false;            // rectángulos (con o sin esquinas redondeadas)
    var vb = it.geometricBounds;                  // [left, top, right, bottom]
    var w = vb[2]-vb[0], h = vb[1]-vb[3];
    if (w <= 0 || h <= 0) return false;
    // área del path vs área del bounding box: si se parecen, es rectangular
    var area = Math.abs(it.area);
    var boxArea = w*h;
    if (boxArea <= 0) return false;
    var ratio = area / boxArea;
    return ratio > (1 - tol);
  } catch(e){ return false; }
}
function collect(container, out){
  var i;
  for (i = 0; i < container.pageItems.length; i++){
    var it = container.pageItems[i];
    if (it.typename === "GroupItem") { collect(it, out); }
    else if (isRectish(it, TOL)) {
      var vb = it.geometricBounds; // [l,t,r,b]
      var w = vb[2]-vb[0], h = vb[1]-vb[3];
      if (Math.min(w,h) >= MIN) out.push({l:vb[0], t:vb[1], r:vb[2], b:vb[3], w:w, h:h});
    }
  }
}
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  var faces = [];
  collect(d, faces);
  if (!faces.length) return "NOFACES: no encontré caras rectangulares (¿el troquel usa rectángulos cerrados?).";
  // ordenar por área desc y descartar el contorno exterior si envuelve a casi todo
  faces.sort(function(a,b){ return (b.w*b.h)-(a.w*a.h); });
  // calcular extents globales para nombrar por posición
  var minL=faces[0].l, maxR=faces[0].r, minB=faces[0].b, maxT=faces[0].t, i;
  for (i=0;i<faces.length;i++){ if(faces[i].l<minL)minL=faces[i].l; if(faces[i].r>maxR)maxR=faces[i].r; if(faces[i].b<minB)minB=faces[i].b; if(faces[i].t>maxT)maxT=faces[i].t; }
  var totW = maxR-minL, totH = maxT-minB;
  function col(cx){ var f=(cx-minL)/totW; return f<0.34?"izquierda":(f<0.67?"centro":"derecha"); }
  function row(cy){ var f=(maxT-cy)/totH; return f<0.34?"arriba":(f<0.67?"medio":"abajo"); }
  // si la cara más grande cubre >85% del total, es el contorno → marcarla
  var outer = (faces[0].w*faces[0].h) > (totW*totH*0.85);
  var res = "FACES:[";
  var k = 0, j;
  for (j=0;j<faces.length;j++){
    var f = faces[j];
    if (outer && j===0) continue; // saltar contorno exterior
    var cx=(f.l+f.r)/2, cy=(f.t+f.b)/2;
    var name = col(cx)+"-"+row(cy);
    if (k>0) res += ",";
    res += '{"id":'+k+',"name":"'+name+'","cx":'+cx.toFixed(1)+',"cy":'+cy.toFixed(1)+
           ',"w":'+f.w.toFixed(1)+',"h":'+f.h.toFixed(1)+
           ',"l":'+f.l.toFixed(1)+',"t":'+f.t.toFixed(1)+',"r":'+f.r.toFixed(1)+',"b":'+f.b.toFixed(1)+'}';
    k++;
  }
  res += "]";
  return res;
}""")


def ai_place_in_face(image_path: str, face_l: float, face_t: float, face_r: float, face_b: float,
                     margin: float = 0.15, trace: bool = False) -> str:
    """Coloca una imagen DENTRO de una cara (rectángulo l,t,r,b) del troquel, centrada y
    escalada para entrar con `margin` (fracción de aire). trace=True le aplica Image Trace."""
    return _jsx({"PATH": image_path, "L": float(face_l), "T": float(face_t),
                 "R": float(face_r), "B": float(face_b), "MARGIN": float(margin),
                 "TRACE": bool(trace)}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  var f = new File(PATH);
  if (!f.exists) return "ERROR: no existe " + PATH;
  var d = app.activeDocument;
  var placed = d.placedItems.add();
  placed.file = f;
  var faceW = R - L, faceH = T - B;
  var availW = faceW * (1 - MARGIN), availH = faceH * (1 - MARGIN);
  var iw = placed.width, ih = placed.height;
  if (iw > 0 && ih > 0){
    var s = Math.min(availW/iw, availH/ih);
    if (s > 0 && s < 100){ placed.width = iw*s; placed.height = ih*s; }
  }
  // centrar dentro de la cara
  var cx = (L+R)/2, cy = (T+B)/2;
  placed.position = [cx - placed.width/2, cy + placed.height/2];
  if (TRACE){
    try {
      var art = placed.trace();
      var grp = art.tracing.expandTracing();
    } catch(e){ /* si falla el trace, queda la imagen colocada igual */ }
  }
  app.redraw();
  return "OK: imagen colocada en la cara (" + faceW.toFixed(0) + "x" + faceH.toFixed(0) + ")";
}""")

