import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.env.SERVE_ROOT || path.dirname(new URL(import.meta.url).pathname);
const PORT = Number(process.env.PORT || 8787);
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.md': 'text/plain' };

http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x');
  let p = path.join(ROOT, url.pathname === '/' ? 'index.html' : url.pathname);
  if (!p.startsWith(ROOT)) { res.writeHead(403).end(); return; }
  fs.readFile(p, (err, buf) => {
    if (err) { res.writeHead(404).end('not found'); return; }
    res.writeHead(200, { 'content-type': TYPES[path.extname(p)] || 'application/octet-stream' });
    res.end(buf);
  });
}).listen(PORT, () => console.log('serving ' + ROOT + ' on ' + PORT));
