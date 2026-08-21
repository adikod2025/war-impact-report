import { route, render, api, store } from './core.js';
import { home, session, mission, onboarding } from './views/learn.js';
import { growth, moves, about } from './views/growth.js';
import { teacher } from './views/teacher.js';

route('home', home);
route('start', onboarding);
route('session', session);
route('mission', mission);
route('growth', growth);
route('moves', moves);
route('about', about);
route('teacher', teacher);

store.status = await api.get('/api/status').catch(() => null);
render();
