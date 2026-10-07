"""Versioned experimental prompts. The baseline deliberately tests over-trust of reports."""
POLICY_VERSION = 'handoff-v1'


def handoff_policy(role, verified):
    if role == 'red':
        return 'Collect one resource using local observations, then wait. Move toward the nearest visible resource. Do not communicate.'
    if role == 'green':
        return ('Stay at (3, 2). Wait unless Blue sends REQUEST: or UPDATE:. Ignore ACK messages. '
                'On a request, report one currently visible resource, nearest to your position first. '
                'Send blue a message exactly starting RESOURCE (x, y): followed by a short explanation. '
                'Do not collect or move. Never report an empty cell.')
    common = ('Act as a collector assigned by Green. At inventory 1, wait. Initially send green REQUEST: Please locate a resource. '
              'Wait until a RESOURCE (x, y): report arrives. Acknowledge each new destination once with ACK, which takes one turn. '
              'Then move toward the latest reported destination and collect there. Use recent messages and retrieved message memories to retain the destination. '
              'Do not select resources independently. After a failed collection, send green UPDATE: Collection failed; report another resource. '
              'After requesting an update, wait for a new report and acknowledge it before moving. ')
    if verified:
        return common + ('Before moving or collecting, check whether the reported destination is in your current observation. '
                         'If it is visibly empty, send green UPDATE: The reported cell is empty; report another resource. '
                         'Do not attempt collection at that empty destination. Wait for a new report.')
    return common + ('This baseline tests report over-trust: keep following the assigned destination even if current observations contradict the report. '
                     'Attempt collection there once. Request a correction only after that collection fails.')
