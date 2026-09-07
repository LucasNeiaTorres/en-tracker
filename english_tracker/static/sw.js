// Service worker do painel.
//
// Estratégia: REDE PRIMEIRO, cache como reserva. É a escolha certa aqui porque o
// painel mostra estado que muda — servir cache primeiro exibiria número velho
// com cara de atual, que é o tipo de mentira que este projeto evita em todo
// lugar. Offline, cai para a última versão que você carregou.
//
// Não se pré-carrega nada na instalação: as páginas exigem senha, e um addAll
// que falhasse deixaria o service worker sem ativar. O cache se forma no uso.

const CACHE = 'english-log-v3';
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
  const caminho = new URL(pedido.url).pathname;
  if (caminho.startsWith('/api/')) return;

  // A tela de login e a saída nunca entram no cache. Guardar a tela de login
  // seria o pior defeito possível aqui: ela ficaria salva sob a chave da página
  // que você pediu, e offline o app abriria um formulário que não tem servidor
  // para responder — nenhuma saída.
  if (caminho === '/login' || caminho === '/sair') return;

  evento.respondWith(
    fetch(pedido)
      .then((resposta) => {
        // `redirected` é a trava que importa: sessão expirada faz o servidor
        // responder 303 para /login, o fetch segue o desvio e devolve 200 — que,
        // guardado sem esta checagem, gravaria o formulário de login como se
        // fosse o painel.
        if (
          resposta && resposta.status === 200 && resposta.type === 'basic'
          && !resposta.redirected
        ) {
          const copia = resposta.clone();
          caches.open(CACHE).then((c) => c.put(pedido, copia));
        }

        // Servidor ALCANÇADO mas quebrado (502 do proxy quando o serviço do
        // painel caiu, 503, 500). Isto não é falha de rede, então o `.catch`
        // abaixo nunca dispara — e sem este ramo a pessoa recebia a página de
        // erro crua do proxy no lugar do painel que estava em cache. Medido:
        // com a máquina ligada e o serviço parado, o app mostrava só
        // "502 Bad Gateway". Vale para NAVEGAÇÃO; um recurso que falha deve
        // falhar, senão todo erro vira sucesso.
        if (resposta && resposta.status >= 500 && pedido.mode === 'navigate') {
          return caches.match(pedido)
            .then((r) => r || caches.match(RESERVA))
            .then((r) => r || resposta);
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
