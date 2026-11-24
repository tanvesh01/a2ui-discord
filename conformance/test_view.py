"""Live protocol contract. Run with the installed [protocol] extra."""

import asyncio
import json
import unittest
from pathlib import Path

from a2ui.core.basic_catalog.v1_0 import BasicCatalog
from a2ui.core.processing import MessageProcessor, MessageProcessorOptions
from a2ui_discord import CATALOG, SurfaceError
from a2ui_discord.view import DiscordView


def walk(parts):
    for part in parts:
        yield part
        yield from walk(part.get('components', []))


class ProtocolTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.actions, self.outbound = [], []
        self.processor = MessageProcessor([BasicCatalog()], self.actions.append,
            MessageProcessorOptions(outbound_listener=self.outbound.append))
        self.addCleanup(self.processor.dispose)
        create, *self.updates = json.loads(Path(__file__).with_name('studio.json').read_text())
        self.processor.process_messages(create)
        self.surface = self.processor.model.get_surface('studio')
        self.view = DiscordView(self.surface)
        self.addCleanup(self.view.dispose)

    def control(self, label):
        return next(p for p in walk(self.view.message()['components']) if label in (p.get('label'), p.get('placeholder')))

    def click(self, label, **data):
        c = self.control(label)
        return self.view.interact({'custom_id': c['custom_id'], 'component_type': c['type'], **data})

    async def edit(self, label, value):
        dialog = await self.click(label)
        self.assertEqual(dialog['type'], 9)
        field = dialog['data']['components'][0]['component']
        return await self.view.interact({'custom_id': dialog['data']['custom_id'], 'components': [
            {'type': 18, 'component': {'type': 4, 'custom_id': field['custom_id'], 'value': value}}]})

    def components(self, *components):
        self.processor.process_messages({'version': '1.0', 'updateComponents': {'surfaceId': 'studio', 'components': list(components)}})

    async def test_stream_edit_dispatch_and_delete(self):
        self.assertEqual(self.view.message()['components'][0]['content'], 'Waiting for content…')
        self.processor.process_messages(self.updates)
        self.assertEqual(self.control('Help')['url'], 'https://example.org/studio')
        with self.assertRaises(SurfaceError):
            await self.click('Save mix')
        self.assertEqual((await self.click('☐ 2. Wind'))['type'], 7)
        await self.edit('Title', 'Night')
        for label, bad, good in [('Gain: 0.25', '0.2', '0.75'), ('Air date: 2028-02-01', '2028-02-30', '2028-02-29')]:
            with self.assertRaises(SurfaceError):
                await self.edit(label, bad)
            await self.edit(label, good)
        await self.edit('Filter Channels', 'MON')
        options = self.control('Channels')['options']
        self.assertEqual([o['label'] for o in options], ['Mono'])
        await self.click('Channels', values=[options[0]['value']])
        save = self.control('Save mix')['custom_id']
        metadata = {'extensions': {'source': 'studio'}}
        await self.view.interact({'custom_id': save, 'component_type': 2}, metadata=metadata)
        self.assertEqual(self.actions[0]['metadata'], metadata)
        self.assertEqual(self.actions[0]['name'], 'saveMix')
        self.assertEqual(self.actions[0]['context'], {'title': 'Night', 'wind': True, 'gain': .75,
            'when': '2028-02-29', 'mix': ['stereo', 'mono']})
        self.assertEqual(self.processor.get_renderer_data_model('1.0')['surfaces']['studio']['tracks'],
                         [{'title': 'Rain', 'enabled': True}, {'title': 'Wind', 'enabled': True}])
        await self.click('Select tab', values=['1'])
        with self.assertRaises(SurfaceError):
            await self.view.interact({'custom_id': save, 'component_type': 2})
        opened = (await self.click('Preview media'))['data']['components']
        self.assertEqual(self.actions[-1]['name'], 'openPreview')
        self.assertEqual([p['items'][0]['media']['url'] for p in opened if p['type'] == 12],
                         ['attachment://cover.png', 'https://example.org/demo.mp4'])
        self.assertEqual(opened[-1]['file']['url'], 'attachment://sample.ogg')
        self.assertFalse(any(p['type'] == 3 for p in walk(opened)))
        await self.click('Close')
        self.control('Select tab')
        self.processor.process_messages({'version': '1.0', 'deleteSurface': {'surfaceId': 'studio'}})
        with self.assertRaises(SurfaceError):
            self.view.message()

    async def test_page_limits_and_secure_input(self):
        text = 'x' + '🌦' * 2200
        self.components({'id': 'root', 'component': 'Card', 'child': 'col'},
            {'id': 'col', 'component': 'Column', 'children': ['blob', *['item'] * 45, 'secret']},
            {'id': 'blob', 'component': 'Text', 'text': text}, {'id': 'item', 'component': 'Text', 'text': '|'},
            {'id': 'secret', 'component': 'TextField', 'label': 'PIN', 'variant': 'obscured', 'value': 'private-sentinel'})
        chunks = []
        for _ in range(10):
            page = list(walk(self.view.message()['components']))
            self.assertLessEqual(len(page), 40)
            chunk = ''.join(p['content'] for p in page if p['type'] == 10)
            self.assertLessEqual(len(chunk.encode('utf-16-le')), 8000)
            self.assertNotIn('private-sentinel', str(page))
            chunks.append(chunk)
            if self.control('Next page')['disabled']:
                break
            await self.click('Next page')
        self.assertEqual(''.join(chunks), text + '|' * 45)
        with self.assertRaises(SurfaceError):
            await self.click('PIN: Secure input unavailable')

    async def test_rpc_answer_updates_bound_text(self):
        self.components({'id': 'root', 'component': 'Text', 'text': {'@call': 'mixStatus', 'args': {'track': 'Wind'}}})
        self.view.message()
        call, = [m['callAgentFunction'] for m in self.outbound if 'callAgentFunction' in m]
        self.assertEqual(call['callFunction']['args'], {'track': 'Wind'})
        self.processor.process_messages({'version': '1.0', 'agentFunctionResponse': {'functionCallId': call['functionCallId'], 'value': 'Ready'}})
        async with asyncio.timeout(1):
            while self.view.message()['components'] != [{'type': 10, 'content': 'Ready'}]:
                await asyncio.sleep(0)
        [reply] = await self.processor.process_messages_async({'version': '1.0', 'callRendererFunction': {'surfaceId': 'studio',
            'functionCallId': 'request-one', 'callFunction': {'catalogId': CATALOG, '@call': 'openUrl', 'args': {'url': 'https://example.org'}}}})
        self.assertEqual(reply['rendererFunctionResponse']['functionCallId'], 'request-one')
        self.assertEqual(reply['rendererFunctionResponse']['error']['code'], 'INVALID_FUNCTION_CALL')


if __name__ == '__main__':
    unittest.main()
