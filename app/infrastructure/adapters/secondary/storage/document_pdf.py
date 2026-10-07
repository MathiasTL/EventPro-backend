"""PDF portable para el flujo administrativo, sin bibliotecas GTK en Windows."""

from html import escape
from io import BytesIO


def render_document(title: str, paragraphs: list[str]) -> bytes:
    from reportlab.lib.styles import getSampleStyleSheet  # type: ignore[import-untyped]
    from reportlab.platypus import (  # type: ignore[import-untyped]
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    output = BytesIO()
    styles = getSampleStyleSheet()
    story = [Paragraph(escape(title), styles["Title"]), Spacer(1, 16)]
    for text in paragraphs:
        story.extend([Paragraph(escape(text), styles["BodyText"]), Spacer(1, 10)])
    SimpleDocTemplate(output, title=title, author="EventPro").build(story)
    return output.getvalue()
