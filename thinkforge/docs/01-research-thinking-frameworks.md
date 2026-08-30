# Research synthesis: frameworks for teaching thinking to 9–15 year-olds

This document is the evidence base for Thinkforge. It surveys the major thinking
frameworks, judges the quality of the evidence behind each, and extracts the
*instructional moves* that the platform can actually teach, elicit and score.

The rule applied throughout: **a framework earns a place in the curriculum only if
its moves can be (a) demonstrated in a worked example, (b) performed by a 9–15
year-old on a concrete task, and (c) observed in a student response as evidence.**
Frameworks that are only descriptions of thinking (rather than procedures for it)
are used as *assessment scaffolding*, not as taught content.

---

## 1. What the evidence says about teaching thinking at all

Four findings shape the entire design.

**1.1 Explicit instruction in thinking works, but modestly.** Abrami et al.'s
meta-analysis of 341 effect sizes found a weighted mean effect of *g* = 0.30 for
instructional interventions targeting critical thinking. The three highest-yield
strategies were (1) **dialogue** — especially teacher-posed questions and
discussion, (2) **authentic or situated problems**, and (3) **mentoring**; they
work best *in combination*. This is the single most important design input: a
thinking platform that is a quiz bank will underperform a platform that is a
dialogue over authentic problems with a mentor-like presence.

**1.2 Far transfer is weak.** Sala & Gobet's second-order meta-analyses of
cognitive training (chess, music, working-memory) find small-to-null far-transfer
effects: trained skills improve the trained task and near neighbours, and rarely
generalise. The honest conclusion is *not* "don't teach thinking" — Abrami's
interventions taught thinking *in content*, which is different from brain
training. It is: **never assume transfer; engineer it.** Thinkforge therefore
re-instantiates every thinking move across at least three distinct domains
(science/nature, everyday & social life, design & invention) and uses explicit
"bridging" reflection, and it *measures* transfer rather than claiming it (see the
Transfer Index in `03-scoring-tutoring-evolution.md`).

**1.3 Metacognition is the best-evidenced lever available.** The EEF rates
metacognition and self-regulation as high-impact/low-cost, with an average impact
around +7 months' additional progress, while warning that the impact is hard to
realise in practice — the effect comes from *disciplined* planning, monitoring and
evaluation routines, not from telling children to "reflect". Metacognition is
therefore a first-class strand in Thinkforge, not a garnish, and it is
instrumented (calibration, strategy choice, revision gain).

**1.4 Novices need worked examples; experts need problems.** Cognitive load
theory's worked-example effect and the guidance-fading effect (Sweller, Renkl)
show that full worked examples beat unguided problem solving early in skill
acquisition, and that *completion problems* — worked examples with successively
faded steps — beat alternating example/problem pairs. This gives Thinkforge its
scaffolding ladder: **study → complete → attempt with hints → attempt clean**, with
fading driven by measured ability rather than by lesson number.

---

## 2. Frameworks surveyed

### 2.1 Lateral & divergent thinking — Edward de Bono (CoRT, Six Thinking Hats)

**What it is.** De Bono distinguished *vertical* thinking (digging the same hole
deeper) from *lateral* thinking (digging elsewhere), and packaged it as direct
instruction: the CoRT programme is ~60 modular lessons of explicitly named
attention-directing tools, taught as procedures to be practised in a few minutes
each.

**The teachable moves.**
- **PMI** — force attention to Plus, Minus and Interesting points before judging.
- **CAF** — "Consider All Factors" before choosing.
- **C&S** — Consequence & Sequel: immediate / short / medium / long-term effects.
- **APC** — Alternatives, Possibilities, Choices: generate ≥3 rival options.
- **OPV** — Other People's Views: enumerate stakeholders and their view.
- **PO / provocation** — assert a deliberately unreasonable statement and *move*
  from it to a usable idea ("PO: cars have square wheels").
- **Random entry** — inject an unrelated noun and force a connection.
- **Concept fan** — climb from a specific idea to the concept, then fan back down
  to new specifics.
- **Six Thinking Hats** — serialised parallel thinking: white (facts), red
  (feelings), black (caution), yellow (benefits), green (new ideas), blue
  (process control).

**Evidence quality: mixed-to-weak but with useful mechanism.** CoRT is enormously
widely adopted and there is positive evidence for short-term gains in divergent
thinking attitudes and fluency, but critics (notably Weisberg) argue the evidence
for lateral thinking as a distinct creative mechanism is thin and that creativity
is better described as logical search, trial-and-error and feedback.

**How Thinkforge uses it.** The tools are adopted as **attention-directing
protocols** — which is their defensible core — not as a theory of creativity.
They are excellent for a platform because each tool produces a *structured
artefact* (three PMI columns, a stakeholder list, a provocation plus a movement)
that is easy to elicit and easy to score for fluency, flexibility and originality
in the Guilford sense. Claims made to students are kept to the mechanism ("this
forces you to look where you wouldn't"), never "this makes you creative".

### 2.2 Analysis & synthesis — Bloom (revised) and SOLO (Biggs & Collis)

**Bloom's revised taxonomy** (Anderson & Krathwohl) gives the cognitive-process
verbs: remember, understand, apply, **analyse**, **evaluate**, **create**. Useful
for writing task prompts; poor as a measurement scale, because it classifies the
*task* rather than the *response*.

**SOLO** classifies the **structure of the observed response** in five levels:
prestructural → unistructural (one relevant aspect) → multistructural (several
aspects, unrelated) → relational (aspects integrated into a coherent whole) →
extended abstract (generalised beyond the given, applied to a new context).

**Why SOLO is the backbone of Thinkforge's measurement.** It is response-based,
so it can be applied uniformly to a written answer, an idea list, a causal
diagram or a chat transcript; it is complexity-graded, so it distinguishes "wrote
a lot" (multistructural) from "connected things" (relational) — exactly the
distinction a naive AI scorer gets wrong; and it defines a *ceiling* per level
that makes rubric anchors writeable. Every open-response rubric in the platform
carries SOLO anchors, and the student's per-strand level is reported on the SOLO
band, not as a percentage.

### 2.3 Critical thinking structure — Paul & Elder

The Paul–Elder model has three parts: **eight elements of reasoning** (purpose,
question at issue, information, interpretation/inference, concepts, assumptions,
implications & consequences, point of view), **nine intellectual standards**
(clarity, accuracy, precision, relevance, depth, breadth, logic, significance,
fairness) applied to those elements, and the **intellectual traits** that grow
from habitual practice.

**How Thinkforge uses it.** The elements are the **diagnostic grid for the
tutor**: when a response is weak, the tutor's job is to identify *which element is
missing or unexamined* (usually assumptions, point of view, or implications) and
ask about that one. The standards become the vocabulary of feedback ("this is
accurate but not deep — you have one cause where there are three layers"). The
traits are explicitly *not* scored: they are dispositions, and scoring a child's
"intellectual humility" would be both unreliable and inappropriate.

### 2.4 Argumentation — Toulmin

Toulmin decomposes an argument into **claim, grounds/data, warrant** (the
principle linking data to claim), **backing** (support for the warrant),
**qualifier** (how strongly the claim holds) and **rebuttal** (the exception or
counter-case).

**Why it is ideal for this age group and for machine scoring.** It converts a
vague instruction ("give a good argument") into six named slots. Slot-filling can
be assessed *structurally* without AI (did the student produce a warrant at all?)
and *qualitatively* with AI (does the warrant actually license the inference?).
The warrant is where 11–15 year-olds characteristically fail — they supply data
and claim with an unstated leap — which makes it a high-value teaching target.
Qualifier and rebuttal directly train the fair-mindedness Paul–Elder cares about.

### 2.5 Logic & inference

The teachable core for this age band, drawn from the standard reasoning
literature and classic tasks:
- **Validity vs truth** — an argument can be valid with false premises, and a true
  conclusion can follow from a bad argument. This dissociation is the single most
  useful logical idea to install early.
- **Conditional reasoning** — affirming the antecedent / denying the consequent
  (valid) vs affirming the consequent / denying the antecedent (invalid); the
  Wason selection task as a diagnostic of falsification.
- **Quantifiers and set relations** — all/some/none, Euler/Venn representation.
- **Necessary vs sufficient conditions.**
- **Informal fallacies** — ad hominem, false dilemma, hasty generalisation,
  post hoc ergo propter hoc, appeal to authority/popularity, straw man,
  survivorship bias, base-rate neglect.
- **Falsification** — what evidence *would* change my mind? (the disposition that
  makes the rest operational).

### 2.6 Reverse engineering & causal analysis

A cluster of "work backwards from the artefact" procedures:
- **Polya's four steps** (understand → plan → carry out → look back) and
  specifically his **work-backwards** heuristic — start at the goal state and ask
  what must immediately precede it.
- **Black-box probing** — infer a hidden rule from input/output pairs. The
  quality move is the **control-of-variables strategy** (change one thing at a
  time), a well-studied and highly teachable middle-school skill, plus the
  discipline of designing a test that could *disconfirm* the current hypothesis.
- **5 Whys / fault tree / Ishikawa** — layered cause analysis; the teachable
  distinction is *proximate vs root cause* and *cause vs correlate*.
- **Design intent recovery** — given an object or a rule, reconstruct the problem
  it was built to solve and the constraints its designer faced ("why is a
  manhole cover round?" as a genre).

This strand is under-served in school curricula and extremely well-suited to an
interactive platform, because probing a black box generates *process data*
(how many tests, were they controlled, did they discriminate between hypotheses)
that is objectively scorable without any AI at all.

### 2.7 Systems thinking — Meadows

Stocks and flows, feedback loops (reinforcing vs balancing), delays, unintended
and second-order consequences, and the ranked **leverage points** (parameters →
buffers → feedback loops → rules → goals → paradigms). For 9–15 year-olds the
tractable moves are: draw the causal loop, label each link + or −, identify
whether a loop is reinforcing or balancing, find the delay, and predict the
second-order effect of an intervention ("and then what happens?").

### 2.8 Invention & design — TRIZ and design thinking

**TRIZ** (Altshuller) contributes two child-accessible ideas: the **contradiction**
("we want X *and* not-X" — e.g. an umbrella that is big when open and small when
carried) and **ideality** (the ideal final result: the function happens with no
cost or harm), plus a handful of the 40 inventive principles (segmentation,
nesting, prior action, "the other way round", dynamism).

**Design thinking** (Stanford d.school lineage: empathise → define → ideate →
prototype → test) contributes the *problem-framing* move: converting a vague
complaint into a well-formed "How might we…" statement with a user, a need and an
insight. Framing is where most student design work fails, and it is scoreable.

**Analogical transfer** — mapping structure (not surface) from a source domain to
a target ("how is a school like an ant colony?") — is the mechanism that both
frameworks rely on and is worth teaching directly, since structural mapping is
exactly what novices fail to do.

### 2.9 Metacognition & self-regulation

Plan → monitor → evaluate, over an explicit strategy repertoire. The specific
instrumented moves in Thinkforge:
- **Strategy selection** — given a problem, name the tool you'll use *and why*.
- **Calibration** — predict your score before submitting, compare after
  (scored with a Brier-style penalty); poor calibration is the most common and
  most fixable metacognitive fault.
- **Error autopsy** — classify your own mistake (misread the question / missing
  step / wrong tool / stopped too early / assumption unexamined).
- **Bridging** — "where else would this move work?" (the transfer prompt).

---

## 3. Developmental fit for ages 9–15

The band spans a real cognitive discontinuity, so the platform is banded, not
uniform.

- Around **age 9–10**, reasoning is largely concrete: children reason well about
  tangible situations and specific cases (justice = *this* punishment was unfair),
  and struggle with hypotheticals detached from experience.
- From roughly **age 11–12**, formal-operational reasoning emerges — hypothetical,
  counterfactual and propositional thinking — but the research consistently shows
  it arrives *unevenly* and many adolescents apply it inconsistently or only in
  familiar content. Never gate content on age alone.
- **Metacognitive ability rises significantly across adolescence**, peaking in
  late adolescence, and processing speed levels off around age 15. So
  metacognitive demands should scale up through the band, and time pressure
  should be minimal at the bottom of it.
- Late in the band (14–15), students can treat a principle as an object of thought
  (is justice compatible with mercy?), which unlocks the extended-abstract SOLO
  level and self-critique of their own reasoning.

**Design consequences.** Tier 1 tasks are concrete, single-move, richly
exemplified, and short. Abstraction, counterfactuals, multi-move chains and
self-critique are introduced by *measured ability* (Elo) with age only setting the
default entry point and the content register (context, vocabulary, and reading
load).

## 4. Evidence for the AI components

- **Socratic tutoring beats answer-giving for durable learning.** Recent studies
  of LLM tutors report that Socratic-guidance tutors and direct-answer tutors
  produce similar in-task performance, but Socratic students show higher later
  learning gains and adopt understanding-driven strategies when subsequently using
  an unconstrained model — even though they *perceive* the Socratic tutor as less
  efficient. Two consequences: the tutor must never hand over answers, and the
  product must not optimise for student-reported ease.
- **RCTs of well-designed LLM tutors** report learning gains at or above in-class
  active learning, with the effect attributed to research-based design
  (scaffolding, conceptual setup before execution) rather than to the model.
- **LLM-generated feedback quality is uneven**, which is why Thinkforge constrains
  AI scoring with deterministic caps, rubric anchors, evidence-span requirements
  and a human review queue rather than trusting a free-form judgement.
- **Elo rating systems** are a well-validated, cheap alternative to IRT/BKT for
  online ability and difficulty estimation, performing comparably to the Rasch
  model in simulation, updating after every response, and requiring no item
  pre-calibration. Known failure mode: with adaptive selection and simultaneous
  student/item updates, rating variance inflates and estimates may not converge —
  mitigated here with a dynamic K (uncertainty-decayed) and by freezing item
  difficulty once its observation count passes a threshold.

## 5. Safety, privacy and age-appropriateness

The regulatory floor for a 9–15 product with an AI chat surface (2025–26):
COPPA's updated rule (verifiable parental consent, data minimisation, deletion
rights, limits on using children's data for training), age-appropriate design
codes, and the emerging AI-chatbot statutes requiring clear non-human disclosure
and crisis routing for minors. Design consequences, implemented in the platform:
data minimisation to a display name and age band; no free-form chat outside a
task context; persistent "this is an AI" disclosure; input/output moderation;
a distress-signal path that hands off to a named adult; full transcript
visibility for the supervising teacher/parent; export and hard-delete; and no
model training on student work.

## 6. What made the cut

| Framework | Strand | Verdict |
|---|---|---|
| CoRT tools (PMI/CAF/C&S/APC/OPV), PO, random entry, concept fan, SCAMPER, Six Hats | Lateral | **In** — as attention-directing protocols producing scoreable artefacts |
| SOLO | Measurement backbone | **In** — every open rubric is SOLO-anchored |
| Bloom revised | Task authoring | **In** — for prompt verbs only, not as a scale |
| Paul–Elder elements & standards | Tutor diagnosis + feedback vocabulary | **In**; traits explicitly not scored |
| Toulmin | Argumentation | **In** — six named slots, hybrid structural + AI scoring |
| Formal/informal logic, Wason, fallacies | Logic | **In** |
| Polya, work-backwards, black-box probing, CVS, 5 Whys | Reverse engineering | **In** — richest source of objective process data |
| Meadows systems tools | Systems | **In** — simplified to loops, delays, second-order effects, leverage |
| TRIZ contradiction & ideality, design thinking framing, analogical mapping | Synthesis & invention | **In** — TRIZ reduced to two ideas + 5 principles |
| Plan–monitor–evaluate, calibration, error autopsy | Metacognition | **In** — first-class strand |
| Learning styles, "brain training" transfer claims, generic IQ-style drills | — | **Out** — no credible evidence of the claimed effect |

---

## Sources

- [Strategies for Teaching Students to Think Critically: A Meta-Analysis (Abrami et al., *Review of Educational Research*)](https://journals.sagepub.com/doi/abs/10.3102/0034654314551063) · [ERIC record](https://eric.ed.gov/?id=EJ1061695) · [full text PDF](https://knilt.arcc.albany.edu/images/9/9b/Critical_thinking_.pdf)
- [Does Far Transfer Exist? Negative Evidence From Chess, Music, and Working Memory Training (Sala & Gobet)](https://journals.sagepub.com/doi/10.1177/0963721417712760) · [Near and Far Transfer in Cognitive Training: A Second-Order Meta-Analysis](https://online.ucpress.edu/collabra/article/5/1/18/113004/Near-and-Far-Transfer-in-Cognitive-Training-A) · [Cognitive Training: A Field in Search of a Phenomenon](https://journals.sagepub.com/doi/10.1177/17456916221091830)
- [EEF Metacognition and Self-Regulated Learning guidance report](https://educationendowmentfoundation.org.uk/education-evidence/guidance-reports/metacognition) · [PDF](https://d2tic4wvo1iusb.cloudfront.net/production/eef-guidance-reports/metacognition/metacognition-and-self-regulated-learning_guidance-report.v.2.4.0.pdf) · [Toolkit entry](https://educationendowmentfoundation.org.uk/education-evidence/teaching-learning-toolkit/metacognition-and-self-regulation)
- [The Guidance Fading Effect (Sweller)](https://cogscisci.wordpress.com/wp-content/uploads/2019/08/sweller-guidance-fading.pdf) · [How Fading Worked Solution Steps Works – A Cognitive Load Perspective (Renkl et al.)](https://link.springer.com/article/10.1023/B:TRUC.0000021815.74806.f6) · [The effect of worked examples on learning solution steps and knowledge transfer](https://www.tandfonline.com/doi/full/10.1080/01443410.2023.2273762)
- [Edward de Bono's Direct Teaching of Thinking (CoRT) — overview PDF](http://www.irdo.si/skupni-cd/cdji/cd-irdo-2011/referati/f-mulej-nastja.pdf) · [de Bono's Thinking Course (full text)](https://ia803207.us.archive.org/32/items/pdfy-RP-OuErwuZWp4xkk/deBonos_thinking_course_text.pdf) · [Creative and Lateral Thinking: Edward de Bono (Burgh, Encyclopedia of Educational Theory and Philosophy)](https://www.researchgate.net/publication/304088397_Creative_and_Lateral_Thinking_Edward_de_Bono)
- [SOLO Taxonomy (John Biggs)](https://www.johnbiggs.com.au/academic/solo-taxonomy/) · [About SOLO Taxonomy (Pam Hook)](https://leadinglearner.me/wp-content/uploads/2014/09/about-solo-taxonomy-by-pam-hook-pdf.pdf) · [SOLO Taxonomy: five levels explained](https://www.structural-learning.com/post/what-is-solo-taxonomy)
- [Paul-Elder Critical Thinking Framework (University of Louisville)](https://louisville.edu/ideastoaction/programs/about/criticalthinking/framework) · [Framework details PDF](https://damiantgordon.com/EducationalModels/CriticalThinking/PaulElder/CriticalThinking-PaulElder-Details.pdf) · [8 elements, 9 standards](https://www.structural-learning.com/post/paul-elder-critical-thinking-framework)
- [Toulmin Argument Model (Writing Arguments in STEM)](https://pressbooks.calstate.edu/writingargumentsinstem/chapter/toulmin-argument-model/) · [Guide to Toulmin Argument (Writing Commons)](https://writingcommons.org/section/genre/argument-argumentation/toulmin-argument/) · [Toulmin's Model of Argumentative Writing (SJSU)](https://www.sjsu.edu/writingcenter/docs/handouts/Toulmin%20Model%20of%20Argumentative%20Writing.pdf)
- [Key systems thinking lessons from Donella Meadows](https://i2insights.org/2023/10/03/meadows-systems-thinking-lessons/) · [Leverage points in system transformation: insights & critiques](https://systemsthinkingalliance.org/transforming-systems-with-leverage-points-insights-and-critiques-and-future-directions/) · [Breakthrough Thinking with TRIZ: an overview](http://www.xtriz.com/TRIZforBusinessAndManagement.pdf)
- [A Brief Introduction to Evidence-Centered Design (Mislevy, Almond & Lukas)](https://files.eric.ed.gov/fulltext/ED483399.pdf) · [Wiley/ETS record](https://onlinelibrary.wiley.com/doi/10.1002/j.2333-8504.2003.tb01908.x) · [Expanded ECD (e-ECD) for learning and assessment systems](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2019.00853/full)
- [The Power of Feedback — four levels (Hattie & Timperley), synopsis](https://ohiop20litcollab.org/wp-content/uploads/2022/10/Synopsis-Power-of-Feedback-2012.pdf) · [How to optimise Hattie and Timperley's feedback levels (BERA)](https://www.bera.ac.uk/blog/how-to-optimise-the-use-of-hattie-and-timperleys-feedback-levels-for-student-learning)
- [Applications of the Elo rating system in adaptive educational systems (Pelánek)](https://www.sciencedirect.com/science/article/abs/pii/S036013151630080X) · [Balancing stability and flexibility: dynamic K for Elo in adaptive learning](https://link.springer.com/article/10.1007/s11257-025-09439-z) · [Keeping Elo alive: evaluating and improving measurement properties](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12784335/)
- [Reflective Dialogue or Prompt Refinement? Effects of Tutor Scaffolding on Students' Independent LLM Use](https://arxiv.org/abs/2607.03303) · [A Theory of Adaptive Scaffolding for LLM-Based Pedagogical Agents](https://arxiv.org/pdf/2508.01503) · [Socratic AI in K–12 Science Classrooms: an RCT](https://www.researchgate.net/publication/398686102_Socratic_AI_in_K-12_Science_Classrooms_Effects_on_Critical_Thinking_Motivation_and_Self-Regulation_in_a_Randomized_Controlled_Trial) · [Evaluating the quality of LLM-generated feedback](https://arxiv.org/pdf/2511.04213)
- [Cognitive development during adolescence (Lumen Lifespan Development)](https://courses.lumenlearning.com/wm-lifespandevelopment/chapter/cognitive-development-during-adolescence/) · [The development of metacognitive ability in adolescence (Weil et al.)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3719211/) · [Piaget's formal operational stage](https://www.simplypsychology.org/formal-operational.html)
- [COPPA compliance in 2025: a practical guide for tech, EdTech and kids' apps](https://blog.promise.legal/startup-central/coppa-compliance-in-2025-a-practical-guide-for-tech-edtech-and-kids-apps/) · [End-of-year 2025 state and federal developments in minors' privacy](https://www.insideprivacy.com/childrens-privacy/end-of-year-2025-state-and-federal-developments-in-minors-privacy/) · [The emerging regulatory framework of AI chatbots](https://industryselfregulation.org/media-resource/media/blog/ai-chatbot-regulations)
