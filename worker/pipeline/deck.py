"""python-pptx deck assembly with a consistent (non-default) theme."""

from __future__ import annotations

from datetime import date

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)

INK = RGBColor(0x1B, 0x1F, 0x3B)       # near-black navy — body text
ACCENT = RGBColor(0x2F, 0x5D, 0xD1)     # primary accent — bars, titles
ACCENT_LIGHT = RGBColor(0xE8, 0xEE, 0xFC)
PAPER = RGBColor(0xFF, 0xFF, 0xFF)
MUTED = RGBColor(0x6B, 0x72, 0x80)

TITLE_FONT = "Georgia"
BODY_FONT = "Calibri"

MAX_REFS_PER_SLIDE = 10


def _set_background(slide, color: RGBColor) -> None:
    background = slide.background
    background.fill.solid()
    background.fill.fore_color.rgb = color


def _accent_bar(slide, prs: Presentation) -> None:
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Emu(0), Emu(0), Emu(int(0.18 * 914400)), prs.slide_height
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    bar.shadow.inherit = False


def _add_title_slide(prs: Presentation, deck_title: str, topic: str) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    _set_background(slide, INK)

    title_box = slide.shapes.add_textbox(Inches(0.9), Inches(2.6), Inches(11.5), Inches(1.8))
    tf = title_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = deck_title
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.name = TITLE_FONT
    p.font.color.rgb = PAPER

    subtitle_box = slide.shapes.add_textbox(Inches(0.9), Inches(4.3), Inches(11.5), Inches(0.8))
    sp = subtitle_box.text_frame.paragraphs[0]
    sp.text = f"Research synthesis on: {topic}  ·  Generated {date.today().isoformat()}"
    sp.font.size = Pt(16)
    sp.font.name = BODY_FONT
    sp.font.color.rgb = ACCENT_LIGHT


def _add_content_slide(prs: Presentation, slide_data: dict, references: list[dict]) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_background(slide, PAPER)
    _accent_bar(slide, prs)

    title_box = slide.shapes.add_textbox(Inches(0.6), Inches(0.5), Inches(12.2), Inches(1.0))
    tp = title_box.text_frame.paragraphs[0]
    tp.text = slide_data["title"]
    tp.font.size = Pt(28)
    tp.font.bold = True
    tp.font.name = TITLE_FONT
    tp.font.color.rgb = INK

    body_box = slide.shapes.add_textbox(Inches(0.7), Inches(1.7), Inches(11.8), Inches(5.2))
    tf = body_box.text_frame
    tf.word_wrap = True

    citation_indices = slide_data.get("citation_indices", [])
    for i, bullet in enumerate(slide_data.get("bullets", [])):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        marker = f" [{', '.join(str(c) for c in citation_indices)}]" if citation_indices else ""
        p.text = f"•  {bullet}{marker}"
        p.font.size = Pt(20)
        p.font.name = BODY_FONT
        p.font.color.rgb = INK
        p.space_after = Pt(14)

    cited = [r for r in references if r["index"] in citation_indices]
    if cited:
        notes = slide.notes_slide
        notes.notes_text_frame.text = "\n".join(
            f"[{r['index']}] {r['title']} — {r['authors']} ({r['year']})" for r in cited
        )


def _add_reference_slides(prs: Presentation, references: list[dict]) -> None:
    for start in range(0, len(references), MAX_REFS_PER_SLIDE):
        chunk = references[start : start + MAX_REFS_PER_SLIDE]
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _set_background(slide, PAPER)
        _accent_bar(slide, prs)

        title_box = slide.shapes.add_textbox(Inches(0.6), Inches(0.5), Inches(12.2), Inches(0.8))
        tp = title_box.text_frame.paragraphs[0]
        tp.text = "References" if start == 0 else "References (cont.)"
        tp.font.size = Pt(26)
        tp.font.bold = True
        tp.font.name = TITLE_FONT
        tp.font.color.rgb = INK

        body_box = slide.shapes.add_textbox(Inches(0.7), Inches(1.5), Inches(11.8), Inches(5.5))
        tf = body_box.text_frame
        tf.word_wrap = True
        for i, ref in enumerate(chunk):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            url_part = f" — {ref['url']}" if ref.get("url") else ""
            p.text = f"[{ref['index']}] {ref['title']}. {ref['authors']} ({ref['year']}){url_part}"
            p.font.size = Pt(13)
            p.font.name = BODY_FONT
            p.font.color.rgb = MUTED
            p.space_after = Pt(8)


def build_deck(deck_data: dict, topic: str, output_path: str) -> None:
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    _add_title_slide(prs, deck_data["deck_title"], topic)
    for slide_data in deck_data["slides"]:
        _add_content_slide(prs, slide_data, deck_data["references"])
    _add_reference_slides(prs, deck_data["references"])

    prs.save(output_path)
