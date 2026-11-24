"""Offline audit-card round trip. Run: python3 -m examples.audit"""

import argparse
import json

from a2ui_discord import CATALOG, Surface

# Fictional audit. Detail stays in the host; it is never embedded in a custom_id.
FINDINGS = {
    'owner': ('Missing owner', 'Two access reviews have no assigned reviewer.'),
    'backup': ('Backup restore untested', 'The March backup has no recorded restore test.'),
    'rotation': ('Key rotation overdue', 'A sandbox key is 12 days past its rotation date.'),
}


def audit_card():
    return {'version': '1.0', 'createSurface': {
        'surfaceId': 'quarterly-audit', 'catalogId': CATALOG,
        'dataModel': {'selected': [], 'detail': 'Choose a finding to inspect the evidence.'},
        'components': [
            {'id': 'root', 'component': 'Column', 'children': ['summary', 'picker', 'detail', 'review']},
            {'id': 'summary', 'component': 'Text', 'text': '## Quarterly audit\n3 open findings'},
            {'id': 'picker', 'component': 'ChoicePicker', 'label': 'Choose finding',
             'value': {'@path': '/selected'}, 'options': [
                 {'label': title, 'value': key} for key, (title, _) in FINDINGS.items()]},
            {'id': 'detail', 'component': 'Text', 'text': {'@path': '/detail'}},
            {'id': 'review', 'component': 'Button', 'child': 'review-label', 'variant': 'primary',
             'action': {'event': {'name': 'reviewFinding', 'context': {'finding': {'@path': '/selected'}}}}},
            {'id': 'review-label', 'component': 'Text', 'text': 'Review finding'},
        ]}}


def handle(surface, interaction):
    """Local stand-in for a bot handler, already routed to the original message."""
    action = surface.interact(interaction['data'])
    selected = surface.model['selected']
    if action is None:
        title, evidence = FINDINGS[selected[0]]
        detail = f'**{title}**\n{evidence}'
    elif action['action']['context']['finding']:
        title, _ = FINDINGS[action['action']['context']['finding'][0]]
        detail = f'Example agent received the review request for **{title}**.'
    else:
        detail = 'Choose a finding before requesting a review.'
    surface.apply({'version': '1.0', 'updateDataModel': {
        'surfaceId': surface.id, 'path': '/detail', 'value': detail}})
    # Discord callback type 7 updates the originating message, not a follow-up.
    return {'type': 7, 'data': surface.message()}, action


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finding', choices=FINDINGS, default='backup')
    args = parser.parse_args()
    surface = Surface(audit_card())
    print(json.dumps({'create': surface.message()}, indent=2))
    for data in ({'custom_id': 'a2ui:picker', 'component_type': 3, 'values': [args.finding]},
                 {'custom_id': 'a2ui:review', 'component_type': 2}):
        callback, event = handle(surface, {'type': 3, 'data': data})
        print(json.dumps({'interactionResponse': callback, 'agentEvent': event}, indent=2))
