import { h, api, store, go, refreshGame } from '../core.js';
import { onboarding } from './learn.js';

const strandColour = (id) => (store.status?.strands || []).find((x) => x.id === id)?.colour || 'var(--accent)';

export async function forge() {
  if (!store.studentId) return onboarding();
  const g = await refreshGame();
  if (!g) return h('p', {}, 'Could not load the forge.');

  return [
    h('div', { class: 'row between' },
      h('div', {},
        h('h1', {}, 'The Forge'),
        h('p', { class: 'muted' }, 'Tools you have forged, work you have proved, and what to go after next.')),
      h('div', { class: 'pill-row' },
        h('span', { class: 'tag' }, `${g.rank.mark} ${g.rank.name}`),
        h('span', { class: 'tag' }, `${g.deck.owned}/${g.deck.total} tools`),
        h('span', { class: 'tag' }, `${g.trophies.length} trophies`))),

    h('div', { class: 'spacer' }),
    h('div', { class: 'grid two' }, rankCard(g), streakCard(g)),
    h('div', { class: 'spacer' }),
    questCard(g),
    h('div', { class: 'spacer' }),
    h('div', { class: 'grid two' }, classGoalCard(g), leaderboardCard(g)),
    h('div', { class: 'spacer' }),
    bossCard(g),
    h('div', { class: 'spacer' }),
    deckCard(g),
    h('div', { class: 'spacer' }),
    trophyCard(g),
    h('div', { class: 'spacer' }),
    marksCard(g),
    h('div', { class: 'spacer' }),
    h('div', { class: 'card tint' },
      h('h3', {}, 'What XP is, and is not'),
      h('p', {}, 'Nothing here is paid for being right. XP comes from carrying a tool somewhere new, predicting your own score honestly — even a low one — revising after coaching, and working unaided. The fastest way to earn is also the most useful thing you could be doing.'),
      h('p', { class: 'muted' }, 'Nothing you have earned can ever be taken away, there are no timers anywhere, and you can switch all of this off without losing a single piece of learning progress.')),
  ];
}

function rankCard(g) {
  return h('div', { class: 'card' },
    h('div', { class: 'row between' },
      h('h3', { style: { margin: 0 } }, `${g.rank.mark} ${g.rank.name}`),
      h('span', { class: 'tag' }, `${g.xp} XP`)),
    h('div', { class: 'xpbar', style: { margin: '10px 0 6px' } }, h('i', { style: { width: `${Math.round(g.rank.progress * 100)}%` } })),
    g.rank.next
      ? h('small', { class: 'muted' }, `${g.rank.toNext} XP to ${g.rank.next.name} ${g.rank.next.mark}`)
      : h('small', { class: 'muted' }, 'Top rank. The deck is the thing to finish now.'),
    h('div', { class: 'row', style: { marginTop: '12px' } },
      h('span', { class: 'tag' }, `✦ ${g.sparks} sparks`),
      h('span', { class: 'tag' }, `${g.weekXp} XP this week`)));
}

function streakCard(g) {
  return h('div', { class: 'card' },
    h('div', { class: 'row between' },
      h('h3', { style: { margin: 0 } }, `🔥 ${g.streak.current} day${g.streak.current === 1 ? '' : 's'} in a row`),
      h('span', { class: 'tag' }, `best ${g.streak.longest}`)),
    h('p', { class: 'muted' }, `You hold ${g.streak.freezes} freeze${g.streak.freezes === 1 ? '' : 's'}. A freeze covers a day you miss, automatically. Miss more than that and the streak simply starts again — nothing you earned is lost, and we will never nag you about it.`),
    h('div', { class: 'row' },
      spendButton(g, 'freeze', `Buy a freeze · ✦${g.spend.freeze.cost}`),
      spendButton(g, 'free_choice', `Free choice of commission · ✦${g.spend.free_choice.cost}`)));
}

function spendButton(g, item, label) {
  const cost = g.spend[item]?.cost ?? Infinity;
  return h('button', {
    class: 'small', disabled: g.sparks < cost,
    onclick: async (e) => {
      e.target.disabled = true;
      const out = await api.post(`/api/students/${store.studentId}/spend`, { item }).catch((err) => err.data || { error: 'failed' });
      if (out.error === 'free_choice') return;
      if (item === 'free_choice' && out.ok) return go('moves');
      go('forge');
    },
  }, label);
}

function questCard(g) {
  const daily = g.quests.filter((q) => q.period === 'day');
  const weekly = g.quests.filter((q) => q.period === 'week');
  const row = (q) => h('div', { class: `quest ${q.done ? 'done' : ''}` },
    h('div', { class: 'top' },
      h('strong', {}, `${q.done ? '✓ ' : ''}${q.label}`),
      h('span', { class: 'tag' }, `${q.xp} XP`)),
    h('small', { class: 'muted' }, q.blurb),
    h('div', { class: 'prog' }, h('i', { style: { width: `${Math.round((q.progress / q.goal) * 100)}%` } })),
    h('small', { class: 'muted' }, `${q.progress} of ${q.goal}`));

  return h('div', { class: 'card' },
    h('div', { class: 'row between' },
      h('h3', { style: { margin: 0 } }, 'Quests'),
      h('div', { class: 'row' },
        h('button', { class: 'small', onclick: async () => { await api.post(`/api/students/${store.studentId}/quests/reroll`, { period: 'day' }); go('forge'); } }, 'Swap today’s'),
        h('button', { class: 'small', onclick: async () => { await api.post(`/api/students/${store.studentId}/quests/reroll`, { period: 'week' }); go('forge'); } }, 'Swap the weekly'))),
    h('small', { class: 'muted' }, 'You choose what to chase. Swapping costs nothing — picking your own target is the point.'),
    h('div', { class: 'spacer', style: { height: '10px' } }),
    h('div', { class: 'grid three' }, daily.map(row)),
    h('div', { class: 'spacer', style: { height: '10px' } }),
    weekly.map(row));
}

function classGoalCard(g) {
  const cg = g.classGoal;
  return h('div', { class: 'card' },
    h('h3', {}, 'The Great Commission'),
    h('p', { class: 'muted' }, 'One target for the whole class this week. Everyone’s work counts towards it, and reaching it opens a boss commission for everybody.'),
    h('div', { class: 'goalbar' },
      h('i', { style: { width: `${Math.round(cg.share * 100)}%` } }),
      h('span', {}, `${cg.progress} / ${cg.target} XP`)),
    cg.reached ? h('p', { style: { marginTop: '10px' } }, '🎉 Reached. The boss commissions are open to everyone this week.') : null);
}

function leaderboardCard(g) {
  const box = h('div', { class: 'stack' });
  const paint = async () => {
    if (!g.leaderboardOptIn) {
      box.replaceChildren(h('p', { class: 'muted' }, 'The ranking is off. It is off for everyone unless they choose otherwise, and it ranks effort this week — never how good you are.'));
      return;
    }
    const data = await api.get('/api/leaderboard');
    box.replaceChildren(
      h('small', { class: 'muted' }, data.basis),
      h('div', { class: 'leader' }, data.rows.length
        ? data.rows.map((r, i) => h('div', { class: `row ${r.studentId === store.studentId ? 'me' : ''}` },
          h('strong', {}, `${i + 1}`), h('span', {}, r.displayName), h('span', { class: 'tag' }, `${r.xp} XP`)))
        : h('p', { class: 'muted' }, 'Nobody else has opted in yet.')));
  };
  paint();
  return h('div', { class: 'card' },
    h('div', { class: 'row between' },
      h('h3', { style: { margin: 0 } }, 'This week’s effort'),
      h('label', { class: 'row', style: { gap: '6px' } },
        h('input', {
          type: 'checkbox', checked: g.leaderboardOptIn,
          onchange: async (e) => { await api.post(`/api/students/${store.studentId}/leaderboard-opt-in`, { optIn: e.target.checked }); go('forge'); },
        }),
        h('small', {}, 'show me'))),
    box);
}

function bossCard(g) {
  return h('div', { class: 'card' },
    h('h3', {}, 'Boss commissions'),
    h('small', { class: 'muted' }, 'Top-tier problems that need several tools at once. They open when you already hold enough of them — a boss is a culmination, not a wall.'),
    h('div', { class: 'spacer', style: { height: '10px' } }),
    h('div', { class: 'grid two' }, g.bosses.map((b) => {
      const missing = new Set(b.missing);
      return h('div', { class: 'card tint strand-edge', style: { '--strand': strandColour(b.strand) } },
        h('div', { class: 'row between' },
          h('strong', {}, b.title),
          h('span', { class: `tag ${b.unlocked ? 'good' : ''}` }, b.unlocked ? 'open' : `${b.have} of ${b.need} tools`)),
        h('div', { class: 'pill-row', style: { margin: '8px 0' } },
          b.moveNames.map((name) => h('span', { class: `tag ${missing.has(name) ? '' : 'good'}` }, `${missing.has(name) ? '○' : '✓'} ${name}`))),
        b.unlocked
          ? h('button', { class: 'primary small', onclick: () => go(`mission/${b.taskId}`) }, 'Take it on')
          : h('small', { class: 'muted' }, `Temper ${b.need} of these to silver and this opens.`));
    })));
}

function deckCard(g) {
  const hall = h('div', { class: 'deck' });
  const paint = (strand) => {
    const cards = g.deck.cards.filter((c) => !strand || c.strand === strand);
    hall.replaceChildren(...cards.map((c) => h('div', { class: `tcard ${c.tier}`, style: { '--strand': strandColour(c.strand) }, title: c.how },
      h('div', { class: 'name' }, c.name),
      h('div', { class: 'pipset' }, [1, 2, 3].map((i) => h('i', { class: i <= c.tierIndex ? 'on' : '' }))),
      h('div', { class: 'meta' },
        h('span', {}, c.tier === 'locked' ? 'not forged' : c.tier),
        h('span', {}, c.rarity),
        c.domains.length ? h('span', {}, `${c.domains.length} situation${c.domains.length === 1 ? '' : 's'}`) : null),
      h('div', { class: 'next' }, c.next))));
  };
  paint(g.deck.halls[0]?.strand || null);

  return h('div', { class: 'card' },
    h('div', { class: 'row between' },
      h('h3', { style: { margin: 0 } }, 'Your tools'),
      h('span', { class: 'tag' }, `${g.deck.gold} tempered to gold`)),
    h('small', { class: 'muted' }, 'A card is your mastery of one move, drawn. There are no packs and no luck: the only way to forge one is to do the thinking.'),
    h('div', { class: 'pill-row', style: { margin: '10px 0' } },
      h('button', { class: 'small', onclick: () => paint(null) }, 'All'),
      g.deck.halls.map((x) => h('button', {
        class: 'small', onclick: () => paint(x.strand),
        style: { borderLeft: `4px solid ${x.colour}` },
      }, `${x.name} ${x.owned}/${x.total}`))),
    hall);
}

function trophyCard(g) {
  const held = new Map(g.trophies.map((t) => [t.key, t]));
  return h('div', { class: 'card' },
    h('h3', {}, 'Trophies'),
    h('small', { class: 'muted' }, 'Each one names the work that earned it. A trophy we cannot point at the evidence for is one we do not give.'),
    h('div', { class: 'spacer', style: { height: '10px' } }),
    h('div', { class: 'trophies' }, g.badges.map((b) => {
      const got = held.get(b.key);
      return h('div', {
        class: `trophy ${b.held ? '' : 'locked'}`,
        title: got?.meta?.evidence?.length ? `Earned on: ${got.meta.evidence.map((e) => e.taskId).join(', ')}` : b.blurb,
      },
        h('div', { class: 'glyph' }, b.glyph),
        h('div', { class: 'tname' }, b.name),
        h('div', { class: 'tblurb' }, b.blurb),
        got?.meta?.evidence?.length ? h('small', { class: 'muted' }, `evidence: ${got.meta.evidence.length} commission${got.meta.evidence.length === 1 ? '' : 's'}`) : null);
    })));
}

function marksCard(g) {
  return h('div', { class: 'card' },
    h('h3', {}, 'Forge marks'),
    h('small', { class: 'muted' }, 'Decoration only. Sparks buy freedom and marks — never hints, scores or levels.'),
    h('div', { class: 'pill-row', style: { marginTop: '10px' } }, g.marks.map((m) => h('button', {
      class: `small ${g.activeMark === m.key ? 'primary' : ''}`,
      disabled: !m.owned && g.sparks < m.cost,
      onclick: async () => {
        if (m.owned) await api.post(`/api/students/${store.studentId}/mark`, { key: m.key });
        else await api.post(`/api/students/${store.studentId}/spend`, { item: m.key }).catch(() => null);
        go('forge');
      },
    }, `${m.glyph} ${m.name}${m.owned ? '' : ` · ✦${m.cost}`}`))));
}
