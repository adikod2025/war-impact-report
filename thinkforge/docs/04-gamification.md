# The game layer

Thinkforge is now a game. This document is the argument for *which* game,
because the evidence on gamifying learning is sharply two-sided and the obvious
implementation is the one that has been shown to backfire.

---

## 1. What the evidence says

**1.1 Gamification works — and the moderators say what kind.** Sailer & Homner's
meta-analysis finds significant effects on cognitive (*g* = 0.49), motivational
(*g* = 0.36) and behavioural (*g* = 0.25) learning outcomes, with the cognitive
effect holding up in the high-rigour subset. Crucially, the significant
moderators of behavioural outcomes were **game fiction** and **social
interaction**, and specifically **competition combined with collaboration**.
That is a design instruction, not a footnote: a world and a shared endeavour do
more work than a points counter.

**1.2 The obvious implementation backfires.** Hanus & Fox ran a 16-week
classroom study where the gamified condition got a **leaderboard and badges**.
Those students ended with *less* intrinsic motivation, less satisfaction, and
lower final exam scores than the ungamified class. Naked social comparison plus
trophies is not a neutral addition — it is a documented way to make learning
worse.

**1.3 Rewards undermine when they are controlling, not when they are
informational.** Deci, Koestner & Ryan's meta-analysis of 128 experiments finds
that tangible, expected, performance-contingent rewards significantly undermine
intrinsic motivation. The escape route in the same literature is that
*informational* feedback — telling someone something true about their competence
— does not carry the undermining effect. So every reward in Thinkforge must
**certify something real about the student's thinking**, and be legible as such.

**1.4 SDT gives the three levers.** Autonomy, competence, relatedness. Game
elements that satisfy them help; the same elements that pressure, compare and
control undermine them through the overjustification effect.

**1.5 Age matters across this band.** Younger children need simplified,
single-focus mechanics, clear timely visual feedback, and benefit from
narrative and collaborative challenge; adolescents respond to peer interaction,
clear goals, real-time feedback and dynamic difficulty. Progress bars,
achievements and immediate feedback are consistently the best-liked elements.

---

## 2. The design rules that follow

1. **Reward the behaviour, never the score.** No XP is paid for being right. XP
   is paid for the behaviours the platform exists to build: using a move in a
   domain you have never used it in, predicting your own performance honestly,
   revising after coaching, working unaided, finishing a session.
2. **Every reward is a claim that can be checked.** A badge names the attempts
   that earned it. A card upgrade means a specific mastery condition was met.
   Nothing is awarded for compliance or time served.
3. **The game layer is a *view* of the learning model, not a parallel economy.**
   Your deck is your move mastery, rendered. It cannot be farmed, because the
   underlying state is the same one the teacher's evidence view reads.
4. **Competition only alongside collaboration**, per the moderator that actually
   showed up in the meta-analysis: the class shares one goal, and the
   head-to-head mechanic (the Forge-off) makes you *improve someone else's
   thinking* to win at it.
5. **Social comparison is opt-in and effort-ranked.** The leaderboard is off by
   default, shows only students who opted in, and ranks XP earned this week —
   i.e. effort and growth — never ability, level or score. A teacher can
   disable it for the whole class.
6. **Losing is never punished.** Streaks freeze rather than break; nothing
   already earned can be taken away; a broken streak is described as a forge
   gone cold and relit, not as a failure. There is no currency you can go into
   debt on, and no timer anywhere in the product.
7. **Autonomy is a mechanic, not a slogan.** Quests can be re-rolled, sparks buy
   free choice of mission, and the whole game layer can be switched off by the
   student without losing any learning progress.
8. **No dark patterns.** No loss framing, no "your streak is about to die"
   nagging, no random loot boxes, no pay-to-win, no leaderboard resets designed
   to re-engage, no notifications at all.

---

## 3. The world

**The Forge.** The student is an apprentice in a workshop where thinking tools
are made. Strands are the eight halls of the workshop. Missions are
*commissions*. Moves are *tools you forge and temper*. This is the "game fiction"
moderator: it exists to make the mechanics coherent, and every fictional term
maps onto exactly one real construct.

| Fiction | Real construct |
|---|---|
| The Forge | The platform |
| A commission | A mission (task) |
| A tool card | A thinking move + its mastery state |
| Tempering a tool | Reaching unaided success in more domains |
| Sparks | Currency earned from process behaviours |
| Rank | Cumulative XP band |
| Boss commission | A multi-move Tier-4 task, gated on holding the moves |
| Forge-off | Peer critique duel |
| The Great Commission | The class's shared weekly goal |

---

## 4. Mechanics

### 4.1 XP — paid for process, never for correctness

| Award | XP | What it certifies |
|---|---|---|
| Commission completed | 10 | You produced something markable |
| New tool used | 25 | A move you had never used |
| **New domain for a tool** | 30 | The transfer behaviour — the highest single award |
| Unaided clear | 15 | Score ≥ 0.6 with no nudges taken |
| **Well-calibrated** | 20 | Prediction within 10 points of outcome — *paid even when the score is low* |
| Revised and improved | 20 | Revision gained ≥ 0.15 over the first attempt |
| Depth reached | 15 | Mean rubric criterion ≥ 2 of 3 |
| Tool tempered | 40 | A card advanced a tier |
| Boss cleared | 100 | A multi-move commission at Tier 4 |
| Quest completed | 20–60 | Named behaviour, chosen by the student |

Two properties matter. **Honest calibration pays whether you did well or badly**,
which removes the incentive to inflate confidence. And **nothing pays for a high
score by itself**, which removes the incentive to fish for answers — the fastest
route to XP is to try a known move somewhere new and to predict yourself
accurately.

Ranks: Apprentice → Smith → Journeyman → Artisan → Master → Forgemaster.

### 4.2 Sparks — a currency you spend on autonomy

Earned alongside XP (5 per commission, +3 calibrated, +5 for a new domain).
Spent on: a **streak freeze** (10), **free choice** of any commission outside the
recommended session (8), and cosmetic **forge marks** (25–60). Sparks buy
freedom and decoration. They cannot buy hints, scores, or levels.

### 4.3 The deck — mastery, rendered

Every one of the 45 moves is a card. Its state is computed from the same move
record the teacher's evidence view uses:

| Card state | Condition |
|---|---|
| Locked | never used |
| Bronze | one successful use |
| Silver | two unaided successes, or two domains |
| Gold | two unaided successes **and** two domains — the platform's definition of "held" |

Rarity is derived from how many commissions in the bank teach that move, so a
rare card is genuinely a rare opportunity to practise, not an artificial drop
rate. There are no packs, no duplicates and no randomness: the only way to get a
card is to do the thinking.

### 4.4 Trophies — badges that are credentials

Fourteen badges, each defined by a predicate over real evidence, and each
displayed **with the attempts that earned it**. Examples: *Warrant Smith* (stated
a licensing warrant at level ≥ 2 in three different commissions), *One Thing at a
Time* (ran a black-box investigation with ≥ 80% controlled tests), *Honest Dial*
(calibration index ≥ 80 over at least eight predictions), *Traveller* (used one
move in three domains). A badge you cannot explain is a badge we do not award.

### 4.5 Quests — chosen, re-rollable, behavioural

Three daily quests and one weekly, drawn from a catalogue keyed to the same
behaviours XP pays for, filtered to what this student can actually do today. One
free re-roll: choosing what to work on is the autonomy lever.

### 4.6 Streak — a commitment device with the teeth removed

Streaks are the single most effective retention mechanic in the wild, and they
work through loss aversion — which is exactly what makes them risky for
children. Thinkforge keeps the commitment and removes the loss: two freezes are
held by default and consumed automatically, more can be bought with sparks, a
lapse costs nothing already earned, and the copy never threatens. The streak
counts *days the forge was lit*, not minutes, so a single honest commission
counts.

### 4.7 The Great Commission — the class goal

One shared weekly XP target for the whole class, displayed as a single bar.
Reaching it unlocks a boss commission for everyone. This is the
competition-with-collaboration combination the meta-analysis identified: your
effort is visible and it helps everyone, and the individual leaderboard beside it
is optional.

### 4.8 The Forge-off — a duel you win by improving someone else's thinking

Two students who answered the same commission exchange anonymised answers. Each
must (a) state the strongest thing about the other's answer, fairly enough that
its author would agree, and (b) name the one element that is missing. The
critique is scored against the ordinary rubric criteria — *steelman fairness* and
*warrant* — so the way to win is to think better about someone else's reasoning,
and both students earn XP. Names are never shown.

### 4.9 The leaderboard — off by default

Opt-in per student, teacher-disableable for the class, and ranked on XP earned in
the last seven days, which is effort. It never ranks ability, level or score. If
a class does nothing about this setting, no student ever sees a ranking. This is
a direct response to Hanus & Fox: the mechanic that made their students worse off
is the one mechanic here that a person has to switch on deliberately.

---

## 5. What was refused

- **Points for correct answers.** The fastest way to teach answer-seeking.
- **Timers and speed bonuses.** Thinking tasks carry high intrinsic load, and
  processing speed is still developing across this band.
- **Loot boxes, random drops, gacha.** Variable-ratio reward schedules aimed at
  children.
- **Losable progress, health bars, lives.** Failure has to stay cheap; the tutor's
  entire job is to make a wrong answer the start of something.
- **Streak-loss notifications and nagging.** The commitment device is allowed;
  the anxiety is not.
- **Public ranking by ability.** See Hanus & Fox.
- **Any reward for time spent.** Session length is not an achievement.

## 6. How this is measured

The game layer is not exempt from the platform's own standards. The teacher view
shows XP composition per student, so a class can see *what* is being rewarded —
if XP is coming mostly from transfer and calibration awards, the game is pulling
in the right direction; if it drifts towards attendance XP, that is visible and
fixable. The growth indices are untouched by the game layer, so the honest
measure of whether any of this is working stays independent of the thing being
evaluated.

---

## Sources

- [The Gamification of Learning: a Meta-analysis (Sailer & Homner, *Educational Psychology Review*)](https://eric.ed.gov/?id=EJ1245270) · [PDF](https://paperity.org/p/204315475/the-gamification-of-learning-a-meta-analysis)
- [Assessing the effects of gamification in the classroom (Hanus & Fox, *Computers & Education*)](https://www.sciencedirect.com/science/article/abs/pii/S0360131514002000) · [record](https://www.semanticscholar.org/paper/Assessing-the-effects-of-gamification-in-the-A-on-Hanus-Fox/dff76a9862467d426113ec530f83942016ae3a97)
- [A Meta-Analytic Review of Experiments Examining the Effects of Extrinsic Rewards on Intrinsic Motivation (Deci, Koestner & Ryan)](https://depts.washington.edu/techdocs/papers/deciExtrinsicRewardsAndIntrinsicMotivation99.pdf) · [Extrinsic Rewards and Intrinsic Motivation in Education: Reconsidered Once Again](https://www.selfdeterminationtheory.org/SDT/documents/2001_DeciKoestnerRyan.pdf)
- [Gamification in Action — self-determination theory (selfdeterminationtheory.org)](https://selfdeterminationtheory.org/wp-content/uploads/2020/10/2018_RutledgeWalshEtAl_Gamification.pdf) · [Align the Game to Your Aim: gamification through the lens of SDT](https://icenet.blog/2025/06/17/align-the-game-to-your-aim-considering-gamification-through-the-lens-of-self-determination-theory/)
- [One Size Doesn't Fit All: Age-Aware Gamification Mechanics for Multimedia Learning Environments](https://arxiv.org/pdf/2512.15630) · [Gamification with Purpose: What Learners Prefer to Motivate Their Learning](https://arxiv.org/pdf/2512.08551)
- [How streaks keep Duolingo learners committed to their language goals](https://blog.duolingo.com/how-streaks-keep-duolingo-learners-committed-to-their-language-goals/) · [Keeping the Streak Alive: Motivation and Language Learning in Duolingo (Oulu)](https://oulurepo.oulu.fi/bitstream/handle/10024/54117/nbnfioulu-202502121605.pdf?sequence=1&isAllowed=y)
