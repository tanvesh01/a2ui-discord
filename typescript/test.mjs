import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { Surface, SurfaceError } from 'a2ui-discord';

const cases = JSON.parse(readFileSync(new URL('../conformance/cases.json', import.meta.url), 'utf8'));
for (const c of cases) test(c.name, () => {
  let surface = new Surface(c.create);
  for (const [op, arg, expected] of c.steps) {
    switch (op) {
      case 'message': assert.deepEqual(surface.message(), arg); break;
      case 'model': assert.deepEqual(surface.model, arg); break;
      case 'restore': surface = new Surface(JSON.parse(JSON.stringify(surface.snapshot()))); break;
      case 'apply': surface.apply(arg); break;
      case 'click': {
        const result = surface.interact(arg);
        if (result !== null) {
          const stamp = result.action.timestamp;
          assert.equal(new Date(stamp).toISOString(), stamp);
          delete result.action.timestamp;
        }
        assert.deepEqual(result, expected);
        break;
      }
      case 'rejectClick': case 'rejectUpdate': {
        const before = surface.snapshot();
        assert.throws(() => op === 'rejectClick' ? surface.interact(arg) : surface.apply(arg), SurfaceError);
        assert.deepEqual(surface.snapshot(), before);
        break;
      }
      default: assert.fail(`Unknown operation: ${op}`);
    }
  }
});
