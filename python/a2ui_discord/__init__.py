"""Translate a documented subset of A2UI 1.0 to Discord Components V2."""

import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

__all__ = ['CATALOG', 'Surface', 'SurfaceError']
CATALOG = 'https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json'
Object = dict[str, Any]
_IMAGE_URL = re.compile(
    r'attachment://[A-Za-z0-9_-][A-Za-z0-9_.-]*|'
    r'https://[A-Za-z0-9]+(?:(?:-+|\.)[A-Za-z0-9]+)*'
    r"(?:[/?#](?:[A-Za-z0-9._~!$&'()*+,;=:@/?#-]|%[0-9A-Fa-f]{2})*)?"
)


class SurfaceError(ValueError):
    """Invalid or unsupported JSON input, binding, component, or interaction."""


def _object(value, required='', optional='') -> Object:
    if not isinstance(value, dict):
        raise SurfaceError('Expected an object')
    keys = set(required.split())
    if missing := keys - value.keys():
        raise SurfaceError(f'Missing fields: {sorted(missing)}')
    if extra := value.keys() - keys - set(optional.split()):
        raise SurfaceError(f'Unsupported fields: {sorted(extra)}')
    return value


def _text(value, limit=None) -> str:
    if not isinstance(value, str) or not value or (limit and len(value) > limit):
        raise SurfaceError('Expected non-empty text' + (f' (maximum {limit} characters)' if limit else ''))
    return value


def _index(nodes) -> dict[str, Object]:
    if not isinstance(nodes, list):
        raise SurfaceError('Expected a list of components')
    indexed = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get('component'), str):
            raise SurfaceError('Expected a component object with a component type')
        ref = _text(node.get('id'))
        if ref in indexed:
            raise SurfaceError(f'Duplicate component ID: {ref}')
        indexed[ref] = node
    return indexed


def _location(model, path):
    """Return a parent and key; array slots and intermediate parents must exist."""
    if not isinstance(path, str) or not path.startswith('/') or re.search(r'~(?![01])', path):
        raise SurfaceError('Expected an absolute JSON Pointer')
    tokens = path[1:].split('/')
    parent = model
    for i, token in enumerate(tokens):
        key: str | int = token.replace('~1', '/').replace('~0', '~')
        if isinstance(parent, list):
            if (not re.fullmatch(r'0|[1-9][0-9]*', token) or len(token) > len(str(len(parent)))
                    or int(token) >= len(parent)):
                raise SurfaceError(f'Invalid array index in {path}')
            key = int(token)
        elif not isinstance(parent, dict):
            raise SurfaceError(f'Expected an object or array in {path}')
        if i == len(tokens) - 1:
            return parent, key
        if isinstance(parent, dict) and key not in parent:
            raise SurfaceError(f'Missing parent in {path}')
        parent = parent[key]


class Surface:
    """One surface per Discord message. This class performs no I/O."""

    def __init__(self, envelope: Object) -> None:
        _object(envelope, 'version createSurface')
        source = _object(envelope['createSurface'], 'surfaceId catalogId components', 'dataModel')
        if envelope['version'] != '1.0' or source['catalogId'] != CATALOG:
            raise SurfaceError('Expected the A2UI 1.0 basic catalog')
        self.id = _text(source['surfaceId'])
        self.model: Object = deepcopy(source.get('dataModel', {}))
        if not isinstance(self.model, dict):
            raise SurfaceError('dataModel must be an object')
        self._nodes = _index(deepcopy(source['components']))
        self._render()

    def snapshot(self) -> Object:
        """Return an independent createSurface envelope, including current selections."""
        return {'version': '1.0', 'createSurface': {
            'catalogId': CATALOG, 'surfaceId': self.id, 'components': deepcopy(list(self._nodes.values())),
            'dataModel': deepcopy(self.model)}}

    def apply(self, envelope: Object) -> None:
        """Apply one complete renderable update atomically, or raise SurfaceError."""
        if not isinstance(envelope, dict) or envelope.get('version') != '1.0':
            raise SurfaceError('Expected a version 1.0 update')
        operations = envelope.keys() - {'version'}
        if len(operations) != 1 or not operations <= {'updateComponents', 'updateDataModel'}:
            raise SurfaceError('Expected exactly one updateComponents or updateDataModel message')
        operation, = operations
        data = envelope[operation]
        nodes = self._nodes
        model = self.model
        if operation == 'updateComponents':
            _object(data, 'surfaceId components')
            nodes = nodes | _index(data['components'])
        else:
            _object(data, 'surfaceId value', 'path')
            path, value = data.get('path', '/'), data['value']
            if path == '/':
                model = value
            else:
                model = deepcopy(model)
                parent, key = _location(model, path)
                if value is not None:
                    parent[key] = value
                elif isinstance(parent, list):
                    parent.pop(key)
                else:
                    parent.pop(key, None)
        if data['surfaceId'] != self.id:
            raise SurfaceError('Update belongs to a different surface')
        updated = Surface({'version': '1.0', 'createSurface': {
            'surfaceId': self.id, 'catalogId': CATALOG, 'components': list(nodes.values()), 'dataModel': model}})
        self._nodes, self.model = updated._nodes, updated.model

    def _value(self, value):
        if not isinstance(value, dict) or not any(k.startswith('@') for k in value):
            return value  # A literal, including a literal object (DynamicValue).
        if '@path' not in value:
            raise SurfaceError('Only @path bindings are supported, not @call functions')
        path = _object(value, '@path')['@path']
        if path == '/':
            return self.model
        parent, key = _location(self.model, path)
        if isinstance(parent, dict) and key not in parent:
            raise SurfaceError(f'Missing bound field: {path}')
        return parent[key]

    def _picker(self, node, cid):
        _object(node, 'id component options value', 'variant label')
        options = node['options']
        variant = node.get('variant', 'mutuallyExclusive')
        if (variant not in ('mutuallyExclusive', 'multipleSelection')
                or not isinstance(options, list) or not 1 <= len(options) <= 25):
            raise SurfaceError('Expected a choice picker with 1–25 options')
        _object(node['value'], '@path')
        selected = self._value(node['value'])
        maximum = len(options) if variant == 'multipleSelection' else 1
        if (not isinstance(selected, list) or len(selected) > maximum
                or any(not isinstance(v, str) for v in selected) or len(set(selected)) != len(selected)):
            raise SurfaceError('Invalid bound selection')
        rendered, values = [], set()
        for option in options:
            _object(option, 'value label')
            value = _text(option['value'], 100)
            if value in values:
                raise SurfaceError('Duplicate picker option')
            values.add(value)
            rendered.append({'value': value, 'label': _text(self._value(option['label']), 100),
                             'default': value in selected})
        if not values.issuperset(selected):
            raise SurfaceError('Invalid bound selection')
        control = {'type': 3, 'custom_id': cid, 'options': rendered}
        if variant == 'multipleSelection':
            control['max_values'] = maximum
        if 'label' in node:
            control['placeholder'] = _text(self._value(node['label']), 150)
        return control

    def _event(self, node: Object) -> Object:
        event = _object(_object(node['action'], 'event')['event'], 'name', 'context userMessage')
        context = event.get('context', {})
        if not isinstance(context, dict):
            raise SurfaceError('Action context must be an object')
        if any(value is None for value in context.values()):
            raise SurfaceError('A literal action context value cannot be null')
        action: Object = {
            'surfaceId': self.id, 'sourceComponentId': node['id'], 'name': _text(event['name']),
            'context': {k: deepcopy(self._value(v)) for k, v in context.items()},
        }
        if 'userMessage' in event:
            action['userMessage'] = _text(self._value(event['userMessage']))
        return action

    def _render(self) -> tuple[Object, dict[str, Object]]:
        parts: list[Object] = []
        controls, seen = {}, set()

        def take(ref):
            ref = _text(ref)
            if ref in seen or ref not in self._nodes:
                raise SurfaceError(f'Repeated or missing component: {ref}')
            seen.add(ref)
            return self._nodes[ref]

        def text(n, limit):
            _object(n, 'id component text')
            if n['component'] != 'Text':
                raise SurfaceError('Expected a Text component')
            return _text(self._value(n['text']), limit)

        def control(n):
            cid = _text('a2ui:' + n['id'], 100)
            controls[cid] = n
            if n['component'] == 'ChoicePicker':
                return self._picker(n, cid)
            if n['component'] != 'Button':
                raise SurfaceError('A Row can contain only buttons or a single picker')
            _object(n, 'id component child action', 'variant')
            variant = n.get('variant', 'default')
            if variant not in ('default', 'primary'):
                raise SurfaceError('Only default and primary buttons are supported')
            self._event(n)  # Reject invalid actions before offering a clickable button.
            return {'type': 2, 'style': 1 if variant == 'primary' else 2,
                    'custom_id': cid, 'label': text(take(n['child']), 80)}

        pending = ['root']
        while pending:
            n = take(pending.pop())
            kind = n['component']
            if kind == 'Column':
                _object(n, 'id component children')
                if not isinstance(n['children'], list):
                    raise SurfaceError('Expected explicit Column children')
                pending.extend(reversed(n['children']))
            elif kind == 'Row':
                _object(n, 'id component children')
                children = n['children']
                if not isinstance(children, list) or not 1 <= len(children) <= 5:
                    raise SurfaceError('Expected 1–5 controls in a Row')
                row = [control(take(child)) for child in children]
                if len(row) > 1 and any(item['type'] != 2 for item in row):
                    raise SurfaceError('A picker must occupy its own Row')
                parts.append({'type': 1, 'components': row})
            elif kind == 'Divider':
                _object(n, 'id component', 'axis')
                if n.get('axis', 'horizontal') != 'horizontal':
                    raise SurfaceError('Only horizontal dividers are supported')
                parts.append({'type': 14})
            elif kind == 'Text':
                parts.append({'type': 10, 'content': text(n, 4000)})
            elif kind == 'Image':
                _object(n, 'id component url', 'description')
                url = _text(self._value(n['url']))
                if not _IMAGE_URL.fullmatch(url):
                    raise SurfaceError('Expected an HTTPS image URL or attachment://filename')
                item: Object = {'media': {'url': url}}
                if 'description' in n:
                    item['description'] = _text(self._value(n['description']), 1024)
                parts.append({'type': 12, 'items': [item]})
            elif kind in ('ChoicePicker', 'Button'):
                parts.append({'type': 1, 'components': [control(n)]})
            else:
                raise SurfaceError(f'Unsupported component: {kind}')
        if not parts or len(parts) + len(controls) + 1 > 40 or sum(len(p.get('content', '')) for p in parts) > 4000:
            raise SurfaceError('Empty or oversized Discord message')
        return {'flags': 32768, 'allowed_mentions': {'parse': []},
                'components': [{'type': 17, 'components': parts}]}, controls

    def message(self) -> Object:
        """Render a fresh create/edit payload. Raises SurfaceError before any I/O."""
        return self._render()[0]

    def interact(self, data: Object) -> Object | None:
        """Handle verified Discord interaction.data; return an A2UI action or a local edit (None)."""
        if not isinstance(data, dict) or not isinstance(data.get('custom_id'), str):
            raise SurfaceError('Expected a Discord component interaction')
        _, controls = self._render()
        n = controls.get(data['custom_id'])
        if not n:
            raise SurfaceError('Unknown control on this message')
        if n['component'] == 'ChoicePicker':
            values = data.get('values')
            if data.get('component_type') != 3 or not isinstance(values, list) or not values:
                raise SurfaceError('Invalid selection')
            self.apply({'version': '1.0', 'updateDataModel': {
                'surfaceId': self.id, 'path': n['value']['@path'], 'value': values}})
            return None
        if data.get('component_type') != 2:
            raise SurfaceError('Expected a button click')
        return {'version': '1.0', 'action': {**self._event(n), 'timestamp': datetime.now(UTC).isoformat()}}
