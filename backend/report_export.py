"""
report_export —— 报表导出器

把 report_service 产出的规范化报表结构渲染成二进制文件：
    to_excel(report) -> bytes   (openpyxl 生成 .xlsx)
    to_pdf(report)   -> bytes   (reportlab 生成 .pdf，中文用内置 STSong-Light)

规范化结构见 report_service.py 顶部 docstring。
"""

from __future__ import annotations

from io import BytesIO

# ============================================================
# Excel
# ============================================================
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

_HEAD_FILL = PatternFill('solid', fgColor='0F766E')
_HEAD_FONT = Font(bold=True, color='FFFFFF', size=11)
_HDR_FONT = Font(bold=True, size=11)
_TITLE_FONT = Font(bold=True, size=15, color='0F766E')
_SUB_FONT = Font(italic=True, size=10, color='6B7280')
_CELL_ALIGN = Alignment(vertical='center', wrap_text=True)
_HEAD_ALIGN = Alignment(horizontal='center', vertical='center', wrap_text=True)
_THIN = Side(style='thin', color='D1D5DB')
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def to_excel(report: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = '报表'

    # 标题区
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)
    c = ws.cell(row=1, column=1, value=report.get('title', ''))
    c.font = _TITLE_FONT
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=8)
    s = ws.cell(row=2, column=1, value=report.get('subtitle', ''))
    s.font = _SUB_FONT

    row = 4
    for section in report.get('sections', []):
        row = _write_section(ws, row, section)
        row += 1  # 节间空行

    _autosize_columns(ws)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_section(ws, row: int, section: dict) -> int:
    # 小节标题（合并 8 列）
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
    c = ws.cell(row=row, column=1, value=section.get('heading', ''))
    c.font = _HDR_FONT
    c.fill = PatternFill('solid', fgColor='E5F0EF')
    row += 1

    for table in section.get('tables', []):
        headers = table.get('headers', [])
        rows = table.get('rows', [])

        # 表头
        for col, h in enumerate(headers, start=1):
            cell = ws.cell(row=row, column=col, value=str(h))
            cell.font = _HEAD_FONT
            cell.fill = _HEAD_FILL
            cell.alignment = _HEAD_ALIGN
            cell.border = _BORDER
        row += 1

        # 数据
        for r in rows:
            for col, v in enumerate(r, start=1):
                cell = ws.cell(row=row, column=col, value=str(v))
                cell.alignment = _CELL_ALIGN
                cell.border = _BORDER
            row += 1

        row += 1  # 表间空行
    return row


def _autosize_columns(ws) -> None:
    """按内容宽度估算列宽（上限 60 字符）"""
    widths = {}
    for row in ws.iter_rows():
        for cell in row:
            v = str(cell.value) if cell.value is not None else ''
            # 中文字符按 2 个字符宽度估算
            length = sum(2 if ord(ch) > 127 else 1 for ch in v)
            col = cell.column
            widths[col] = max(widths.get(col, 0), length)
    for col, w in widths.items():
        from openpyxl.utils import get_column_letter
        ws.column_dimensions[get_column_letter(col)].width = min(max(w + 2, 10), 60)


# ============================================================
# PDF
# ============================================================
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# 内置中文字体（Adobe CID 字体，无需外部字体文件）
_FONT = 'STSong-Light'
pdfmetrics.registerFont(UnicodeCIDFont(_FONT))

_PAGE_W, _PAGE_H = A4
_MARGIN = 14 * mm
_USABLE = _PAGE_W - 2 * _MARGIN


def to_pdf(report: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=_MARGIN, bottomMargin=_MARGIN,
        title=report.get('title', '报表'),
    )
    story = [
        Paragraph(report.get('title', ''), _style(16, bold=True, color='#0F766E')),
        Spacer(1, 2 * mm),
        Paragraph(report.get('subtitle', ''), _style(9.5, color='#6B7280')),
        Spacer(1, 4 * mm),
    ]

    for section in report.get('sections', []):
        story.append(Paragraph(section.get('heading', ''), _style(11, bold=True)))
        story.append(Spacer(1, 2 * mm))
        for table in section.get('tables', []):
            story.append(_pdf_table(table))
            story.append(Spacer(1, 4 * mm))

    doc.build(story)
    return buf.getvalue()


def _style(size: float, bold: bool = False, color: str = '#111827') -> ParagraphStyle:
    return ParagraphStyle(
        's', fontName=_FONT, fontSize=size,
        leading=size * 1.4, textColor=colors.HexColor(color),
        spaceAfter=0, spaceBefore=0,
        # STSong-Light 无 bold 变体，用颜色/字号区分层级
    )


def _pdf_table(table: dict) -> Table:
    headers = table.get('headers', [])
    rows = table.get('rows', [])
    ncols = max(len(headers), *(len(r) for r in rows) if rows else [0])

    # 列多则字号小，保证可容纳
    if ncols <= 4:
        fsize = 9.0
    elif ncols <= 8:
        fsize = 7.5
    else:
        fsize = 6.5

    head_style = _style(fsize, color='#FFFFFF')
    cell_style = _style(fsize)

    data = [[Paragraph(str(h), head_style) for h in headers]]
    for r in rows:
        data.append([Paragraph(str(c) if c is not None else '—', cell_style) for c in r])

    colw = _USABLE / ncols
    tbl = Table(data, colWidths=[colw] * ncols, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), _FONT),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F766E')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D1D5DB')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')]),
    ]))
    return tbl