import { route, render, api, store, refreshGame } from './core.js';
import { home, session, mission, onboarding } from './views/learn.js';
import { growth, moves, about } from './views/growth.js';
import { teacher } from './views/teacher.js';
import { forge } from './views/forge.js';
import { duel } from './views/duel.js';

route('home', home);
route('start', onboarding);
route('session', session);
route('mission', mission);
route('growth', growth);
route('moves', moves);
route('about', about);
route('teacher', teacher);
route('forge', forge);
route('duel', duel);

store.status = await api.get('/api/status').catch(() => null);
await refreshGame();
render();
