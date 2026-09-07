// Service worker do painel.
//
// Estratégia: REDE PRIMEIRO, cache como reserva. É a escolha certa aqui porque o
// painel mostra estado que muda — servir cache primeiro exibiria número velho
// com cara de atual, que é o tipo de mentira que este projeto evita em todo
// lugar. Offline, cai para a última versão que você carregou.
//
// Não se pré-carrega nada na instalação: as páginas exigem senha, e um addAll
// que falhasse deixaria o service worker sem ativar. O cache se forma no uso.

const CACHE = 'english-log-v1';
const RESERVA = '/';

self.addEventListener('install', (evento) => {
  self.skipWaiting();
});

self.addEventListener('activate', (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((nomes) => Promise.all(
        nomes.filter((n) => n !== CACHE).map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (evento) => {
  const pedido = evento.request;

  // Só GET entra no cache. As ações do painel são POST e precisam do servidor:
  // guardá-las ou responder do cache daria a impressão de que algo aconteceu.
  if (pedido.method !== 'GET') return;

  // /api/ NUNCA passa por aqui. Resposta de API servida do cache é dado velho
  // com cara de atual — e, no caso do /api/ping, faria a página concluir que
  // está online justamente quando não está.
  if (new URL(pedido.url).pathname.startsWith('/api/')) return;

  evento.respondWith(
    fetch(pedido)
      .then((resposta) => {
        if (resposta && resposta.status === 200 && resposta.type === 'basic') {
          const copia = resposta.clone();
          caches.open(CACHE).then((c) => c.put(pedido, copia));
        }
        return resposta;
      })
      .catch(() => caches.match(pedido).then((r) => {
        if (r) return r;
        // A reserva vale só para NAVEGAÇÃO: devolver a página raiz no lugar de
        // um recurso qualquer faria toda falha parecer sucesso (status 200).
        if (pedido.mode === 'navigate') return caches.match(RESERVA);
        return Response.error();
      }))
  );
});
