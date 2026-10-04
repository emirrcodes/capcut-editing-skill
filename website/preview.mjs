import http from 'node:http';
import worker from './worker.mjs';

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1:8765');
  if (url.pathname !== '/capcut' && !url.pathname.startsWith('/capcut/')) {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(req.method === 'HEAD' ? undefined : 'Preview only serves /capcut.');
    return;
  }
  try {
    const response = await worker.fetch(new Request(url, { method: req.method }));
    res.writeHead(response.status, Object.fromEntries(response.headers));
    res.end(Buffer.from(await response.arrayBuffer()));
  } catch {
    res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Preview failed.');
  }
});
server.listen(8765, '127.0.0.1', () => console.log('Plain text: http://127.0.0.1:8765/capcut'));
