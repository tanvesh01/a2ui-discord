import { imageUrl } from './media.js';

/** The supported A2UI 1.0 basic catalog. No catalog or network resource is fetched. */
export const CATALOG = 'https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json';

type Json = null | boolean | number | string | Json[] | Obj;
type Obj = { [key: string]: Json };
type Option = { value: string; label: string; default: boolean };
type Control = { type: 2; style: 1 | 2; custom_id: string; label: string }
  | { type: 3; custom_id: string; options: Option[]; placeholder?: string; max_values?: number };
type Part = { type: 10; content: string } | { type: 14 } | { type: 1; components: Control[] }
  | { type: 12; items: [{ media: { url: string }; description?: string }] };
export interface DiscordMessage {
  flags: 32768;
  allowed_mentions: { parse: [] };
  components: [{ type: 17; components: Part[] }];
}
export interface ActionEnvelope {
  version: '1.0';
  action: { name: string; surfaceId: string; sourceComponentId: string; context: Obj; timestamp: string; userMessage?: string };
}

export class SurfaceError extends Error {
  override name = 'SurfaceError';
}

function fail(message: string): never { throw new SurfaceError(message); }
function isObject(value: unknown): value is Obj {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function object(value: unknown): Obj {
  return isObject(value) ? value : fail('Expected a JSON object');
}
function fields(value: unknown, required: string[], optional: string[] = []): Obj {
  const result = object(value);
  for (const key of required) if (!Object.hasOwn(result, key)) fail(`Missing field: ${key}`);
  for (const key of Object.keys(result)) {
    if (!required.includes(key) && !optional.includes(key)) fail(`Unsupported field: ${key}`);
  }
  return result;
}
function text(value: unknown, limit?: number): string {
  if (typeof value !== 'string' || !value || (limit !== undefined && [...value].length > limit)) {
    return fail('Expected non-empty text within the component limit');
  }
  return value;
}
function location(model: Obj, path: unknown) {
  if (typeof path !== 'string' || path[0] !== '/' || /~(?![01])/u.test(path)) return fail('Expected an absolute JSON Pointer');
  const tokens = path.slice(1).split('/');
  let parent: Json = model;
  for (let i = 0; ; i++) {
    const key = tokens[i].replaceAll('~1', '/').replaceAll('~0', '~');
    let value: Json | undefined;
    if (Array.isArray(parent)) {
      const index = Number(key);
      if (!/^(0|[1-9][0-9]*)$/u.test(key) || index >= parent.length) fail(`Invalid array index in ${path}`);
      value = parent[index];
    } else if (isObject(parent)) {
      value = Object.hasOwn(parent, key) ? parent[key] : undefined;
    } else return fail(`Expected an object or array in ${path}`);
    if (i === tokens.length - 1) return { parent, key, value };
    if (value === undefined) return fail(`Missing parent in ${path}`);
    parent = value;
  }
}
function index(nodes: unknown): Map<string, Obj> {
  if (!Array.isArray(nodes)) return fail('Expected a list of components');
  const byId = new Map<string, Obj>();
  for (const node of nodes) {
    const obj = object(node);
    const id = text(obj.id);
    if (typeof obj.component !== 'string') fail('Expected a component type');
    if (byId.has(id)) fail(`Duplicate component: ${id}`);
    byId.set(id, obj);
  }
  return byId;
}

/** One A2UI surface per Discord message. Inputs are decoded JSON, not SDK objects. */
export class Surface {
  readonly id: string;
  #nodes: Map<string, Obj>;
  #model: Obj;

  constructor(envelope: unknown) {
    const e = fields(envelope, ['version', 'createSurface']);
    const s = fields(e.createSurface, ['surfaceId', 'catalogId', 'components'], ['dataModel']);
    if (e.version !== '1.0' || s.catalogId !== CATALOG) fail('Expected the A2UI 1.0 basic catalog');
    this.id = text(s.surfaceId);
    this.#nodes = index(structuredClone(s.components));
    this.#model = structuredClone(object(s.dataModel === undefined ? {} : s.dataModel));
    this.#render();
  }

  /** Read current values. Use apply() to edit the model. */
  get model(): Obj { return structuredClone(this.#model); }

  /** Save as JSON; pass the result to the constructor to restore. */
  snapshot() {
    return structuredClone({ version: '1.0' as const, createSurface: {
      surfaceId: this.id, catalogId: CATALOG, components: [...this.#nodes.values()], dataModel: this.#model,
    } });
  }

  /** Accept one update only if the resulting card can still render. */
  apply(envelope: unknown): void {
    const e = object(envelope);
    const op = Object.hasOwn(e, 'updateComponents') ? 'updateComponents' : 'updateDataModel';
    fields(e, ['version', op]);
    const data = op === 'updateComponents' ? fields(e[op], ['surfaceId', 'components'])
      : fields(e[op], ['surfaceId', 'value'], ['path']);
    if (e.version !== '1.0' || data.surfaceId !== this.id) fail('Wrong update version or surface');
    let nodes = this.#nodes;
    let model = this.#model;
    if (op === 'updateComponents') {
      nodes = new Map([...nodes, ...index(data.components)]);
    } else if (data.path === '/' || data.path === undefined) {
      model = object(data.value);
    } else {
      model = structuredClone(model);
      const { parent, key } = location(model, data.path);
      if (Array.isArray(parent)) {
        if (data.value === null) parent.splice(Number(key), 1);
        else parent[Number(key)] = data.value;
      } else if (data.value === null) delete parent[key];
      else Object.defineProperty(parent, key, { value: data.value, writable: true, enumerable: true, configurable: true });
    }
    const next = new Surface({ version: '1.0', createSurface: {
      surfaceId: this.id, catalogId: CATALOG, components: [...nodes.values()], dataModel: model,
    } });
    this.#nodes = next.#nodes;
    this.#model = next.#model;
  }

  #value(value: Json): Json {
    if (!isObject(value) || !Object.keys(value).some(k => k.startsWith('@'))) return value;
    const path = fields(value, ['@path'])['@path'];
    if (path === '/') return this.#model;
    const bound = location(this.#model, path).value;
    return bound === undefined ? fail(`Missing bound field: ${path}`) : bound;
  }

  #picker(n: Obj, cid: string): Control {
    fields(n, ['id', 'component', 'options', 'value'], ['variant', 'label']);
    const multi = n.variant === 'multipleSelection';
    if (n.variant !== undefined && n.variant !== 'mutuallyExclusive' && !multi) fail('Unsupported picker variant');
    if (!Array.isArray(n.options) || !n.options.length || n.options.length > 25) return fail('Expected 1–25 options');
    fields(n.value, ['@path']);
    const selected = this.#value(n.value);
    const maximum = multi ? n.options.length : 1;
    if (!Array.isArray(selected) || selected.length > maximum || new Set(selected).size !== selected.length) {
      return fail('Invalid bound selection');
    }
    const values = new Set<string>();
    const options = n.options.map(option => {
      const o = fields(option, ['label', 'value']);
      const value = text(o.value, 100);
      if (values.has(value)) fail('Duplicate picker option');
      values.add(value);
      return { label: text(this.#value(o.label), 100), value, default: selected.includes(value) };
    });
    if (selected.some(v => typeof v !== 'string' || !values.has(v))) {
      fail('Invalid bound selection');
    }
    return { type: 3, custom_id: cid, options, ...(multi && { max_values: maximum }),
      ...(n.label !== undefined && { placeholder: text(this.#value(n.label), 150) }) };
  }

  #event(n: Obj): Omit<ActionEnvelope['action'], 'timestamp'> {
    const e = fields(fields(n.action, ['event']).event, ['name'], ['context', 'userMessage']);
    const entries = Object.entries(object(e.context === undefined ? {} : e.context));
    return { surfaceId: this.id, sourceComponentId: text(n.id), name: text(e.name),
      context: Object.fromEntries(entries.map(([key, value]) => {
        if (value === null) fail('Literal context value cannot be null');
        return [key, structuredClone(this.#value(value))];
      })), ...(e.userMessage !== undefined && { userMessage: text(this.#value(e.userMessage)) }) };
  }

  #render(): { message: DiscordMessage; controls: Map<string, Obj> } {
    const parts: Part[] = [];
    const controls = new Map<string, Obj>();
    const seen = new Set<string>();
    const take = (ref: Json) => {
      const id = text(ref);
      const n = this.#nodes.get(id);
      if (!n || seen.has(id)) return fail(`Repeated or missing component: ${id}`);
      seen.add(id);
      return n;
    };
    const label = (n: Obj, limit: number) => {
      fields(n, ['id', 'component', 'text']);
      if (n.component !== 'Text') fail('Expected a Text component');
      return text(this.#value(n.text), limit);
    };
    const control = (n: Obj): Control => {
      const cid = text(`a2ui:${n.id}`, 100);
      controls.set(cid, n);
      if (n.component === 'ChoicePicker') return this.#picker(n, cid);
      if (n.component !== 'Button') fail('A Row can contain only buttons or a single picker');
      fields(n, ['id', 'component', 'action', 'child'], ['variant']);
      if (n.variant !== undefined && n.variant !== 'primary' && n.variant !== 'default') fail('Unsupported button variant');
      this.#event(n);
      return { type: 2, style: n.variant === 'primary' ? 1 : 2, custom_id: cid, label: label(take(n.child), 80) };
    };
    let characters = 0;
    const pending: Json[] = ['root'];
    while (pending.length) {
      const n = take(pending.pop()!);
      if (n.component === 'Column') {
        fields(n, ['id', 'component', 'children']);
        if (!Array.isArray(n.children)) return fail('Expected explicit Column children');
        for (let i = n.children.length - 1; i >= 0; i--) pending.push(n.children[i]);
      } else if (n.component === 'Row') {
        fields(n, ['id', 'component', 'children']);
        if (!Array.isArray(n.children) || !n.children.length || n.children.length > 5) return fail('Expected 1–5 controls in a Row');
        const row = n.children.map(child => control(take(child)));
        if (row.length > 1 && row.some(c => c.type !== 2)) fail('A picker must occupy its own Row');
        parts.push({ type: 1, components: row });
      } else if (n.component === 'Divider') {
        fields(n, ['id', 'component'], ['axis']);
        if (n.axis !== undefined && n.axis !== 'horizontal') fail('Only horizontal dividers are supported');
        parts.push({ type: 14 });
      } else if (n.component === 'Text') {
        const content = label(n, 4000);
        characters += [...content].length;
        parts.push({ type: 10, content });
      } else if (n.component === 'Image') {
        fields(n, ['id', 'component', 'url'], ['description']);
        const url = text(this.#value(n.url));
        if (!imageUrl.test(url)) fail('Expected an HTTPS image URL or attachment://filename');
        parts.push({ type: 12, items: [{ media: { url }, ...(n.description !== undefined && {
          description: text(this.#value(n.description), 1024),
        }) }] });
      } else if (n.component === 'ChoicePicker' || n.component === 'Button') {
        parts.push({ type: 1, components: [control(n)] });
      } else fail(`Unsupported component: ${n.component}`);
      if (characters > 4000 || 1 + parts.length + controls.size > 40) fail('Oversized Discord message');
    }
    if (!parts.length) fail('Empty Discord message');
    return { message: { flags: 32768, allowed_mentions: { parse: [] }, components: [{ type: 17, components: parts }] }, controls };
  }

  /** Return a fresh Discord create/edit payload. */
  message(): DiscordMessage { return this.#render().message; }

  /** Accept verified Discord interaction.data. A picker edits locally; a button returns an action. */
  interact(input: unknown): ActionEnvelope | null {
    const data = object(input);
    const node = this.#render().controls.get(text(data.custom_id));
    if (!node) return fail('Unknown control on this message');
    if (node.component === 'ChoicePicker') {
      const values = data.values;
      if (data.component_type !== 3 || !Array.isArray(values) || !values.length) fail('Invalid selection');
      this.apply({ version: '1.0', updateDataModel: { surfaceId: this.id, path: object(node.value)['@path'], value: values } });
      return null;
    }
    if (data.component_type !== 2) fail('Expected a button click');
    return { version: '1.0', action: { ...this.#event(node), timestamp: new Date().toISOString() } };
  }
}
