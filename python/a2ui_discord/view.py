"""Discord projection of a live a2ui-core surface. Install the `protocol` extra."""

from __future__ import annotations

import inspect
import math
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from weakref import WeakKeyDictionary

from a2ui.core.resolution import (
    ComponentNode,
    NodeResolver,
    ResolvedBinding,
    WritableBinding,
)
from a2ui.core.state import SurfaceModel

from . import _IMAGE_URL, CATALOG, SurfaceError

__all__ = ['DiscordView']


def _value(x):
    return x.value if isinstance(x, ResolvedBinding) else x


def _str(x, default=''):
    x = _value(x)
    return x if isinstance(x, str) and x else default


def _short(s, n):
    return s[:n].encode('utf-16-le')[:n * 2].decode('utf-16-le', errors='ignore')


def _row(*controls):
    return {'type': 1, 'components': list(controls)}


def _button(cid, label, style=2, disabled=False):
    return {'type': 2, 'style': style, 'label': _short(label, 80), 'custom_id': cid, 'disabled': disabled}


def _title(n, fallback):
    if not isinstance(n, ComponentNode) or n.is_placeholder:
        return fallback
    p = n.props
    access = p.get('@accessibility') or {}
    label = _str(access.get('label')) or _str(p.get('text')) or _str(p.get('label')) or _str(p.get('name'))
    if label:
        return label
    if 'child' in p:
        return _title(p['child'], fallback)
    if isinstance(p.get('children'), list):
        return ' '.join(filter(None, (_title(c, '') for c in p['children']))) or fallback
    return fallback


_DECIMAL = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')


def _field_value(n, raw):
    if not isinstance(raw, str) or len(raw.encode('utf-16-le')) > 8000:
        raise SurfaceError('Invalid modal text')
    p = n.props
    if n.type == 'Slider' or (n.type == 'TextField' and p.get('variant') == 'number' and raw):
        if not _DECIMAL.fullmatch(raw) or not math.isfinite(number := float(raw)):
            raise SurfaceError('Enter a finite decimal number')
        if n.type == 'Slider':
            low, high = p.get('min', 0), p['max']
            if not low <= number <= high:
                raise SurfaceError('Value outside slider range')
            if 'steps' in p and high > low:
                pos = (number - low) / (high - low) * p['steps']
                if abs(pos - round(pos)) > 1e-8:
                    raise SurfaceError('Value is not a slider step')
            return number
    if n.type == 'DateTimeInput' and raw:
        has_date, has_time = p.get('enableDate'), p.get('enableTime')
        fmt = 'date-time' if has_date and has_time else 'time' if has_time else 'date'
        day = r'[0-9]{4}-[0-9]{2}-[0-9]{2}'
        clock = r'[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,3})?)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])?'
        pattern = {'date': day, 'time': clock, 'date-time': day + 'T' + clock}[fmt]

        def parsed(s):
            if not re.fullmatch(pattern, s):
                raise ValueError()
            d = datetime.fromisoformat('2000-01-01T' + s if fmt == 'time' else s)
            return d if d.tzinfo else d.replace(tzinfo=UTC)
        try:
            current = parsed(raw)
            if ((lower := _str(p.get('min'))) and current < parsed(lower)
                    or (upper := _str(p.get('max'))) and current > parsed(upper)):
                raise ValueError()
        except ValueError:
            raise SurfaceError(f'Enter a valid ISO {fmt} within the allowed range') from None
    return raw


class DiscordView:
    """Mount one live SDK surface. Keep the view until its message is retired."""

    def __init__(self, surface: SurfaceModel, *, custom_text: Callable[[ComponentNode], str] | None = None):
        if surface.protocol_version != '1.0':
            raise SurfaceError('DiscordView requires an A2UI 1.0 surface')
        self._surface = surface
        self._tree = NodeResolver(surface)
        self._custom_text = custom_text
        self._choice: WeakKeyDictionary[ComponentNode, int] = WeakKeyDictionary()
        self._filters: WeakKeyDictionary[ComponentNode, str] = WeakKeyDictionary()
        self._page = 0

    def dispose(self):
        self._tree.dispose()

    def _render(self, metadata=None):
        if self._surface.disposed or self._tree.disposed:
            raise SurfaceError('Surface is no longer mounted')
        routes = {}
        dialog_page = None

        def editor(cid, caption, current, setter, *, disabled=False, placeholder='', long=False, required=False):
            # Never silently replace a long source value with a truncated prefill.
            disabled = disabled or _short(current, 4000) != current
            if not disabled:
                field = {'type': 4, 'custom_id': 'value', 'style': 2 if long else 1, 'required': required}
                if current:
                    field['value'] = current
                if placeholder:
                    field['placeholder'] = _short(placeholder, 100)
                heading = _short(caption, 45)
                dialog = {'type': 9, 'data': {'custom_id': 'edit:' + cid, 'title': heading,
                          'components': [{'type': 18, 'label': heading, 'component': field}]}}
                routes[cid] = (2, lambda _: dialog)
                routes['edit:' + cid] = (5, setter)
            return _row(_button(cid, caption + (': ' + current if current else ''), disabled=disabled))

        def render(n):
            nonlocal dialog_page
            if n is None or n.is_placeholder:
                return [{'type': 10, 'content': 'Waiting for content…' if n is None or n.state == 'pending' else 'Unavailable component'}]
            p, kind, cid = n.props, n.type, 'view:' + n.id
            catalog = n.context.component_model.catalog or self._surface.default_catalog
            if catalog is None or catalog.catalog_id != CATALOG:
                if self._custom_text:
                    return [{'type': 10, 'content': _str(self._custom_text(n), 'No content')}]
                raise SurfaceError('No Discord mapping for this catalog')
            value = _value(p.get('value'))
            writable = isinstance(p.get('value'), WritableBinding)
            access = p.get('@accessibility') or {}
            caption = _str(access.get('label')) or _str(p.get('label'), kind)
            notes = [r.get('message') for r in n.validation_results if r.get('valid') is False]
            errors = [{'type': 10, 'content': s} for s in dict.fromkeys([*n.validation_errors, *notes]) if s]
            if kind in ('Column', 'Row', 'List'):
                parts = [part for child in p.get('children', []) for part in render(child)]
                if kind == 'Row':
                    packed = []
                    for part in parts:
                        if (packed and part['type'] == packed[-1]['type'] == 1
                                and part.get('_card') == packed[-1].get('_card')
                                and all(c['type'] == 2 for row in [part, packed[-1]] for c in row['components'])
                                and len(part['components']) + len(packed[-1]['components']) <= 5):
                            packed[-1]['components'].extend(part['components'])
                        else:
                            packed.append(part)
                    return packed
                return parts
            if kind == 'Card':
                parts = render(p.get('child'))
                for part in parts:
                    part.setdefault('_card', n.id)
                return parts
            if kind in ('Text', 'Icon'):
                content = _str(p.get('text')) if kind == 'Text' else _title(n, 'Icon')
                return [{'type': 10, 'content': ('-# ' if p.get('variant') == 'caption' else '') + content}] if content else []
            if kind == 'Divider':
                return [{'type': 14}]
            if kind in ('AudioPlayer', 'Video', 'Image'):
                url = _str(p.get('url')).strip()
                desc = _str(access.get('description')) or _str(p.get('description')) or _str(access.get('label'))
                if not _IMAGE_URL.fullmatch(url) or len(url) > 512 and kind == 'AudioPlayer' and not url.startswith('attachment:'):
                    return [{'type': 10, 'content': desc or 'Media unavailable'}]
                if kind == 'AudioPlayer':
                    if url.startswith('attachment:'):
                        return ([{'type': 10, 'content': desc}] if desc else []) + [{'type': 13, 'file': {'url': url}}]
                    return [_row({'type': 2, 'style': 5, 'label': _short(desc or 'Play audio', 80), 'url': url})]
                item = {'media': {'url': url}}
                if desc:
                    item['description'] = _short(desc, 1024)
                return [{'type': 12, 'items': [item]}]
            if kind == 'Tabs':
                tabs = p.get('tabs', [])
                if not tabs:
                    return []
                i = min(self._choice.get(n, 0), len(tabs) - 1)
                routes[cid] = (3, lambda values: self._choice.__setitem__(n, int(values[0])))
                opts = [{'label': _short(_str(t.get('title'), f'Tab {j+1}'), 100), 'value': str(j), 'default': j == i}
                        for j, t in enumerate(tabs)]
                return menus(cid, opts, False, False, 'Select tab', tabs=True) + render(tabs[i]['child'])
            if kind == 'Modal':
                opened = self._choice.get(n, 0)
                trigger = p.get('trigger')
                async def toggle(_):
                    if not opened and trigger.type == 'Button':
                        result = trigger.props['action'](metadata)
                        if inspect.isawaitable(result):
                            await result
                    self._choice[n] = int(not opened)
                    self._page = 0
                routes[cid] = (2, toggle)
                entry = _row(_button(cid, _title(trigger, 'Open'), disabled=not trigger or trigger.is_placeholder or not trigger.is_valid))
                if opened:
                    contents = render(p.get('content'))
                    if dialog_page is None:
                        dialog_page = [_row(_button(cid, 'Close')), *contents]
                return [entry]
            if kind == 'Button':
                label = _str(access.get('label')) or _title(p.get('child'), caption)
                action = n.context.component_model.properties.get('action', {})
                call = action.get('functionCall', {})
                if call.get('@call') == 'openUrl' and call.get('catalogId', self._surface.default_catalog and self._surface.default_catalog.catalog_id) == CATALOG:
                    target = call.get('args', {}).get('url')
                    url = n.context.data_context.resolve_dynamic_value(target) if isinstance(target, str) or isinstance(target, dict) and set(target) == {'@path'} else None
                    if isinstance(url, str) and url.startswith('https://') and len(url) <= 512 and _IMAGE_URL.fullmatch(url) and n.is_valid:
                        return [_row({'type': 2, 'style': 5, 'label': _short(label, 80), 'url': url})]
                    return [_row(_button(cid, label, disabled=True)), *errors]
                routes[cid] = (2, lambda _: p['action'](metadata))
                return [_row(_button(cid, label, 1 if p.get('variant') == 'primary' else 2, not n.is_valid)), *errors]
            if kind == 'CheckBox':
                routes[cid] = (2, lambda _: p['value'].set(not bool(value)))
                return [_row(_button(cid, ('☑ ' if value else '☐ ') + caption, 3 if value else 2, not writable)), *errors]
            if kind == 'ChoicePicker':
                multi = p.get('variant') == 'multipleSelection'
                opts = [{'label': _short(_str(o.get('label'), o['value']) or 'Option', 100),
                         'value': str(i), 'default': o['value'] in (value or [])} for i, o in enumerate(p.get('options', []))]
                routes[cid] = (3, lambda selected: p['value'].set([p['options'][int(i)]['value'] for i in selected]))
                query = self._filters.get(n, '') if p.get('filterable') else ''
                search = [editor(cid + ':filter', 'Filter ' + caption, query, lambda s: self._filters.__setitem__(n, s))] if p.get('filterable') else []
                return search + menus(cid, opts, multi, not writable, caption, query=query) + errors
            if kind in ('TextField', 'DateTimeInput', 'Slider'):
                obscured = p.get('variant') == 'obscured'
                if obscured:
                    return [_row(_button(cid, caption + ': Secure input unavailable', disabled=True))]
                return [editor(cid, caption, '' if value is None else str(value),
                               lambda raw: p['value'].set(_field_value(n, raw)), disabled=not writable,
                               placeholder=_str(p.get('placeholder')), long=p.get('variant') == 'longText', required=kind == 'Slider'), *errors]
            raise SurfaceError(f'No Discord mapping for {kind}')

        def menus(cid, options, multi, disabled, label, tabs=False, query=''):
            # Split large catalogs into native menus. Edits preserve other chunks in a multi-select.
            visible = [o for o in options if query.lower() in o['label'].lower()]
            if not visible:
                return [{'type': 10, 'content': 'No choices available'}]
            _, assign = routes[cid]
            result = []
            for start in range(0, len(visible), 25):
                chunk = visible[start:start+25]
                key = f'{cid}:{start}'
                def select(selected, chunk=chunk):
                    retained = [o['value'] for o in options if multi and o['default'] and o not in chunk]
                    assign(retained + selected)
                routes[key] = (3, select)
                result.append(_row({'type': 3, 'custom_id': key, 'options': chunk, 'disabled': disabled,
                                    'min_values': 1 if tabs else 0, 'max_values': len(chunk) if multi else 1,
                                    'placeholder': _short(label, 150)}))
            return result

        parts = render(self._tree.root) or [{'type': 10, 'content': 'No content'}]
        parts = dialog_page or parts
        pages: list[list[dict]] = [[]]
        count = chars = 0
        group = None
        for part in parts:
            card = part.pop('_card', None)
            content = part.get('content', '')
            while True:
                chunk = _short(content, 4000)
                size = 1 + len(part.get('components', []))
                units = len(chunk.encode('utf-16-le')) // 2
                if group is not None and len(pages[-1][-1]['components']) == 10:
                    group = None
                if count + size + int(card is not None and card != group) > 37 or chars + units > 4000:
                    pages.append([])
                    count = chars = 0
                    group = None
                if card is not None and card != group:
                    pages[-1].append({'type': 17, 'components': []})
                    count += 1
                destination = pages[-1][-1]['components'] if card is not None else pages[-1]
                destination.append({**part, 'content': chunk} if content else part)
                group = card
                count += size
                chars += units
                content = content[len(chunk):]
                if not content:
                    break
        self._page = min(self._page, len(pages)-1)
        parts = pages[self._page]
        if len(pages) > 1:
            for key, delta in [('prev', -1), ('next', 1)]:
                routes[key] = (2, lambda _, d=delta: setattr(self, '_page', self._page + d))
            parts.append(_row(_button('prev', 'Previous page', disabled=self._page == 0),
                              _button('next', 'Next page', disabled=self._page == len(pages)-1)))
        rows = [p for part in parts for p in (part['components'] if part['type'] == 17 else [part]) if p['type'] == 1]
        active = {c['custom_id']: c for part in rows for c in part['components']
                  if 'custom_id' in c and not c.get('disabled')}
        return {'flags': 32768, 'allowed_mentions': {'parse': []}, 'components': parts}, active, routes

    def message(self) -> dict[str, Any]:
        """Render the current page as a Discord message or edit."""
        return self._render()[0]

    async def interact(self, data: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Handle authorized interaction.data. Return the Discord type 7 or 9 response."""
        _, active, routes = self._render(metadata)
        cid = data.get('custom_id') if isinstance(data, dict) else None
        if not isinstance(cid, str) or cid.removeprefix('edit:') not in active or cid not in routes:
            raise SurfaceError('Unknown or disabled control')
        kind, handler = routes[cid]
        arg = None
        if kind == 5:
            children = data.get('components')
            if not isinstance(children, list) or len(children) != 1 or not isinstance(children[0], dict):
                raise SurfaceError('Invalid modal submission')
            field = children[0].get('component')
            if children[0].get('type') != 18 or not isinstance(field, dict) or field.get('type') != 4 or field.get('custom_id') != 'value':
                raise SurfaceError('Invalid modal field')
            arg = field.get('value')
            if not isinstance(arg, str) or _short(arg, 4000) != arg:
                raise SurfaceError('Invalid modal text')
        elif data.get('component_type') != kind:
            raise SurfaceError('Wrong interaction type')
        elif kind == 3:
            arg, c = data.get('values'), active[cid]
            allowed = {o['value'] for o in c['options']}
            if (not isinstance(arg, list) or not c['min_values'] <= len(arg) <= c['max_values']
                    or any(not isinstance(v, str) or v not in allowed for v in arg) or len(set(arg)) != len(arg)):
                raise SurfaceError('Invalid selection')
        result = handler(arg)
        if inspect.isawaitable(result):
            result = await result
        # Function return values are application data, never Discord callbacks.
        if kind == 2 and 'edit:' + cid in routes:
            return result
        return {'type': 7, 'data': self.message()}
