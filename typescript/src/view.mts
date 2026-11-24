/** A Discord view over the official SDK's live, resolved surface. */
import { type ActionDispatchOptions, type ComponentNode, NodeResolver, ResolvedBinding, type SurfaceModel, WritableBinding,
  isComponentNode, peekValue } from '@a2ui/web_core/v1_0';
import { CATALOG, SurfaceError } from './index.js';
import { imageUrl } from './media.js';

type Option = { label: string; value: string; default: boolean };
type Button = { type: 2; style: number; label: string; custom_id?: string; url?: string; disabled?: boolean };
type Menu = { type: 3; custom_id: string; options: Option[]; disabled: boolean; min_values: number; max_values: number; placeholder: string };
type Part = { type: 1; components: (Button | Menu)[] } | { type: 10; content: string } | { type: 14 }
  | { type: 12; items: { media: { url: string }; description?: string }[] } | { type: 13; file: { url: string } };
type Container = { type: 17; components: Part[] };
type Message = { flags: 32768; allowed_mentions: { parse: [] }; components: (Part | Container)[] };
type Dialog = { type: 9; data: { custom_id: string; title: string; components: { type: 18; label: string;
  component: { type: 4; custom_id: string; style: number; required: boolean; value?: string; placeholder?: string } }[] } };
type Route = { type: 2; run: () => unknown; dialog?: Dialog } | { type: 3; run: (v: string[]) => void }
  | { type: 5; run: (v: string) => void };

function fail(s: string): never { throw new SurfaceError(s); }
function obj(x: unknown): Record<string, unknown> {
  return x && typeof x === 'object' && !Array.isArray(x) ? x as Record<string, unknown> : {};
}
function array(x: unknown): unknown[] { return Array.isArray(x) ? x : []; }
function unbind(x: unknown): unknown { return x instanceof ResolvedBinding ? x.value : x; }
function str(x: unknown, fallback = ''): string {
  const value = unbind(x);
  return typeof value === 'string' && value ? value : fallback;
}
function short(s: string, n: number) {
  const chunk = s.slice(0, n);
  return s.length > n && /[\uDC00-\uDFFF]/u.test(s[n]) ? chunk.replace(/[\uD800-\uDBFF]$/u, '') : chunk;
}
function row(...components: (Button | Menu)[]): Part { return { type: 1, components }; }
function button(id: string, label: string, style = 2, disabled = false): Button {
  return { type: 2, style, label: short(label, 80), custom_id: id, disabled };
}
function title(n: unknown, fallback: string): string {
  if (!isComponentNode(n) || n.isPlaceholder) return fallback;
  const p = peekValue(n.props);
  return str(obj(p['@accessibility']).label) || str(p.text) || str(p.label) || str(p.name)
    || (p.child ? title(p.child, '') : '') || array(p.children).map(c => title(c, '')).filter(Boolean).join(' ') || fallback;
}

function fieldValue(n: ComponentNode, raw: string): number | string {
  const p = peekValue(n.props);
  if (raw.length > 4000) return fail('Invalid modal text');
  if (n.type === 'Slider' || (p.variant === 'number' && raw)) {
    const v = Number(raw);
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/u.test(raw) || !Number.isFinite(v)) fail('Enter a finite decimal number');
    if (n.type === 'Slider') {
      const low = Number(p.min ?? 0), high = Number(p.max);
      if (!(low <= v && v <= high)) fail('Value outside slider range');
      if (p.steps !== undefined && high > low) {
        const pos = (v - low) / (high - low) * Number(p.steps);
        if (Math.abs(pos - Math.round(pos)) > 1e-8) fail('Value is not a slider step');
      }
      return v;
    }
  }
  if (n.type === 'DateTimeInput' && raw) {
    const mode = p.enableTime ? p.enableDate ? 'date-time' : 'time' : 'date';
    const bad = () => fail(`Enter a valid ISO ${mode} within the allowed range`);
    const stamp = (s: string) => {
      const day = mode === 'time' ? '2000-01-01' : s.slice(0, 10);
      const clock = mode === 'date' ? '00:00' : mode === 'time' ? s : s.slice(11);
      if (mode === 'date' && day !== s || mode === 'date-time' && s[10] !== 'T'
          || !/^\d{4}-\d{2}-\d{2}$/u.test(day) || day.startsWith('0000')
          || !/^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,3})?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?$/u.test(clock)) bad();
      const midnight = new Date(day + 'T00:00Z');
      if (!Number.isFinite(midnight.valueOf()) || !midnight.toISOString().startsWith(day + 'T')) bad();
      return Date.parse(`${day}T${clock}${/[Z+-]/u.test(clock) ? '' : 'Z'}`);
    };
    const v = stamp(raw), min = str(p.min), max = str(p.max);
    if ((min && v < stamp(min)) || (max && v > stamp(max))) bad();
  }
  return raw;
}

/** Mount once per Discord message. Keep the view until the surface is retired. */
export class DiscordView {
  #surface: SurfaceModel;
  #tree: NodeResolver;
  #choice = new WeakMap<ComponentNode, number>();
  #filters = new WeakMap<ComponentNode, string>();
  #customText?: (node: ComponentNode) => string;
  #page = 0;

  constructor(surface: SurfaceModel, options: { customText?: (node: ComponentNode) => string } = {}) {
    if (surface.protocolVersion !== '1.0') fail('DiscordView requires an A2UI 1.0 surface');
    this.#surface = surface;
    this.#tree = new NodeResolver(surface);
    this.#customText = options.customText;
  }
  dispose(): void { this.#tree.dispose(); }

  #render(dispatch?: ActionDispatchOptions) {
    if (this.#surface.disposed || this.#tree.disposed) fail('Surface is no longer mounted');
    const routes = new Map<string, Route>();
    const cards = new Map<Part, string>();
    let dialogPage: Part[] | undefined;
    const editor = (cid: string, caption: string, current: string, setter: (v: string) => void,
      disabled = false, placeholder = '', long = false, required = false): Part => {
      disabled ||= current.length > 4000;
      if (!disabled) {
        const heading = short(caption, 45);
        const dialog: Dialog = { type: 9, data: { custom_id: 'edit:' + cid, title: heading, components: [{ type: 18,
          label: heading, component: { type: 4, custom_id: 'value', style: long ? 2 : 1, required,
            ...(current && { value: current }), ...(placeholder && { placeholder: short(placeholder, 100) }) } }] } };
        routes.set(cid, { type: 2, dialog, run: () => undefined });
        routes.set('edit:' + cid, { type: 5, run: setter });
      }
      return row(button(cid, caption + (current ? ': ' + current : ''), 2, disabled));
    };
    const menus = (cid: string, options: Option[], multi: boolean, disabled: boolean, label: string,
      tabs: boolean, assign: (values: string[]) => void, query = ''): Part[] => {
      const visible = options.filter(o => o.label.toLowerCase().includes(query.toLowerCase()));
      if (!visible.length) return [{ type: 10, content: 'No choices available' }];
      const result: Part[] = [];
      for (let start = 0; start < visible.length; start += 25) {
        const chunk = visible.slice(start, start + 25), key = `${cid}:${start}`;
        routes.set(key, { type: 3, run: values => assign([...options.filter(o =>
          multi && o.default && !chunk.includes(o)).map(o => o.value), ...values]) });
        result.push(row({ type: 3, custom_id: key, options: chunk, disabled, min_values: tabs ? 1 : 0,
          max_values: multi ? chunk.length : 1, placeholder: short(label, 150) }));
      }
      return result;
    };
    const render = (n: unknown): Part[] => {
      if (!isComponentNode(n) || n.isPlaceholder) return [{ type: 10, content:
        !isComponentNode(n) || n.state === 'pending' ? 'Waiting for content…' : 'Unavailable component' }];
      const p = peekValue(n.props), cid = 'view:' + n.id;
      if ((n.context?.componentModel.catalog ?? this.#surface.defaultCatalog)?.id !== CATALOG) {
        if (this.#customText) return [{ type: 10, content: str(this.#customText(n), 'No content') }];
        fail('No Discord mapping for this catalog');
      }
      const binding = p.value, value = unbind(binding), writable = binding instanceof WritableBinding;
      const access = obj(p['@accessibility']);
      const caption = str(access.label) || str(p.label, n.type);
      const notes = array(p.validationResults).map(obj).filter(r => r.valid === false).map(r => r.message);
      const errors: Part[] = [...new Set([...array(p.validationErrors), ...notes])].flatMap(e => typeof e === 'string' && e ? [{ type: 10, content: e }] : []);
      switch (n.type) {
        case 'Row': case 'Column': case 'List': {
          const out: Part[] = [];
          for (const part of array(p.children).flatMap(render)) {
            const prev = out.at(-1);
            if (n.type === 'Row' && prev?.type === 1 && part.type === 1 && prev.components.length + part.components.length <= 5
                && cards.get(prev) === cards.get(part)
                && [...part.components, ...prev.components].every(c => c.type === 2)) prev.components.push(...part.components);
            else out.push(part);
          }
          return out;
        }
        case 'Card': {
          const parts = render(p.child);
          for (const part of parts) if (!cards.has(part)) cards.set(part, n.id);
          return parts;
        }
        case 'Text': case 'Icon': {
          const content = n.type === 'Text' ? str(p.text) : title(n, 'Icon');
          return content ? [{ type: 10, content: (p.variant === 'caption' ? '-# ' : '') + content }] : [];
        }
        case 'Divider': return [{ type: 14 }];
        case 'Image': case 'Video': case 'AudioPlayer': {
          const url = str(p.url).trim(), desc = str(access.description) || str(p.description) || str(access.label), file = url.startsWith('attachment:');
          if (!imageUrl.test(url) || (n.type === 'AudioPlayer' && !file && url.length > 512)) return [{ type: 10, content: desc || 'Media unavailable' }];
          if (n.type === 'AudioPlayer') {
            if (file) return [...(desc ? [{ type: 10 as const, content: desc }] : []), { type: 13, file: { url } }];
            return [row({ type: 2, style: 5, label: short(desc || 'Play audio', 80), url })];
          }
          return [{ type: 12, items: [{ media: { url }, ...(desc && { description: short(desc, 1024) }) }] }];
        }
        case 'Tabs': {
          const tabs = array(p.tabs).map(obj);
          if (!tabs.length) return [];
          const i = Math.min(this.#choice.get(n) ?? 0, tabs.length - 1);
          const options = tabs.map((t, j) => ({ label: short(str(t.title, `Tab ${j + 1}`), 100), value: String(j), default: j === i }));
          return [...menus(cid, options, false, false, 'Select tab', true, v => this.#choice.set(n, Number(v[0]))), ...render(tabs[i].child)];
        }
        case 'Modal': {
          const open = this.#choice.get(n);
          const trigger = p.trigger;
          routes.set(cid, { type: 2, run: async () => {
            const action = isComponentNode(trigger) && trigger.type === 'Button' && peekValue(trigger.props).action;
            if (!open && typeof action === 'function') await action(dispatch);
            this.#choice.set(n, Number(!open)); this.#page = 0;
          } });
          if (open) {
            const contents = render(p.content);
            dialogPage ??= [row(button(cid, 'Close')), ...contents];
          }
          return [row(button(cid, title(trigger, 'Open'), 2, !isComponentNode(trigger) || trigger.isPlaceholder || peekValue(trigger.props).isValid === false))];
        }
        case 'Button': {
          const label = str(access.label) || title(p.child, caption);
          const call = obj(obj(n.context?.componentModel.properties.action).functionCall);
          if (call['@call'] === 'openUrl' && (call.catalogId ?? this.#surface.defaultCatalog?.id) === CATALOG) {
            const target = obj(call.args).url;
            const url = typeof target === 'string' || (Object.keys(obj(target)).length === 1 && typeof obj(target)['@path'] === 'string')
              ? n.context?.dataContext.resolveDynamicValue(target) : undefined;
            if (p.isValid !== false && typeof url === 'string' && url.startsWith('https://') && url.length <= 512 && imageUrl.test(url)) {
              return [row({ type: 2, style: 5, label: short(label, 80), url })];
            }
            return [row(button(cid, label, 2, true)), ...errors];
          }
          const action = p.action;
          routes.set(cid, { type: 2, run: () => typeof action === 'function' ? action(dispatch) : fail('Invalid button action') });
          return [row(button(cid, label, p.variant === 'primary' ? 1 : 2, p.isValid === false)), ...errors];
        }
        case 'CheckBox': {
          routes.set(cid, { type: 2, run: () => writable && binding.set(!value) });
          return [row(button(cid, (value ? '☑ ' : '☐ ') + caption, value ? 3 : 2, !writable)), ...errors];
        }
        case 'ChoicePicker': {
          const multi = p.variant === 'multipleSelection', options = array(p.options).map(obj);
          const opts = options.map((o, i) => ({ label: short(str(o.label, str(o.value, 'Option')), 100),
            value: String(i), default: array(value).includes(o.value) }));
          const query = p.filterable ? this.#filters.get(n) ?? '' : '';
          const search = p.filterable ? [editor(cid + ':filter', 'Filter ' + caption, query, s => this.#filters.set(n, s))] : [];
          return [...search, ...menus(cid, opts, multi, !writable, caption, false, v => writable && binding.set(v.map(i => options[Number(i)].value)), query), ...errors];
        }
        case 'TextField': case 'Slider': case 'DateTimeInput': {
          if (p.variant === 'obscured') return [row(button(cid, caption + ': Secure input unavailable', 2, true))];
          return [editor(cid, caption, value == null ? '' : String(value), raw => writable && binding.set(fieldValue(n, raw)),
            !writable, str(p.placeholder), p.variant === 'longText', n.type === 'Slider'), ...errors];
        }
        default: return fail(`No Discord mapping for ${n.type}`);
      }
    };
    const parts = render(peekValue(this.#tree.rootNode));
    if (!parts.length) parts.push({ type: 10, content: 'No content' });
    const pages: Message['components'][] = [[]];
    let count = 0, chars = 0;
    let group: string | undefined, container: Container | undefined;
    for (const part of dialogPage ?? parts) {
      const card = cards.get(part);
      let content = part.type === 10 ? part.content : '';
      do {
        const chunk = short(content, 4000), size = 1 + (part.type === 1 ? part.components.length : 0);
        if (container?.components.length === 10) group = undefined;
        if (count + size + Number(card !== undefined && card !== group) > 37 || chars + chunk.length > 4000) {
          pages.push([]); count = chars = 0; group = undefined;
        }
        if (card !== undefined && card !== group) {
          container = { type: 17, components: [] }; pages.at(-1)!.push(container); count++;
        }
        const output = card === undefined ? pages.at(-1)! : container!.components;
        output.push(part.type === 10 ? { type: 10, content: chunk } : part);
        group = card;
        count += size; chars += chunk.length;
        content = content.slice(chunk.length);
      } while (content);
    }
    this.#page = Math.min(this.#page, pages.length - 1);
    const components = pages[this.#page];
    if (pages.length > 1) {
      routes.set('prev', { type: 2, run: () => --this.#page });
      routes.set('next', { type: 2, run: () => ++this.#page });
      components.push(row(button('prev', 'Previous page', 2, this.#page === 0), button('next', 'Next page', 2, this.#page === pages.length - 1)));
    }
    const active = new Map<string, Button | Menu>();
    for (const part of components.flatMap(p => p.type === 17 ? p.components : [p])) {
      if (part.type === 1) for (const c of part.components) if (c.custom_id && !c.disabled) active.set(c.custom_id, c);
    }
    const message: Message = { flags: 32768, allowed_mentions: { parse: [] }, components };
    return { message, routes, active };
  }

  message(): Message { return this.#render().message; }

  /** Handle authorized interaction.data, returning a type 7 update or type 9 modal. */
  async interact(input: unknown, dispatch?: ActionDispatchOptions): Promise<Dialog | { type: 7; data: Message }> {
    const data = obj(input), id = str(data.custom_id);
    const { active, routes } = this.#render(dispatch);
    const control = active.get(id.replace(/^edit:/u, '')), route = routes.get(id);
    if (!control || !route) return fail('Unknown or disabled control');
    if (route.type === 5) {
      const [label] = array(data.components).map(obj), field = obj(label?.component);
      if (array(data.components).length !== 1 || label.type !== 18 || field.type !== 4 || field.custom_id !== 'value' || typeof field.value !== 'string' || field.value.length > 4000) return fail('Invalid modal submission');
      route.run(field.value);
    } else if (data.component_type !== route.type) fail('Wrong interaction type');
    else if (route.type === 3) {
      const values = data.values;
      if (control.type !== 3 || !Array.isArray(values) || values.length < control.min_values || values.length > control.max_values
          || new Set(values).size !== values.length || !values.every(v => control.options.some(o => o.value === v))) return fail('Invalid selection');
      route.run(values);
    } else if (route.dialog) return route.dialog;
    else await route.run();
    return { type: 7, data: this.message() };
  }
}
