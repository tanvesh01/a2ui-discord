import json
import unittest
from datetime import datetime, timedelta

from a2ui_discord import CATALOG, Surface, SurfaceError
from examples.audit import audit_card, handle


class AuditTest(unittest.TestCase):
    def test_select_then_review(self):
        surface = Surface(audit_card())
        msg = surface.message()
        self.assertEqual(msg['flags'], 32768)
        self.assertEqual(msg['allowed_mentions'], {'parse': []})
        container, = msg['components']
        self.assertEqual(container['type'], 17)
        _summary, select_row, _detail, button_row = container['components']
        self.assertEqual([part['type'] for part in container['components']], [10, 1, 10, 1])
        picker, = select_row['components']
        button, = button_row['components']
        self.assertEqual((picker['type'], button['type']), (3, 2))
        self.assertEqual(button['style'], 1)
        callback, event = handle(surface, {'data': {'component_type': 3, 'custom_id': picker['custom_id'], 'values': ['backup']}})
        self.assertIsNone(event)
        self.assertEqual(callback['type'], 7)
        parts = callback['data']['components'][0]['components']
        self.assertIn('March backup', parts[2]['content'])
        self.assertEqual([o['default'] for o in parts[1]['components'][0]['options']], [False, True, False])
        _, event = handle(surface, {'data': {'component_type': 2, 'custom_id': button['custom_id']}})
        self.assertEqual(event['action']['context'], {'finding': ['backup']})
        self.assertEqual(event['action']['name'], 'reviewFinding')
        self.assertEqual(event['action']['surfaceId'], 'quarterly-audit')

    def test_unknown_input_leaves_selection_unchanged(self):
        surface = Surface(audit_card())
        before = surface.message()
        for cid, kind, values in [('bogus', 3, ['backup']), ('a2ui:picker', 3, ['other']),
                                  ('a2ui:picker', 2, ['backup']), ('a2ui:picker', 3, ['owner', 'backup'])]:
            with self.assertRaises(ValueError):
                surface.interact({'component_type': kind, 'custom_id': cid, 'values': values})
        self.assertEqual(surface.message(), before)

    def test_unsupported_control_is_not_silently_dropped(self):
        envelope = audit_card()
        envelope['createSurface']['components'][1]['component'] = 'Video'
        with self.assertRaisesRegex(ValueError, 'Unsupported component: Video'):
            Surface(envelope)

    def test_restore_and_edit_after_restart(self):
        original = Surface(audit_card())
        original.interact({'component_type': 3, 'custom_id': 'a2ui:picker', 'values': ['rotation']})
        restored = Surface(json.loads(json.dumps(original.snapshot())))
        restored.apply({'version': '1.0', 'updateDataModel': {
            'surfaceId': restored.id, 'path': '/detail', 'value': 'Updated by agent'}})
        self.assertIn('Updated by agent', json.dumps(restored.message()))
        self.assertNotIn('Updated by agent', json.dumps(original.message()))
        action = restored.interact({'component_type': 2, 'custom_id': 'a2ui:review'})
        self.assertEqual(action['action']['context'], {'finding': ['rotation']})

    def test_replace_layout_retires_old_controls(self):
        surface = Surface(audit_card())
        surface.apply({'version': '1.0', 'updateComponents': {'surfaceId': surface.id, 'components': [
            {'id': 'root', 'component': 'Column', 'children': ['summary', 'closed']},
            {'id': 'closed', 'component': 'Text', 'text': 'Review closed'}]}})
        self.assertEqual([n['content'] for n in surface.message()['components'][0]['components']],
                         ['## Quarterly audit\n3 open findings', 'Review closed'])
        with self.assertRaises(SurfaceError):
            surface.interact({'component_type': 2, 'custom_id': 'a2ui:review'})

    def test_invalid_updates_preserve_working_card(self):
        surface = Surface(audit_card())
        expected = surface.snapshot()
        for update in [
            {'updateDataModel': {'surfaceId': 'different', 'path': '/detail', 'value': 'wrong'}},
            {'updateDataModel': {'surfaceId': surface.id, 'path': '/selected', 'value': ['unknown']}},
            {'updateComponents': {'surfaceId': surface.id, 'components': [
                {'id': 'root', 'component': 'Column', 'children': ['root']}]}}
        ]:
            with self.subTest(update=update), self.assertRaises(SurfaceError):
                surface.apply({'version': '1.0', **update})
            self.assertEqual(surface.snapshot(), expected)

    def test_option_limit(self):
        envelope = audit_card()
        options = [{'value': str(i), 'label': f'Item {i}'} for i in range(25)]
        picker = next(n for n in envelope['createSurface']['components'] if n['id'] == 'picker')
        picker['options'] = options
        self.assertIn('Item 24', json.dumps(Surface(envelope).message()))
        options.append({'value': '25', 'label': 'One too many'})
        with self.assertRaises(SurfaceError):
            Surface(envelope).message()


class SurfaceTest(unittest.TestCase):
    def test_selection_validates_other_controls_bound_to_same_key(self):
        pickers = [
            {'id': name, 'component': 'ChoicePicker', 'value': {'@path': '/size'},
             'options': [{'label': size, 'value': size} for size in sizes]}
            for name, sizes in [('full', ['small', 'large']), ('limited', ['small'])]
        ]
        surface = Surface({'version': '1.0', 'createSurface': {
            'surfaceId': 'sizes', 'catalogId': CATALOG, 'dataModel': {'size': []},
            'components': [{'id': 'root', 'component': 'Column', 'children': ['full', 'limited']}, *pickers]}})
        data = {'component_type': 3, 'custom_id': 'a2ui:full', 'values': ['small']}
        surface.interact(data)
        before = surface.snapshot()
        with self.assertRaises(SurfaceError):
            surface.interact({**data, 'values': ['large']})
        self.assertEqual(surface.snapshot(), before)
        self.assertEqual(surface.message(), Surface(before).message())

    def test_default_button_emits_current_context_and_message(self):
        event = {'name': 'submit', 'context': {'item': {'kind': 'note'}}, 'userMessage': {'@path': '/message'}}
        envelope = {'version': '1.0', 'createSurface': {
            'surfaceId': 'form', 'catalogId': CATALOG, 'dataModel': {'message': 'Draft'},
            'components': [{'id': 'root', 'component': 'Button', 'child': 'label', 'action': {'event': event}},
                           {'id': 'label', 'component': 'Text', 'text': 'Submit'}]}}
        surface = Surface(envelope)
        button, = surface.message()['components'][0]['components'][0]['components']
        self.assertEqual(button['style'], 2)
        surface.apply({'version': '1.0', 'updateDataModel': {'surfaceId': 'form', 'value': {'message': 'Ready'}}})
        response = surface.interact({'component_type': 2, 'custom_id': button['custom_id']})
        self.assertEqual(response['version'], '1.0')
        action = response['action']
        self.assertEqual(datetime.fromisoformat(action.pop('timestamp')).utcoffset(), timedelta(0))
        self.assertEqual(action, {'name': 'submit', 'sourceComponentId': 'root', 'surfaceId': 'form',
                                  'userMessage': 'Ready', 'context': {'item': {'kind': 'note'}}})
        action['context']['item'].clear()
        self.assertEqual(surface.snapshot()['createSurface']['components'], envelope['createSurface']['components'])

    def test_message_limits_count_text_and_nested_controls(self):
        # One container, one row, one button and 37 text displays = 40 components.
        texts = [{'id': str(i), 'component': 'Text', 'text': 'x'} for i in range(37)]
        texts[0]['text'] = 'x' * 3964  # 4000 characters across all displays.
        root = {'id': 'root', 'component': 'Column', 'children': ['ok', *(n['id'] for n in texts)]}
        surface = Surface({'version': '1.0', 'createSurface': {
            'surfaceId': 'limits', 'catalogId': CATALOG, 'components': [root, *texts,
                {'id': 'ok', 'component': 'Button', 'child': 'label', 'action': {'event': {'name': 'ok'}}},
                {'id': 'label', 'component': 'Text', 'text': 'OK'}]}})
        self.assertEqual(len(surface.message()['components'][0]['components']), 38)
        for changes in [[{**texts[0], 'text': texts[0]['text'] + 'x'}],
                        [{**root, 'children': [*root['children'], 'extra']},
                         {**texts[0], 'text': 'short'}, {**texts[1], 'id': 'extra'}]]:
            with self.assertRaises(SurfaceError):
                surface.apply({'version': '1.0', 'updateComponents': {'surfaceId': 'limits', 'components': changes}})
