# -*- coding: utf-8 -*-
"""adobe/common.py — helpers de documento compartidos (abrir/guardar/cerrar/info)."""
from __future__ import annotations
from core.adobe_templates import _jsx, _hex_to_rgb, _esc


def doc_open(path: str) -> str:
    return _jsx({"PATH": path}, """
function main(){
  var f = new File(PATH);
  if (!f.exists) return "ERROR: no existe " + PATH;
  app.open(f);
  return "OK: abierto " + f.name;
}""")


def doc_save() -> str:
    return _jsx({}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento abierto.";
  app.activeDocument.save();
  return "OK: guardado";
}""")


def doc_close(app_key: str) -> str:
    # enum de cierre sin guardar difiere entre apps
    enum = "SaveOptions.NO" if app_key == "indesign" else "SaveOptions.DONOTSAVECHANGES"
    return _jsx({}, """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento abierto.";
  app.activeDocument.close(""" + enum + """);
  return "OK: cerrado";
}""")


def doc_info(app_key: str) -> str:
    if app_key == "illustrator":
        body = """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  return "📐 " + d.name + " | mesas: " + d.artboards.length +
         " | capas: " + d.layers.length + " | objetos: " + d.pageItems.length;
}"""
    elif app_key == "indesign":
        body = """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  return "📄 " + d.name + " | páginas: " + d.pages.length +
         " | capas: " + d.layers.length;
}"""
    else:  # photoshop
        body = """
function main(){
  if (app.documents.length === 0) return "ERROR: no hay documento.";
  var d = app.activeDocument;
  return "🖼️ " + d.name + " | " + d.width.as("px") + "x" + d.height.as("px") + "px" +
         " | capas: " + d.layers.length + " | " + d.resolution + "ppi";
}"""
    return _jsx({}, body)

