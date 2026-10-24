"""An EPUB shaped like a real light-novel volume: image-only front matter off the TOC, chapters
that start mid-file at TOC anchors and run across files, several chapters in one file, and a
nav document whose landmarks nav comes first. Made-up text only."""
import zipfile
from pathlib import Path

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

# Spine order; every page lives in OEBPS/text/<name>.xhtml.
SPINE = ["cover", "plate1", "plate2", "plate3", "toc", "p6", "p7", "p8", "p9", "p10"]
IMAGES = ["cover.jpg", "plate1.jpg", "plate2.jpg", "plate3.jpg", "inline.jpg"]

P6_PARAS = ["The wind came down from the hills.", "Nobody in the village slept."]
P8_PROLOGUE = ["By morning the bridge was gone."]
P8_CH1 = ["Chapter one opens at the mill.", "The miller counted his sacks."]
P9_PARAS = ["Off the contents page, still chapter one."]
P10_CH2 = ["Chapter two begins at the river."]
P10_CH3 = ["Chapter three is short."]
P10_CH4 = ["Chapter four closes the book.", "The end."]


def _ps(paras: list[str]) -> str:
    return "".join(f"<p>{p}</p>" for p in paras)


def _img(name: str) -> str:
    return f'<p><img src="../images/{name}" alt=""/></p>'


PAGES = {
    "cover": _img("cover.jpg"),
    "plate1": _img("plate1.jpg"),
    "plate2": _img("plate2.jpg"),
    "plate3": (
        '<div><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 150">'
        '<image width="100" height="150" xlink:href="../images/plate3.jpg"/></svg></div>'
    ),
    "toc": '<p><a href="p6.xhtml#t1">Prologue</a></p><p><a href="p8.xhtml#t2">Chapter 1</a></p>',
    "p6": '<h1 id="t1">Prologue</h1>' + _ps(P6_PARAS),
    "p7": _img("inline.jpg"),
    "p8": _ps(P8_PROLOGUE) + '<h1 id="t2">Chapter 1</h1>' + _ps(P8_CH1),
    "p9": _ps(P9_PARAS),
    "p10": (
        f'<p id="t3">{P10_CH2[0]}</p>'
        f'<p id="t4">{P10_CH3[0]}</p>'
        f'<p id="t5">{P10_CH4[0]}</p>{_ps(P10_CH4[1:])}'
    ),
}

NAV = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body>
<nav epub:type="landmarks">
<ol>
<li><a epub:type="cover" href="text/cover.xhtml">Cover</a></li>
<li><a epub:type="bodymatter" href="text/p6.xhtml">Start</a></li>
</ol>
</nav>
<nav epub:type="toc">
<ol>
<li><a href="text/p6.xhtml#t1">Prologue</a></li>
<li><a href="text/p8.xhtml#t2">Chapter 1</a></li>
<li><a href="text/p10.xhtml">Part 1</a>
  <ol>
    <li><a href="text/p10.xhtml#t3">Chapter 2</a></li>
    <li><a href="text/p10.xhtml#t4">Chapter 3</a></li>
    <li><a href="text/p10.xhtml#t5">Chapter 4</a></li>
  </ol>
</li>
</ol>
</nav>
</body>
</html>
"""


def _opf() -> str:
    pages = "\n".join(
        f'<item id="{n}" href="text/{n}.xhtml" media-type="application/xhtml+xml"/>' for n in SPINE
    )
    cover = ' properties="cover-image"'
    images = "\n".join(
        f'<item id="img-{n[:-4]}" href="images/{n}" media-type="image/jpeg"'
        f'{cover if n == "cover.jpg" else ""}/>'
        for n in IMAGES
    )
    spine = "\n".join(f'<itemref idref="{n}"/>' for n in SPINE)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Split Book</dc:title>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
{pages}
{images}
</manifest>
<spine>
{spine}
</spine>
</package>
"""


def split_book(tmp_path: Path) -> Path:
    path = tmp_path / "split.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", _opf())
        zf.writestr("OEBPS/nav.xhtml", NAV)
        for name, body in PAGES.items():
            zf.writestr(f"OEBPS/text/{name}.xhtml", f"<html><body>{body}</body></html>")
        for name in IMAGES:
            zf.writestr(f"OEBPS/images/{name}", f"fake-{name}".encode())
    return path
