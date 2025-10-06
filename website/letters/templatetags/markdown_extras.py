from __future__ import annotations

import html
import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.*)$')
HORIZONTAL_RULE = re.compile(r'^\s*([-*_]){3,}\s*$')
BULLET_PATTERN = re.compile(r'^[-*]\s+')
ORDERED_PATTERN = re.compile(r'^(\d+)\.\s+')
BOLD_PATTERN = re.compile(r'\*\*(.+?)\*\*')
ITALIC_PATTERN = re.compile(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)')
CODE_PATTERN = re.compile(r'`([^`]+)`')
LINK_PATTERN = re.compile(r'\[([^\]]+)\]\((https?://[^\)\s]+)\)')


def _process_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = LINK_PATTERN.sub(r'<a href="\2" rel="nofollow noopener" target="_blank">\1</a>', escaped)
    escaped = CODE_PATTERN.sub(r'<code>\1</code>', escaped)
    escaped = BOLD_PATTERN.sub(r'<strong>\1</strong>', escaped)
    escaped = ITALIC_PATTERN.sub(r'<em>\1</em>', escaped)
    return escaped


def _render_lines(lines: list[str]) -> str:
    rendered: list[str] = []
    current_list: str | None = None

    def close_list() -> None:
        nonlocal current_list
        if current_list:
            rendered.append(f'</{current_list}>')
            current_list = None

    for raw_line in lines:
        line = raw_line.rstrip('\n')
        if not line.strip():
            close_list()
            rendered.append('')
            continue

        hr_match = HORIZONTAL_RULE.match(line)
        if hr_match:
            close_list()
            rendered.append('<hr>')
            continue

        header_match = HEADER_PATTERN.match(line)
        if header_match:
            close_list()
            level = len(header_match.group(1))
            content = _process_inline(header_match.group(2).strip())
            rendered.append(f'<h{level}>{content}</h{level}>')
            continue

        stripped = line.lstrip()
        if BULLET_PATTERN.match(stripped):
            content = _process_inline(BULLET_PATTERN.sub('', stripped, count=1).strip())
            if current_list != 'ul':
                close_list()
                rendered.append('<ul>')
                current_list = 'ul'
            rendered.append(f'<li>{content}</li>')
            continue

        ordered_match = ORDERED_PATTERN.match(stripped)
        if ordered_match:
            content = _process_inline(ORDERED_PATTERN.sub('', stripped, count=1).strip())
            if current_list != 'ol':
                close_list()
                start_attr = f' start="{ordered_match.group(1)}"' if ordered_match.group(1) != '1' else ''
                rendered.append(f'<ol{start_attr}>')
                current_list = 'ol'
            rendered.append(f'<li>{content}</li>')
            continue

        if stripped.startswith('>'):
            close_list()
            content = _process_inline(stripped[1:].strip())
            rendered.append(f'<blockquote>{content}</blockquote>')
            continue

        close_list()
        rendered.append(f'<p>{_process_inline(line.strip())}</p>')

    close_list()
    return '\n'.join(part for part in rendered if part is not None)


@register.filter(name='markdownify')
def markdownify(value: str | None) -> str:
    if not value:
        return ''

    lines = value.replace('\r\n', '\n').split('\n')
    html_output = _render_lines(lines)
    return mark_safe(html_output)
