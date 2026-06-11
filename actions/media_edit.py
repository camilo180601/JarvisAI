"""
media_edit.py — Edición local de imágenes y PDF (sin abrir apps pesadas).

Imagen (Pillow):
  img_resize        redimensionar (max_side o width/height)
  img_convert       cambiar formato (png/jpg/webp/...)
  img_crop          recortar (box left,top,right,bottom)
  img_rotate        rotar grados
  img_watermark     texto de marca de agua
  img_remove_bg     quitar fondo (rembg — opcional, se instala al primer uso)

PDF (pypdf):
  pdf_merge         unir varios PDF
  pdf_split         dividir en páginas / rango
  pdf_extract_text  extraer texto
  pdf_info          nº de páginas, metadatos
"""
from __future__ import annotations
from pathlib import Path
from core.registry import tool


def _out_path(src: Path, suffix: str, new_ext: str | None = None) -> Path:
    ext = new_ext or src.suffix.lstrip(".")
    return src.with_name(f"{src.stem}{suffix}.{ext}")


@tool(
    name='media_edit',
    description="Edita imágenes y PDF localmente sin abrir apps pesadas. Imagen: img_resize, img_convert, img_crop, img_rotate, img_watermark, img_remove_bg (quita fondo, requiere rembg). PDF: pdf_merge, pdf_split, pdf_extract_text, pdf_info. Ej: 'redimensioná esta imagen a 800px', 'convertí a JPG', 'quitá el fondo', 'uní estos PDFs', 'extraé el texto del PDF'.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'img_resize | img_convert | img_crop | img_rotate | '
                                              'img_watermark | img_remove_bg | pdf_merge | pdf_split | '
                                              'pdf_extract_text | pdf_info'},
                    'path': {'type': 'STRING', 'description': 'Ruta del archivo de entrada'},
                    'dest': {'type': 'STRING',
                             'description': 'Ruta de salida (opcional, se autogenera)'},
                    'max_side': {'type': 'INTEGER', 'description': 'img_resize: lado máximo en px'},
                    'width': {'type': 'INTEGER', 'description': 'img_resize: ancho exacto'},
                    'height': {'type': 'INTEGER', 'description': 'img_resize: alto exacto'},
                    'format': {'type': 'STRING', 'description': 'img_convert: png|jpg|webp...'},
                    'box': {'type': 'ARRAY',
                            'items': {'type': 'INTEGER'},
                            'description': 'img_crop: [left,top,right,bottom]'},
                    'degrees': {'type': 'NUMBER', 'description': 'img_rotate: grados'},
                    'text': {'type': 'STRING', 'description': 'img_watermark: texto de la marca'},
                    'inputs': {'type': 'ARRAY',
                               'items': {'type': 'STRING'},
                               'description': 'pdf_merge: lista de PDFs a unir'},
                    'pages': {'type': 'STRING',
                              'description': "pdf_split/pdf_extract_text: rango ej '2-5'"}},
     'required': ['action']},
)
def media_edit(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "").lower().strip()

    # ───────────── IMAGEN ─────────────
    if action.startswith("img"):
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            return "Falta Pillow (pip install pillow)."
        src = Path(parameters.get("path") or parameters.get("input") or "")
        if action != "img_remove_bg" and (not src or not src.exists()):
            return f"Error: imagen inexistente ({src})."

        if action == "img_resize":
            im = Image.open(src)
            w, h = im.size
            if parameters.get("max_side"):
                m = int(parameters["max_side"])
                scale = m / max(w, h)
                if scale < 1:
                    im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            else:
                nw = int(parameters.get("width") or w)
                nh = int(parameters.get("height") or h)
                im = im.resize((nw, nh), Image.LANCZOS)
            out = Path(parameters.get("dest") or _out_path(src, "_resized"))
            im.save(out)
            return f"✓ {im.size[0]}x{im.size[1]} → {out}"

        if action == "img_convert":
            fmt = (parameters.get("format") or "png").lower().lstrip(".")
            im = Image.open(src)
            if fmt in ("jpg", "jpeg") and im.mode in ("RGBA", "P", "LA"):
                im = im.convert("RGB")
            out = Path(parameters.get("dest") or _out_path(src, "", "jpg" if fmt == "jpeg" else fmt))
            im.save(out)
            return f"✓ Convertido a {fmt.upper()} → {out}"

        if action == "img_crop":
            box = parameters.get("box")  # [left, top, right, bottom]
            if not (isinstance(box, (list, tuple)) and len(box) == 4):
                return "Error: 'box' debe ser [left, top, right, bottom]."
            im = Image.open(src).crop(tuple(int(x) for x in box))
            out = Path(parameters.get("dest") or _out_path(src, "_crop"))
            im.save(out)
            return f"✓ Recortado {im.size} → {out}"

        if action == "img_rotate":
            deg = float(parameters.get("degrees") or 90)
            im = Image.open(src).rotate(-deg, expand=True)
            out = Path(parameters.get("dest") or _out_path(src, "_rot"))
            im.save(out)
            return f"✓ Rotado {deg}° → {out}"

        if action == "img_watermark":
            text = parameters.get("text") or "JARVIS"
            im = Image.open(src).convert("RGBA")
            layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            size = max(16, im.size[0] // 18)
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", size)
            except Exception:
                font = ImageFont.load_default()
            tw = d.textlength(text, font=font)
            d.text((im.size[0] - tw - 20, im.size[1] - size - 20), text,
                   fill=(255, 255, 255, 160), font=font)
            out = Path(parameters.get("dest") or _out_path(src, "_wm", "png"))
            Image.alpha_composite(im, layer).save(out)
            return f"✓ Marca de agua → {out}"

        if action == "img_remove_bg":
            if not src or not src.exists():
                return f"Error: imagen inexistente ({src})."
            try:
                from rembg import remove
            except ImportError:
                return ("Para quitar fondo localmente instalá rembg: "
                        ".venv/bin/pip install rembg onnxruntime  (descarga un modelo ~170MB la 1ª vez).")
            data = src.read_bytes()
            out = Path(parameters.get("dest") or _out_path(src, "_nobg", "png"))
            out.write_bytes(remove(data))
            return f"✓ Fondo quitado → {out}"

        return f"Acción de imagen '{action}' no reconocida."

    # ───────────── PDF ─────────────
    if action.startswith("pdf"):
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            return "Falta pypdf (pip install pypdf)."

        if action == "pdf_merge":
            inputs = parameters.get("inputs") or parameters.get("paths") or []
            if isinstance(inputs, str):
                inputs = [s.strip() for s in inputs.split(",") if s.strip()]
            if len(inputs) < 2:
                return "Error: 'inputs' debe listar 2+ PDFs."
            writer = PdfWriter()
            for p in inputs:
                if not Path(p).exists():
                    return f"Error: no existe {p}."
                for page in PdfReader(p).pages:
                    writer.add_page(page)
            out = Path(parameters.get("dest") or Path(inputs[0]).with_name("merged.pdf"))
            with open(out, "wb") as f:
                writer.write(f)
            return f"✓ {len(inputs)} PDFs unidos → {out}"

        src = Path(parameters.get("path") or parameters.get("input") or "")
        if not src or not src.exists():
            return f"Error: PDF inexistente ({src})."

        if action == "pdf_info":
            r = PdfReader(src)
            meta = r.metadata or {}
            return (f"{src.name}: {len(r.pages)} páginas. "
                    f"Título: {meta.get('/Title', '—')}. Autor: {meta.get('/Author', '—')}.")

        if action == "pdf_extract_text":
            r = PdfReader(src)
            pages = parameters.get("pages")  # ej "1-3" o None=todas
            idxs = range(len(r.pages))
            if pages:
                try:
                    a, b = (pages.split("-") + [pages])[:2]
                    idxs = range(int(a) - 1, int(b))
                except Exception:
                    pass
            text = "\n".join((r.pages[i].extract_text() or "") for i in idxs if 0 <= i < len(r.pages))
            text = text.strip()
            if parameters.get("dest"):
                Path(parameters["dest"]).write_text(text, encoding="utf-8")
                return f"✓ Texto extraído → {parameters['dest']} ({len(text)} chars)"
            return text[:3000] + ("…" if len(text) > 3000 else "") if text else "(sin texto extraíble)"

        if action == "pdf_split":
            r = PdfReader(src)
            rng = parameters.get("pages")  # "2-5"
            out = Path(parameters.get("dest") or _out_path(src, "_split"))
            writer = PdfWriter()
            if rng:
                a, b = rng.split("-") if "-" in rng else (rng, rng)
                for i in range(int(a) - 1, int(b)):
                    if 0 <= i < len(r.pages):
                        writer.add_page(r.pages[i])
                with open(out, "wb") as f:
                    writer.write(f)
                return f"✓ Páginas {rng} → {out}"
            # sin rango: una por archivo
            folder = Path(parameters.get("dest") or src.with_suffix("")).with_name(src.stem + "_pages")
            folder.mkdir(exist_ok=True)
            for i, page in enumerate(r.pages, 1):
                w = PdfWriter()
                w.add_page(page)
                with open(folder / f"{src.stem}_{i}.pdf", "wb") as f:
                    w.write(f)
            return f"✓ {len(r.pages)} páginas separadas → {folder}"

        return f"Acción de PDF '{action}' no reconocida."

    return ("Acción no reconocida. Imagen: img_resize, img_convert, img_crop, img_rotate, "
            "img_watermark, img_remove_bg. PDF: pdf_merge, pdf_split, pdf_extract_text, pdf_info.")
