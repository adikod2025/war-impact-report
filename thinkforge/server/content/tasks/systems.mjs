import { c } from '../rubrics.mjs';

export default [
  {
    id: 'sys-t1-loop-type',
    strand: 'systems', moves: ['causal_loop', 'loop_type'], tier: 1, difficulty: -1.25,
    domain: 'everyday', register: [9, 11],
    title: 'Which way does the loop run?',
    stimulus: 'Amir practises guitar → he gets better → playing is more fun → he practises more → …\n\nA thermostat: the room gets cold → the heating switches on → the room warms up → the heating switches off → …',
    prompt: 'One of these loops runs away and one settles down. Which statement is right?',
    mode: 'select',
    payload: {
      options: [
        { id: 'a', text: 'Both loops settle down at a steady level.', correct: false, why: 'The guitar loop has nothing pulling it back — each trip round makes the next trip stronger.' },
        { id: 'b', text: 'The guitar loop runs away (reinforcing); the thermostat loop settles (balancing).', correct: true, why: 'Right. A reinforcing loop feeds itself; a balancing loop contains something that switches the cause off once the goal is reached.' },
        { id: 'c', text: 'The thermostat loop runs away; the guitar loop settles.', correct: false, why: 'Backwards — the thermostat has an off switch built into it, which is what makes it settle.' },
        { id: 'd', text: 'Neither is a loop, they are just chains of events.', correct: false, why: 'Both come back to where they started, which is what makes them loops rather than chains.' },
      ],
    },
    checks: {},
    hints: [
      'Follow each one round twice. Is the second lap bigger than the first, or the same?',
      'Look for something that *switches the cause off* once things are good enough. Which loop has one?',
      'Worked: *savings → interest → more savings* has nothing to stop it, so it grows. *Hungry → eat → not hungry → stop eating* switches itself off. The guitar and the thermostat are one of each.',
    ],
    bridge: 'Find one loop at home that runs away and one that settles.',
  },
  {
    id: 'sys-t1-secondorder-corridor',
    strand: 'systems', moves: ['second_order'], tier: 1, difficulty: -0.85,
    domain: 'everyday', register: [9, 12],
    title: 'And then what?',
    stimulus: 'To stop collisions, a school bans running in corridors. Anyone caught running loses their break.',
    prompt: 'Ask "**and then what happens?**" three times in a row. Each answer must come out of the one before it. Your third one must include something that works against the point of the rule.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'then1', label: 'And then what? (1)', required: true, minWords: 6 },
        { id: 'then2', label: 'And then what? (2)', required: true, minWords: 6 },
        { id: 'then3', label: 'And then what? (3) — include a backfire', required: true, minWords: 8 },
      ],
      commonIdeas: ['people walk', 'fewer accidents', 'people get told off'],
      conceptVocabulary: ['late', 'lesson', 'break', 'teacher', 'crowded', 'push', 'stairs', 'rush', 'hide'],
    },
    rubric: {
      criteria: [c('second_order_chain', 0.5), c('specificity', 0.25), c('originality', 0.25)],
      solo: {
        3: 'Three linked steps where each is caused by the one above.',
        4: 'The third step shows the rule undermining its own goal, and says why.',
      },
    },
    checks: { requiredFields: ['then1', 'then2', 'then3'], capIfMissing: { then3: 0.6 } },
    hints: [
      'Your first answer is probably "people walk". Now — what happens to people who are *late* because they walked?',
      'Think about where people would run instead, if corridors are watched.',
      'Worked chain: *toll on the main road → drivers use side streets → side streets get dangerous → the school on the side street asks for a barrier.* Three steps, each caused by the last, ending somewhere nobody intended. Now redo yours.',
    ],
    bridge: 'Take one rule you like and ask "and then what?" three times.',
  },
  {
    id: 'sys-t2-loop-build',
    strand: 'systems', moves: ['causal_loop', 'loop_type', 'delay'], tier: 2, difficulty: 0.3,
    domain: 'social', register: [11, 14],
    title: 'Draw the loop',
    stimulus: 'A group chat gets busier every week. People post more because they get replies; replies come because people post; but at some point everyone mutes it and posting drops.',
    prompt: 'Write the loop out as arrows with **signs**: A →(+/−) B →(+/−) C … back to A. Then name the loop type, and find the **delay** that makes people mistime their reaction.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'loop', label: 'The loop, as signed arrows', required: true, minWords: 8 },
        { id: 'type', label: 'Reinforcing or balancing? Why?', required: true, minWords: 10 },
        { id: 'second', label: 'The second loop that eventually kicks in', required: true, minWords: 12 },
        { id: 'delay', label: 'Where is the delay, and what does it make people get wrong?', required: true, minWords: 12 },
      ],
      conceptVocabulary: ['posts', 'replies', 'notifications', 'mute', 'annoyance', 'delay', 'reinforcing', 'balancing', 'threshold'],
    },
    rubric: {
      criteria: [c('loop_signs', 0.3), c('loop_type', 0.25), c('delay_identified', 0.25), c('integration', 0.2)],
      solo: {
        3: 'A closed signed loop, correctly typed, plus the balancing loop that eventually appears.',
        4: 'Explains that the system flips behaviour when the second loop overtakes the first, and locates the delay as the reason people notice too late.',
      },
    },
    checks: { requiredFields: ['loop', 'type', 'second', 'delay'], capIfMissing: { delay: 0.7, second: 0.75 } },
    hints: [
      'Write only two things first — posts and replies — and put an arrow each way. What sign goes on each?',
      'The muting is a second loop working the other way. What is the thing that builds up before someone mutes?',
      'Worked pair: *sales →(+) reviews →(+) sales* is reinforcing. Add *sales →(+) delivery time →(−) sales* and the second loop caps the first. The delay is that delivery times only get bad weeks later. Now do the group chat.',
    ],
    misconceptions: [
      { signal: 'lists factors without arrows', tutorMove: 'Ask which thing changes which, and in which direction.' },
    ],
    bridge: 'Draw the loop behind one habit of yours that grew and then collapsed.',
  },
  {
    id: 'sys-t2-delay-shower',
    strand: 'systems', moves: ['delay'], tier: 2, difficulty: 0.0,
    domain: 'science', register: [11, 14],
    title: 'Why you always overshoot',
    stimulus: 'An old shower takes about eight seconds to respond to the tap. People turn it up, feel nothing, turn it up more — then jump back scalded, and turn it right down.',
    prompt: 'What is the general lesson here about systems with delays?',
    mode: 'select',
    payload: {
      options: [
        { id: 'a', text: 'The shower is broken and should be replaced.', correct: false, why: 'The behaviour is normal for any delayed system — replacing it just shortens the delay.' },
        { id: 'b', text: 'When feedback arrives late, people over-correct, and the swings get bigger.', correct: true, why: 'Exactly. Delay plus impatience produces oscillation — the same pattern shows up in traffic, stock, and school policies.' },
        { id: 'c', text: 'People should just be more patient in general.', correct: false, why: 'True but shallow — it does not explain *why* the mistake happens or when to expect it.' },
        { id: 'd', text: 'The delay means the shower has no feedback at all.', correct: false, why: 'There is feedback — it just arrives after you have already acted again.' },
      ],
    },
    checks: {},
    hints: [
      'Ask what the person is reacting to when they turn the tap up the second time.',
      'The information they need has not arrived yet. What does anyone do when they act on missing information?',
      'The same shape appears when a shop reorders stock that takes three weeks to arrive: too little, then panic-order, then far too much. Which option describes that pattern?',
    ],
    bridge: 'Spot one place this week where somebody over-corrected because the news arrived late.',
  },
  {
    id: 'sys-t3-leverage-litter',
    strand: 'systems', moves: ['leverage'], tier: 3, difficulty: 1.0,
    domain: 'social', register: [13, 16],
    title: 'Where to push',
    stimulus: 'A park is covered in litter every weekend. Proposals on the table: (a) add six more bins, (b) double the fine, (c) pay a Sunday cleaner, (d) change the café\'s packaging to reusable deposit cups, (e) run a campaign about what litter does to the river, (f) give the local scouts responsibility for the park and a small budget.',
    prompt: 'Place each proposal on the leverage ladder — **numbers → buffers → feedback loops → rules → goals → the idea behind it all** — and argue which one has the most leverage and why. Higher on the ladder is not automatically better; say what makes yours the right level *here*.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'placement', label: 'Each proposal, placed on the ladder', required: true, minWords: 30, multiline: true },
        { id: 'best', label: 'Highest-leverage proposal, and why at this level', required: true, minWords: 25 },
        { id: 'cheap', label: 'Which low-leverage proposal is still worth doing, and why', required: true, minWords: 15 },
      ],
      conceptVocabulary: ['numbers', 'buffer', 'loop', 'rule', 'goal', 'paradigm', 'deposit', 'ownership', 'fine', 'enforcement'],
    },
    rubric: {
      criteria: [c('leverage_placement', 0.4), c('integration', 0.25), c('rival_explanations', 0.2), c('specificity', 0.15)],
      solo: {
        3: 'All six placed sensibly, with a justified choice of the highest-leverage one.',
        4: 'Argues that leverage depends on what the system is currently limited by, and shows why a high-ladder change could fail here while a mid-ladder one works.',
      },
    },
    checks: { requiredFields: ['placement', 'best', 'cheap'], capIfMissing: { cheap: 0.8 } },
    hints: [
      'Two of these only change a number. Which two, and what does that tell you about their ceiling?',
      'The deposit cup changes who is motivated to pick a cup up — that is a feedback loop, not a number. Where does handing the park to the scouts sit?',
      'Worked placement in another system: *more hospital beds = a buffer; changing how a ward is paid = a rule; deciding the goal is "days of health" instead of "patients treated" = a goal change.* Note how each level changes what the level below is even trying to do. Now place yours.',
    ],
    misconceptions: [
      { signal: 'assumes highest rung is always best', tutorMove: 'Ask what happens if you change the goal but nobody has a bin.' },
    ],
    bridge: 'Take a problem you keep "solving" with numbers and find the rung above it.',
  },
  {
    id: 'sys-t4-induced-demand',
    strand: 'systems', moves: ['causal_loop', 'second_order', 'delay', 'leverage'], tier: 4, difficulty: 2.0,
    domain: 'data', register: [14, 16],
    title: 'The road that filled up again',
    stimulus: 'A congested two-lane road is widened to four lanes. Journey times fall by 40% for eight months. Within three years, journey times are back where they started, with twice as many vehicles. The council is asked to widen it again.',
    prompt: 'Explain the system. Give the loop, the delay, why the eight-month improvement was real but temporary, and what a higher-leverage intervention would be. Then state what evidence would show your explanation was wrong.',
    mode: 'open_short',
    payload: {
      maxWords: 250,
      answerKey: 'Widening lowers the cost (time) of driving that route → more people choose to drive it, and some choose to live or shop further away because the trip is now cheap → traffic rises until journey time returns to the level at which people stop choosing it. That is a balancing loop with the equilibrium set by drivers\' tolerance for delay, not by road capacity — so capacity cannot be the lever. The delay is in the slow decisions (where to live, work, shop, school) which take months to years, which is why the improvement is real for eight months and gone by year three. Higher-leverage interventions act on the goal or the rules rather than the number of lanes: pricing the road, improving the alternative so the tolerance point is reached sooner on the alternative, or changing land use so fewer trips are needed at all. Disconfirming evidence: if traffic volumes did not rise, or if the same widening elsewhere produced permanent improvement where alternatives and land use were fixed.',
      conceptVocabulary: ['induced', 'demand', 'equilibrium', 'tolerance', 'balancing', 'capacity', 'pricing', 'land use', 'delay', 'alternative'],
    },
    rubric: {
      criteria: [c('loop_type', 0.25), c('delay_identified', 0.2), c('leverage_placement', 0.25), c('beyond_case', 0.15), c('test_design', 0.15)],
      solo: {
        3: 'Identifies the balancing loop and explains why capacity gains erode, with the delay located in slow decisions.',
        4: 'States the general principle — the equilibrium is set by what people will tolerate, not by capacity — and applies it to a non-traffic case.',
      },
    },
    checks: { minWords: { response: 80 } },
    hints: [
      'The journey time came back to *exactly* where it was. What quantity is the system actually holding steady, and what does that tell you about who is controlling it?',
      'Eight months versus three years — what kinds of decision take months, and what kinds take years? The gap between them is your delay.',
      'Worked parallel: *a bigger fridge does not reduce food waste, because people fill the space they have. The equilibrium is set by habits, so more capacity is absorbed.* Now say what sets the equilibrium on the road, and which lever touches it.',
    ],
    misconceptions: [
      { signal: 'concludes the widening simply failed', tutorMove: 'Ask why the improvement was genuine for eight months if it "failed".' },
      { signal: 'recommends widening further', tutorMove: 'Ask what their own loop predicts will happen after that.' },
    ],
    bridge: 'Find another case where adding capacity got absorbed instead of solving the problem.',
  },
];
