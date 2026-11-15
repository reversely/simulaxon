"""Templates: projects with blanks. Data only; opening one fills the same frame as any project.

Each template names its sampling plan, its declared parameters with roles, its analyses, the controls that can challenge
it, what it hands off, and a short walkthrough that names the flow at each step (research/13_flows_and_templates.md).
"""

FLOWS = {
    'build': 'Build a world',
    'vary': 'Choose what varies',
    'run': 'Run',
    'compare': 'Compare',
    'challenge': 'Challenge',
    'handoff': 'Hand off',
}

TEMPLATES = [
    {
        'id': 'check_contrast',
        'title': 'Check a contrast',
        'question': 'Does {a} raise {region} more than {b}?',
        'blurb': 'Matched pairs of objects, one category against its look-alikes.',
        'plan': 'matched', 'unit_noun': 'pair', 'stimulus': 'still', 'world': 'counter',
        'parameters': [
            {'name': 'item', 'type': 'asset', 'role': 'manipulated', 'value': '{a} or {b}'},
            {'name': 'match_on', 'type': 'choice', 'role': 'matched', 'value': '{match_on}'},
            {'name': 'framing', 'type': 'choice', 'role': 'fixed', 'value': 'equal size on screen'},
            {'name': 'on_screen_s', 'type': 'number', 'unit': 's', 'role': 'fixed', 'value': 3},
            {'name': 'seed', 'type': 'number', 'role': 'fixed', 'value': 0},
        ],
        'analyses': ['paired', 'items_needed', 'time_course'],
        'controls': ['Colour matched', 'Shape matched', 'Greyscale', 'Look-alikes', 'Faces as a positive control', 'Other brain models', 'More seeds'],
        'handoff': ['Stimulus list', 'Pairs needed', 'Regions to preregister'],
        'walkthrough': [
            ('build', 'Each item sits alone on the same counter, framed to the same size on screen.'),
            ('vary', 'One parameter changes per pair: the item. Everything else is fixed or matched.'),
            ('run', 'Every image is shown for 3 s, then 7 s of grey, one TRIBE run per clip.'),
            ('compare', 'Each pair gives one difference. The result is the mean difference with a 95% interval.'),
            ('challenge', 'Rerun with a different match, a positive control, or more seeds, and see how much survives.'),
            ('handoff', 'Pairs needed estimates how many pairs a study needs at this effect size.'),
        ],
    },
    {
        'id': 'one_object_out',
        'title': 'One object out',
        'question': 'Which objects in {scene} drive {region}?',
        'blurb': 'Hide each object in a room in turn and map what changes.',
        'plan': 'leave_one_out', 'unit_noun': 'object', 'stimulus': 'still', 'world': 'stage',
        'parameters': [
            {'name': 'hidden_object', 'type': 'asset', 'role': 'manipulated', 'value': 'none, then each object'},
            {'name': 'camera', 'type': 'choice', 'role': 'fixed', 'value': '{camera}'},
            {'name': 'objects_tested', 'type': 'number', 'role': 'fixed', 'value': '{n_objects}'},
            {'name': 'on_screen_s', 'type': 'number', 'unit': 's', 'role': 'fixed', 'value': 3},
        ],
        'analyses': ['per_object'],
        'controls': ['Other cameras', 'Swap in place of hide', 'Object size on screen', 'Other brain models'],
        'handoff': ['Objects that matter', 'Room with one change per condition'],
        'walkthrough': [
            ('build', 'A whole room from SAGE-10k, rendered from one camera.'),
            ('vary', 'The plan hides one object at a time. The full room is the reference.'),
            ('run', 'The full room and every variant go through TRIBE as separate clips.'),
            ('compare', 'Each object\'s effect is the full room minus the room without it, per region.'),
            ('challenge', 'Large objects change many pixels. Check effects against size on screen before reading them.'),
            ('handoff', 'The objects with the largest effects become the conditions of a smaller study.'),
        ],
    },
    {
        'id': 'possible_impossible',
        'title': 'Possible or impossible',
        'question': 'Does {region} respond when {event}?',
        'blurb': 'The same motion with and without a physical violation.',
        'plan': 'matched', 'unit_noun': 'item', 'stimulus': 'motion', 'world': 'fall',
        'parameters': [
            {'name': 'item', 'type': 'asset', 'role': 'randomized', 'value': '{n_items} items'},
            {'name': 'outcome', 'type': 'choice', 'role': 'manipulated', 'value': '{a} or {b}'},
            {'name': 'drop_m', 'type': 'number', 'unit': 'm', 'role': 'fixed', 'value': '{drop_m}'},
            {'name': 'hover_gap_m', 'type': 'number', 'unit': 'm', 'role': 'fixed', 'value': '{gap_m}'},
            {'name': 'restitution', 'type': 'number', 'role': 'fixed', 'value': '{restitution}'},
        ],
        'analyses': ['paired', 'time_course', 'items_needed'],
        'controls': ['Same final position, no motion', 'Matched motion', 'Other violations', 'Other brain models', 'More items'],
        'handoff': ['Clip pairs', 'Items needed', 'Regions to preregister'],
        'walkthrough': [
            ('build', 'One counter, one item, one camera. The item falls from the same height every time.'),
            ('vary', 'Only the outcome changes. Every frame before contact is identical in both clips.'),
            ('run', '3 s of motion, then 7 s of grey, one TRIBE run per clip.'),
            ('compare', 'Each item gives one difference, impossible minus possible.'),
            ('challenge', 'The hovering item ends 8 cm higher, so a position-only control comes next.'),
            ('handoff', 'Clip pairs and the items needed for a study.'),
        ],
    },
    {
        'id': 'select_stimuli',
        'title': 'Drive two regions together or apart',
        'question': 'Which stimuli drive {a_label} and {b_label} together, and which drive them apart?',
        'blurb': 'Screen every stimulus in the model, then keep the ones that align or separate two regions.',
        'plan': 'selection', 'unit_noun': 'stimulus', 'stimulus': 'still', 'world': 'counter',
        'parameters': [
            {'name': 'stimulus', 'type': 'asset', 'role': 'manipulated', 'value': '{n_items} screened stimuli'},
            {'name': 'first_region', 'type': 'choice', 'role': 'measured', 'value': '{a_region}'},
            {'name': 'second_region', 'type': 'choice', 'role': 'measured', 'value': '{b_region}'},
            {'name': 'kept', 'type': 'number', 'role': 'fixed', 'value': '{k} per condition'},
        ],
        'analyses': ['selection'],
        'controls': ['Random baseline', 'Held-out camera', 'Other brain models'],
        'handoff': ['Selected stimuli', 'Validation run'],
        'walkthrough': [
            ('build', 'Every stimulus already rendered on the counter is screened.'),
            ('vary', 'Nothing new is rendered to screen: each stimulus has a predicted response in both regions.'),
            ('run', 'The selection keeps the stimuli that drive both regions up or down, or one up and the other down.'),
            ('compare', 'Each condition is compared with random sets of the same size, chosen without optimisation.'),
            ('challenge', 'The selected stimuli are rendered again from a camera angle the screen never saw.'),
            ('handoff', 'The selected stimuli and the validation run, ready for a scanner.'),
        ],
    },
    {
        'id': 'region_prefers',
        'title': 'What a region prefers',
        'question': 'Which scene raises {region} the most?',
        'blurb': 'Search over objects, camera and light to drive one region up.',
        'plan': 'adaptive', 'unit_noun': 'scene', 'stimulus': 'still', 'world': 'counter',
        'parameters': [
            {'name': 'item', 'type': 'asset', 'role': 'randomized', 'value': 'any library asset'},
            {'name': 'distance_m', 'type': 'number', 'unit': 'm', 'role': 'randomized', 'value': '0.3 to 3'},
            {'name': 'light_deg', 'type': 'angle', 'unit': '°', 'role': 'randomized', 'value': '-15 to 60'},
            {'name': 'objective', 'type': 'choice', 'role': 'measured', 'value': '{region}'},
        ],
        'analyses': ['paired'],
        'controls': ['Random baseline', 'Held-out seeds', 'Other brain models'],
        'handoff': ['Scenes to rebuild'],
        'walkthrough': [
            ('build', 'Start from a room or a counter.'),
            ('vary', 'Mark the parameters to search, and the region to raise.'),
            ('run', 'Each round renders a batch, reads the region, and picks the next batch.'),
            ('compare', 'The best scenes against a random baseline with the same budget.'),
            ('challenge', 'Rerun the winners with new seeds and other brain models.'),
            ('handoff', 'Scenes that can be rebuilt for a scanner.'),
        ],
    },
    {
        'id': 'look_and_motion',
        'title': 'Look against motion',
        'question': "Does {region} respond when a body's look and its motion disagree?",
        'blurb': 'Real moments of social interaction, each acted out by a human body and a robot, with human and with robotic motion.',
        'plan': 'factorial', 'unit_noun': 'moment', 'stimulus': 'video', 'world': 'body', 'unit_parameter': 'moment', 'window_s': [1, 9],
        'defaults': {'n_moments': 6, 'keyframe_s': 0.5},   # blanks the form does not ask for: a new project starts with these
        'cells': [
            {'id': 'human_recorded', 'label': 'Human, recorded motion', 'values': {'body': 'human', 'motion': 'recorded'}},
            {'id': 'human_robotic', 'label': 'Human, robotic motion', 'values': {'body': 'human', 'motion': 'robotic'}},
            {'id': 'g1_recorded', 'label': 'G1, recorded motion', 'values': {'body': 'g1', 'motion': 'recorded'}},
            {'id': 'g1_robotic', 'label': 'G1, robotic motion', 'values': {'body': 'g1', 'motion': 'robotic'}},
        ],
        'contrasts': [
            {'title': 'Look and motion disagree, against agree', 'weights': {'human_robotic': 1, 'g1_recorded': 1, 'human_recorded': -1, 'g1_robotic': -1}},
            {'title': 'Human look with robotic motion, against the human and the robot', 'weights': {'human_robotic': 1, 'human_recorded': -0.5, 'g1_robotic': -0.5}},
            {'title': 'Human body against the G1', 'weights': {'human_recorded': 0.5, 'human_robotic': 0.5, 'g1_recorded': -0.5, 'g1_robotic': -0.5}},
            {'title': 'Robotic motion against recorded', 'weights': {'human_robotic': 0.5, 'g1_robotic': 0.5, 'human_recorded': -0.5, 'g1_recorded': -0.5}},
        ],
        'parameters': [
            {'name': 'moment', 'type': 'asset', 'role': 'randomized', 'value': '{n_moments} EgoBody moments'},
            {'name': 'body', 'type': 'choice', 'role': 'manipulated', 'value': 'Human body or Unitree G1'},
            {'name': 'motion', 'type': 'choice', 'role': 'manipulated', 'value': 'recorded or robotic'},
            {'name': 'Keyframes', 'type': 'number', 'unit': 's', 'role': 'fixed', 'value': '{keyframe_s}'},
            {'name': 'camera', 'type': 'choice', 'role': 'fixed', 'value': "the partner's eye"},
        ],
        'analyses': ['paired', 'items_needed', 'time_course'],
        'controls': ['Motion energy matched', 'Brightness matched between bodies', 'Lifelike look with Cosmos', 'More moments', 'Other brain models'],
        'handoff': ['Clip list', 'Moments needed', 'Regions to preregister'],
        'walkthrough': [
            ('build', "Each moment is a real recorded interaction, rebuilt in the scan of its room and filmed from where the partner stood."),
            ('vary', 'Two things change: the body and the motion. The body is a human or the G1. The motion is as recorded, or robotic: the same poses joined at constant speed.'),
            ('run', 'Every moment is played four ways, 9 s each, and TRIBE reads each clip.'),
            ('compare', 'The first result is look against motion, with its interval over moments.'),
            ('challenge', 'Match motion energy and brightness, make the human lifelike, and see how much survives.'),
            ('handoff', 'Moments needed estimates how many moments a study needs at this effect size.'),
        ],
    },
]


def get(template_id: str) -> dict:
    for t in TEMPLATES:
        if t['id'] == template_id: return t
    from ..store import Missing
    raise Missing(f"no template {template_id}")


def fill(text, bindings: dict):
    if isinstance(text, str):
        try: return text.format(**bindings)
        except (KeyError, IndexError): return text
    return text
