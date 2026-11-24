import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { setImmediate } from 'node:timers/promises';
import { MessageProcessor, basicCatalog } from '@a2ui/web_core/v1_0';
import { SurfaceError } from 'a2ui-discord';
import { DiscordView } from 'a2ui-discord/view';

const studio = JSON.parse(readFileSync(new URL('../conformance/studio.json', import.meta.url), 'utf8'));
const walk = parts => parts.flatMap(p => [p, ...walk(p.components ?? [])]);

function mount(t) {
  const outbound = [];
  const processor = new MessageProcessor([basicCatalog], undefined, {
    unifiedOutbound: true, outboundListener: m => { outbound.push(m); },
  });
  processor.processMessages(studio[0]);
  const view = new DiscordView(processor.getSurface('studio'));
  t.after(() => { view.dispose(); processor.dispose(); });
  const control = label => {
    const c = walk(view.message().components).find(c => c.label === label || c.placeholder === label);
    assert.ok(c, label); return c;
  };
  const click = (label, data = {}) => {
    const c = control(label);
    return view.interact({ custom_id: c.custom_id, component_type: c.type, ...data });
  };
  const edit = async (label, value) => {
    const dialog = await click(label);
    assert.equal(dialog.type, 9);
    return view.interact({ custom_id: dialog.data.custom_id, components: [{ type: 18,
      component: { type: 4, custom_id: dialog.data.components[0].component.custom_id, value } }] });
  };
  const update = (...components) => processor.processMessages({ version: '1.0', updateComponents: { surfaceId: 'studio', components } });
  return { processor, view, outbound, control, click, edit, update };
}

test('stream a studio; edit, filter, dispatch, change tab, preview media and delete', async t => {
  const { processor, view, outbound, control, click, edit } = mount(t);
  assert.equal(view.message().components[0].content, 'Waiting for content…');
  processor.processMessages(studio.slice(1));
  assert.equal(control('Help').url, 'https://example.org/studio');
  await assert.rejects(click('Save mix'), SurfaceError);
  assert.equal((await click('☐ 2. Wind')).type, 7);
  await edit('Title', 'Night');
  for (const [label, bad, good] of [['Gain: 0.25', '0.2', '0.75'], ['Air date: 2028-02-01', '2028-02-30', '2028-02-29']]) {
    await assert.rejects(edit(label, bad), SurfaceError);
    await edit(label, good);
  }
  await edit('Filter Channels', 'MON');
  const options = control('Channels').options;
  assert.deepEqual(options.map(o => o.label), ['Mono']);
  await click('Channels', { values: [options[0].value] });
  const save = { custom_id: control('Save mix').custom_id, component_type: 2 }, metadata = { extensions: { source: 'studio' } };
  await view.interact(save, { metadata });
  assert.equal(outbound[0].action.name, 'saveMix');
  assert.deepEqual(outbound[0].action.metadata, metadata);
  assert.deepEqual(outbound[0].action.context, { title: 'Night', wind: true, gain: .75, when: '2028-02-29', mix: ['stereo', 'mono'] });
  assert.deepEqual(processor.getRendererDataModel('1.0').surfaces.studio.tracks,
    [{ title: 'Rain', enabled: true }, { title: 'Wind', enabled: true }]);
  await click('Select tab', { values: ['1'] });
  await assert.rejects(view.interact(save), SurfaceError);
  const { data } = await click('Preview media');
  assert.equal(outbound.at(-1).action.name, 'openPreview');
  assert.deepEqual(data.components.filter(p => p.type === 12).map(p => p.items[0].media.url),
    ['attachment://cover.png', 'https://example.org/demo.mp4']);
  assert.equal(data.components.at(-1).file.url, 'attachment://sample.ogg');
  assert.ok(!walk(data.components).some(c => c.type === 3));
  await click('Close'); control('Select tab');
  processor.processMessages({ version: '1.0', deleteSurface: { surfaceId: 'studio' } });
  assert.throws(() => view.message(), SurfaceError);
});

test('split oversized cards without losing text or exposing secure input', async t => {
  const { update, click, control, view } = mount(t), text = 'x' + '🌦'.repeat(2200);
  update({ id: 'root', component: 'Card', child: 'col' },
    { id: 'col', component: 'Column', children: ['blob', ...Array(45).fill('item'), 'secret'] },
    { id: 'blob', component: 'Text', text }, { id: 'item', component: 'Text', text: '|' },
    { id: 'secret', component: 'TextField', label: 'PIN', variant: 'obscured', value: 'private-sentinel' });
  let all = '';
  for (let i = 0; i < 10; i++) {
    const page = walk(view.message().components), chunk = page.filter(c => c.type === 10).map(c => c.content).join('');
    assert.ok(page.length <= 40 && chunk.length <= 4000);
    assert.ok(!JSON.stringify(page).includes('private-sentinel')); all += chunk;
    if (control('Next page').disabled) break;
    await click('Next page');
  }
  assert.equal(all, text + '|'.repeat(45));
  await assert.rejects(click('PIN: Secure input unavailable'), SurfaceError);
});

test('correlate an agent RPC result with bound text; deny renderer-only RPC', async t => {
  const { update, processor, view, outbound } = mount(t);
  update({ id: 'root', component: 'Text', text: { '@call': 'mixStatus', args: { track: 'Wind' } } });
  await setImmediate();
  const { callAgentFunction: call } = outbound[0];
  assert.deepEqual(call.callFunction.args, { track: 'Wind' });
  processor.processMessages({ version: '1.0', agentFunctionResponse: { functionCallId: call.functionCallId, value: 'Ready' } });
  await setImmediate();
  assert.deepEqual(view.message().components, [{ type: 10, content: 'Ready' }]);
  const [reply] = await processor.processMessagesAsync({ version: '1.0', callRendererFunction: { surfaceId: 'studio',
    functionCallId: 'request-one', callFunction: { '@call': 'openUrl', catalogId: basicCatalog.id, args: { url: 'https://example.org' } } } });
  assert.equal(reply.rendererFunctionResponse.functionCallId, 'request-one');
  assert.equal(reply.rendererFunctionResponse.error.code, 'INVALID_FUNCTION_CALL');
});
