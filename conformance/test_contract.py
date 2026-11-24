"""Run against an installed package: python conformance/test_contract.py."""

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from a2ui_discord import Surface, SurfaceError


class ContractTest(unittest.TestCase):
    def test_wire_contract(self):
        for case in json.loads(Path(__file__).with_name('cases.json').read_text()):
            s = Surface(case['create'])
            for i, (op, *args) in enumerate(case['steps']):
                with self.subTest(case=case['name'], step=i, op=op):
                    if op == 'message':
                        self.assertEqual(s.message(), args[0])
                    elif op == 'model':
                        self.assertEqual(s.model, args[0])
                    elif op == 'restore':
                        s = Surface(json.loads(json.dumps(s.snapshot())))
                    elif op == 'apply':
                        s.apply(args[0])
                    elif op == 'click':
                        result = s.interact(args[0])
                        if result is not None:
                            stamp = datetime.fromisoformat(result['action'].pop('timestamp'))
                            self.assertEqual(stamp.utcoffset(), timedelta(0))
                        self.assertEqual(result, args[1])
                    elif op in ('rejectClick', 'rejectUpdate'):
                        before = s.snapshot()
                        with self.assertRaises(SurfaceError):
                            (s.interact if op == 'rejectClick' else s.apply)(args[0])
                        self.assertEqual(s.snapshot(), before)
                    else:
                        self.fail(f'Unknown operation: {op}')


if __name__ == '__main__':
    unittest.main()
