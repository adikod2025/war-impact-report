import { c } from '../rubrics.mjs';

export default [
  {
    id: 'lat-t1-pmi-nohomework',
    strand: 'lateral', moves: ['pmi'], tier: 1, difficulty: -1.4,
    domain: 'everyday', register: [9, 11],
    title: 'PMI: homework is abolished',
    stimulus: 'Suppose your school announced tomorrow: no homework, ever again. Not less homework — none.',
    prompt: 'Run a **PMI** before you decide whether you like it. Plus points, Minus points, and Interesting points — the Interesting ones are the things that are neither good nor bad, but that you notice and want to know more about.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'plus', label: 'P — good things about it (at least 3)', required: true, minWords: 8, multiline: true },
        { id: 'minus', label: 'M — bad things about it (at least 3)', required: true, minWords: 8, multiline: true },
        { id: 'interesting', label: 'I — interesting: neither good nor bad, but worth noticing (at least 2)', required: true, minWords: 8, multiline: true },
      ],
      commonIdeas: ['more free time', 'less stress', 'lower grades', 'more sleep', 'more video games'],
      conceptVocabulary: ['time', 'practice', 'parents', 'teachers', 'grades', 'sleep', 'tests', 'clubs', 'learning', 'fair'],
    },
    rubric: {
      criteria: [c('completeness', 0.3, { name: 'All three columns really filled' }), c('distinctness', 0.3, { heuristic: { type: 'distinct', target: 5 } }), c('originality', 0.4, { name: 'The Interesting column is genuinely interesting' })],
      solo: {
        3: 'Three columns, non-overlapping, with an Interesting entry that is truly neither plus nor minus.',
        4: 'Notices that whether something is a plus or a minus depends on *who you are* in the situation, and says so.',
      },
    },
    checks: { requiredFields: ['plus', 'minus', 'interesting'], capIfMissing: { interesting: 0.5 }, minWords: { interesting: 8 } },
    hints: [
      'Read your Minus list. Is any item on it actually just a Plus for someone else in the school?',
      'The Interesting column is the hard one. Try starting with "I wonder what would happen to…" — clubs? teachers\' evenings? the way tests work?',
      'Worked Interesting entries for "school starts at 11am": *I wonder whether parents\' work hours would change too. I wonder whether the last lesson of the day would suddenly become the best one.* Neither is good or bad — both are things that would shift. Now write two like that.',
    ],
    misconceptions: [
      { signal: 'Interesting column is just more pluses', tutorMove: 'Ask whether that item would be good or bad — if they can answer, it belongs in P or M.' },
      { signal: 'fewer than three per column', tutorMove: 'Ask them to name who else is affected and repeat the column from that person\'s side.' },
    ],
    bridge: 'Run a PMI on the next thing you are about to say no to straight away.',
  },
  {
    id: 'lat-t1-caf-classpet',
    strand: 'lateral', moves: ['caf'], tier: 1, difficulty: -1.0,
    domain: 'social', register: [9, 11],
    title: 'Consider all factors: the class pet',
    stimulus: 'Your class is allowed to get a class pet. Everyone is arguing about which animal. Nobody has asked what actually needs to be considered.',
    prompt: 'List all the factors that would have to be taken into account — **at least seven**. Then star the one you think most classes would forget.',
    mode: 'open_list',
    payload: {
      minIdeas: 7,
      commonIdeas: ['cost', 'food', 'cleaning', 'noise', 'space', 'who takes it home'],
      conceptVocabulary: ['allergy', 'holidays', 'weekend', 'vet', 'smell', 'cage', 'lifespan', 'noise', 'fear', 'insurance', 'rules', 'cost'],
    },
    rubric: {
      criteria: [c('fluency', 0.25, { heuristic: { type: 'count', target: 7 } }), c('distinctness', 0.3, { heuristic: { type: 'distinct', target: 6 } }), c('originality', 0.45, { name: 'Factors most people forget' })],
      solo: {
        3: 'Seven or more distinct factors, spanning more than one kind of concern (money, care, people, time).',
        4: 'Sorts the factors into kinds, or spots a factor that only appears when two others combine (e.g. long holidays + a short-lived animal).',
      },
    },
    checks: { minWords: { response: 15 } },
    hints: [
      'You have covered the animal. Now go through the *people*: everyone in the room, everyone who cleans the room, everyone who visits it.',
      'Two whole categories are usually missed: what happens in the six-week summer holiday, and what happens if someone in the class is allergic or frightened.',
      'Worked example for "a class 3D printer": *cost, filament, noise, fumes and ventilation, who fixes it, whether one person hogs it, what happens to it when the teacher leaves.* Notice the last three are about people, not the machine. Add three people-factors to your list.',
    ],
    misconceptions: [{ signal: 'all factors are about the animal itself', tutorMove: 'Ask who else is in the room all day.' }],
    bridge: 'Run CAF on the next family decision you are part of — and see which factor was missing.',
  },
  {
    id: 'lat-t2-cns-freebuses',
    strand: 'lateral', moves: ['cns'], tier: 2, difficulty: -0.1,
    domain: 'social', register: [11, 14],
    title: 'Consequence and sequel: free buses',
    stimulus: 'A city makes all buses free for everyone, starting next month. It is paid for out of the city budget.',
    prompt: 'Trace the consequences across **four time bands**: immediately, in a few weeks, in a year, in ten years. At least one band must contain something that works *against* the original goal.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'now', label: 'Immediately (days)', required: true, minWords: 6 },
        { id: 'short', label: 'Short term (weeks)', required: true, minWords: 6 },
        { id: 'medium', label: 'Medium term (a year)', required: true, minWords: 8 },
        { id: 'long', label: 'Long term (ten years)', required: true, minWords: 8 },
        { id: 'backfire', label: 'Which of these works against the point of the policy?', required: true, minWords: 8 },
      ],
      commonIdeas: ['more people use buses', 'less traffic', 'costs the city money'],
      conceptVocabulary: ['crowded', 'traffic', 'cycling', 'walking', 'drivers', 'tax', 'routes', 'maintenance', 'housing', 'cars', 'demand'],
    },
    rubric: {
      criteria: [c('second_order_chain', 0.35), c('specificity', 0.2), c('originality', 0.25), c('rival_explanations', 0.2, { name: 'Finds the backfire' })],
      solo: {
        3: 'Four bands with effects that follow on from each other rather than four restatements of "more people ride buses".',
        4: 'Sees a long-term effect that changes the *system*, not just the numbers — e.g. where people choose to live, or what the city stops funding.',
      },
    },
    checks: { requiredFields: ['now', 'short', 'medium', 'long', 'backfire'], capIfMissing: { backfire: 0.6, long: 0.7 } },
    hints: [
      'Your "immediately" answer is probably "more people get on the bus". Ask: and then what happens *to the bus*?',
      'Think about who *stops* doing something. If buses are free, what do some people stop doing — and was that thing good?',
      'Worked chain for free school breakfasts: *day one, more children eat → weeks, the hall is full at 8am so the club that used it moves → a year, families rely on it so the school cannot cancel it → ten years, it is a fixed cost that squeezes the trips budget.* Each step comes out of the one before. Now redo yours that way.',
    ],
    misconceptions: [
      { signal: 'four bands all say the same thing at different scales', tutorMove: 'Ask what new thing happens in band two that was not happening in band one.' },
      { signal: 'no backfire found', tutorMove: 'Ask what a cyclist does when the bus becomes free.' },
    ],
    bridge: 'Take a rule your school introduced this year and run four time bands on it.',
  },
  {
    id: 'lat-t2-apc-lunchqueue',
    strand: 'lateral', moves: ['apc'], tier: 2, difficulty: 0.2,
    domain: 'everyday', register: [11, 14],
    title: 'Three real alternatives',
    stimulus: 'The lunch queue takes 25 minutes. By the time Year 8 is served, they have twelve minutes to eat. The school\'s plan is "make the servers faster".',
    prompt: 'Produce **three genuinely different** solutions — not three versions of "make it faster". They must attack the problem from different directions. Include one you personally dislike.',
    mode: 'open_list',
    payload: {
      minIdeas: 3,
      commonIdeas: ['more serving staff', 'more tills', 'longer lunch break', 'pre-order online'],
      categories: [
        { id: 'supply', name: 'Serve faster / more capacity', keywords: ['staff', 'till', 'counter', 'server', 'faster', 'queue'] },
        { id: 'demand', name: 'Change who arrives when', keywords: ['stagger', 'shift', 'year', 'time', 'slot', 'rota', 'split'] },
        { id: 'bypass', name: 'Remove the queue entirely', keywords: ['pre-order', 'delivery', 'packed', 'classroom', 'vending', 'collect', 'bring'] },
        { id: 'reframe', name: 'Change what "lunch" means here', keywords: ['eat outside', 'longer day', 'lesson', 'brunch', 'two sittings', 'timetable'] },
      ],
      conceptVocabulary: ['queue', 'stagger', 'pre-order', 'timetable', 'hall', 'collect', 'sitting', 'space'],
    },
    rubric: {
      criteria: [c('flexibility_categories', 0.45, { heuristic: { type: 'distinct', target: 3 } }), c('specificity', 0.25), c('originality', 0.3)],
      solo: {
        3: 'Three options from three different directions, each described concretely enough to try.',
        4: 'Names the *dimension* each option moves along (capacity / timing / removing the queue) and picks using that.',
      },
    },
    checks: { minWords: { response: 25 } },
    hints: [
      'Look at your three. If all three make the serving faster, you have one idea in three coats.',
      'There are at least three directions here: serve faster, change *when people arrive*, or get rid of the queue altogether. Which have you not used?',
      'Worked alternatives for a busy school gate: *(1) two gates open instead of one — capacity; (2) Years 7-8 leave five minutes earlier — timing; (3) buses park on the far side so those students never reach the gate — removing the flow.* Three directions, not three speeds. Now do yours.',
    ],
    misconceptions: [{ signal: 'three variants of one idea', tutorMove: 'Ask what all three have in common — that shared thing is the assumption to break.' }],
    bridge: 'Next time you get stuck, force a third option before choosing between the first two.',
  },
  {
    id: 'lat-t3-opv-phones',
    strand: 'lateral', moves: ['opv'], tier: 3, difficulty: 0.8,
    domain: 'social', register: [13, 16],
    title: 'Other people\'s views: the phone lockers',
    stimulus: 'A school will require every phone to be locked in a pouch from 8:40 to 15:20. Parents, students, teachers, the office staff, and the school\'s safeguarding lead all have a stake.',
    prompt: 'For **four different stakeholders**, state their view *in their own terms* — fairly enough that they would agree with your version. Then name the one place where two of their interests genuinely cannot both be satisfied.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 's1', label: 'Stakeholder 1 — who, and their actual interest', required: true, minWords: 12 },
        { id: 's2', label: 'Stakeholder 2', required: true, minWords: 12 },
        { id: 's3', label: 'Stakeholder 3', required: true, minWords: 12 },
        { id: 's4', label: 'Stakeholder 4', required: true, minWords: 12 },
        { id: 'clash', label: 'Where two of these genuinely cannot both be satisfied', required: true, minWords: 15 },
      ],
      conceptVocabulary: ['parent', 'contact', 'emergency', 'lesson', 'attention', 'safeguarding', 'bullying', 'independence', 'trust', 'office', 'cost'],
    },
    rubric: {
      criteria: [c('stakeholder_fairness', 0.4), c('specificity', 0.2), c('rebuttal_real', 0.2, { name: 'The clash is a real clash' }), c('integration', 0.2)],
      solo: {
        3: 'Four stakeholders with distinct, fairly-stated interests, and a clash that is genuinely irreducible.',
        4: 'Notices that one stakeholder holds two interests that conflict *with each other*, and says what that means for the policy.',
      },
    },
    checks: { requiredFields: ['s1', 's2', 's3', 's4', 'clash'], capIfMissing: { clash: 0.65 } },
    hints: [
      'Read your least favourite stakeholder\'s paragraph. Would that person actually sign it, or would they say "that is not what I think"?',
      'The office staff are the ones people forget. Who has to hold 900 pouches, hand them back, and deal with the ones that break?',
      'A fairly-stated opposing view on school uniform: *"For me it is not about smartness — it is that without a uniform I would be asked for expensive clothes every September and I cannot afford that argument."* Notice it gives the person their strongest reason, not their weakest. Rewrite your weakest stakeholder like that.',
    ],
    misconceptions: [
      { signal: 'all stakeholders sound like the student', tutorMove: 'Ask what the safeguarding lead is responsible for that a student is not.' },
      { signal: 'clash is stated as a preference difference', tutorMove: 'Ask whether a clever policy could satisfy both — if yes, it is not yet a real clash.' },
    ],
    bridge: 'In the next disagreement you watch, write the other side\'s view until they would sign it.',
  },
  {
    id: 'lat-t3-po-library',
    strand: 'lateral', moves: ['po', 'random_entry'], tier: 3, difficulty: 1.2,
    domain: 'design', register: [13, 16],
    title: 'PO: the library has no books',
    stimulus: 'Your school library is used by nine people at lunchtime. The librarian has tried posters, a book club, and beanbags.',
    prompt: 'Use a **provocation**. Write a deliberately impossible statement about the library (starting "PO:"), then *move* from it — do not judge it, use it as a stepping stone — until you land on an idea that could actually be tried on Monday. Show the movement.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'po', label: 'PO: (your impossible statement)', required: true, minWords: 5 },
        { id: 'movement', label: 'The movement — what does that make you notice?', required: true, minWords: 20 },
        { id: 'idea', label: 'The usable idea it produced', required: true, minWords: 15 },
        { id: 'monday', label: 'What exactly happens on Monday to test it?', required: true, minWords: 12 },
      ],
      commonIdeas: ['more posters', 'a book club', 'comfier chairs', 'free snacks'],
      conceptVocabulary: ['quiet', 'noise', 'space', 'lunch', 'friends', 'shelves', 'lend', 'stay', 'reason', 'room'],
    },
    rubric: {
      criteria: [c('movement', 0.4), c('originality', 0.3), c('specificity', 0.3, { name: 'Monday test is concrete' })],
      solo: {
        3: 'A real provocation, a visible movement, and an idea that could not have been reached by asking "how do we get more people in the library?"',
        4: 'Notices that the provocation exposed an assumption ("the library is for books") and names that assumption directly.',
      },
    },
    checks: { requiredFields: ['po', 'movement', 'idea', 'monday'], capIfMissing: { movement: 0.5 } },
    hints: [
      'Is your PO actually impossible? If someone could reasonably do it, it is a suggestion, not a provocation.',
      'Try taking the *main function* away: "PO: the library has no books." Now — what is the room for, if not books? Follow that, do not argue with it.',
      'Worked movement: *"PO: the bus has no seats." → notice: seats are what makes buses expensive to clean and slow to fill → notice: standing is fine for two stops → idea: a short shuttle route with almost no seats that runs three times as often.* The impossible statement was never adopted; it just moved attention. Redo your movement like that.',
    ],
    misconceptions: [
      { signal: 'provocation is a sensible suggestion', tutorMove: 'Ask them to remove the thing the place is defined by.' },
      { signal: 'movement is a rejection of the PO', tutorMove: 'Remind them: do not judge it, ask what it makes visible.' },
    ],
    bridge: 'Take something at home that is "obviously necessary" and PO it away for five minutes.',
  },
];
