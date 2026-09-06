# Como subir e como usar no dia a dia

Passo a passo verificado nesta máquina (Linux, Python 3.14). Os comandos abaixo
foram todos executados; onde algo depende do Google e não pôde ser testado aqui,
está dito.

---

## Antes de começar

Você vai precisar de três coisas: **Python 3.10+** no notebook, uma **conta
Google** (a mesma do celular), e o **Gemini Live no telefone** — é lá que a
sessão acontece, o notebook só prepara e mede.

### Onde se roda cada coisa

Isto vale para todo o resto do arquivo, e é a confusão mais fácil de fazer:

| Onde | O que acontece lá |
|---|---|
| **Terminal do notebook** | **Todos** os comandos `english-tracker` (`pull`, `status`, `prompt`, `add`, `push`, `report`) |
| **Navegador do notebook** | Só duas vezes: o Console do Google (Parte 3) e a tela de autorização que abre sozinha no primeiro `pull` |
| **Celular** | A sessão de voz no Gemini Live, com o prompt colado |
| **Google Drive** | O arquivo `english-log.md`, que é a fonte da verdade |

Sobre **de qual pasta** rodar: para `pull`, `push`, `status`, `prompt` e `add`,
**tanto faz** — eles falam com o Drive e gravam em `~/.english-tracker/`. Só dois
casos dependem do diretório: `--file sample/english-log.md` (caminho relativo,
precisa ser dentro do projeto) e `report`, que escreve o `dashboard.html` na
pasta atual.

O que **não** é opcional é o comando estar no PATH. Ele só está com o venv ativo
naquele terminal; se você fechou o terminal desde a instalação, o
`english-tracker` "desaparece". Duas saídas:

```bash
# ativar o venv neste terminal
cd ~/pessoal/english-tracker && source .venv/bin/activate
english-tracker pull

# ou chamar pelo caminho completo, de qualquer pasta, sem ativar nada
~/pessoal/english-tracker/.venv/bin/english-tracker pull
```

A segunda forma é a do dia a dia — e é para encurtar isso que existe o
`alias en=...` da Parte 7. Configure o alias antes de começar a rotina.

---

## Parte 1 — Instalar (5 minutos)

```bash
cd ~/pessoal/english-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Confira que subiu inteiro:

```bash
pip install -e ".[dev]"             # o [dev] traz o pytest
python -m pytest tests/ -q          # esperado: 151 passed
english-tracker --file sample/english-log.md --offline status
```

O `status` do exemplo mostra 5 sessões e **o dia 5 faltando** — o buraco é
proposital, é o caso de teste da detecção. Se você vê isso, está funcionando.

> O `source .venv/bin/activate` vale só para o terminal atual. Para não depender
> disso, veja o atalho na Parte 7.

---

## Parte 2 — Criar o arquivo no Drive **você mesmo** (2 minutos)

Não espere o professor criar. Faça agora, à mão:

1. No Google Drive, **Novo → Upload de arquivo**, ou crie local e suba: um
   arquivo de texto vazio chamado exatamente **`english-log.md`**.
2. Não use "Novo → Documento Google": Doc nativo o programa **lê mas não
   sobrescreve**, de propósito. Tem de ser texto simples.

Por que primeiro: com o arquivo já existindo e com o nome certo, a primeira
leitura fixa o id dele em `~/.english-tracker/file-id`, e daí em diante toda
escrita vai para esse arquivo e nenhum outro. Se o professor criar sozinho com
outro nome (`English Log`, `english-log (1)`), o primeiro `push` vai **recusar**
por segurança e você terá de resolver a mão.

---

## Parte 3 — Conectar o Drive (uma vez, ~5 minutos)

1. [Google Cloud Console](https://console.cloud.google.com) → crie um projeto
   (nome qualquer, "english-tracker" serve).
2. **APIs e serviços → Biblioteca** → ative a **Google Drive API**.
   Atalho: <https://console.cloud.google.com/apis/library/drive.googleapis.com>
3. Configure o consentimento em **Google Auth Platform** (é onde essas telas
   moram hoje; não ficam mais em "APIs e serviços"). O menu dessa seção tem
   quatro páginas — **Branding**, **Público-alvo**, **Clientes** e
   **Acesso a dados**:
   - **Branding**: nome do app e e-mail de suporte, o mínimo.
   - **Público-alvo**: tipo **Externo** e, em **Usuários de teste** →
     **Adicionar usuários**, o seu próprio e-mail. Sem isso o login falha no
     fim, com "app não verificado".
     Atalho: <https://console.cloud.google.com/auth/audience>
4. **Google Auth Platform → Clientes → Criar cliente** → **Tipo de aplicativo:
   App para computador** → nome qualquer → **Criar**. O JSON sai no modal que
   abre em seguida, ou depois pelo ícone de download na linha do cliente, em
   **IDs do cliente OAuth 2.0**.
   Atalho: <https://console.cloud.google.com/auth/clients>

   > Se algum tutorial (ou uma versão anterior deste arquivo) mandar em
   > **Credenciais → Criar credenciais → ID do cliente OAuth**, é a UI antiga.
   > O caminho velho, `console.cloud.google.com/apis/credentials`, ainda
   > funciona e redireciona para cá.
5. Salve como `~/.english-tracker/credentials.json`:

```bash
mkdir -p ~/.english-tracker
mv ~/Downloads/client_secret_*.json ~/.english-tracker/credentials.json
```

6. Primeira leitura. **No terminal do notebook** (com o venv ativo, ou pelo
   caminho completo do venv — ver "Onde se roda cada coisa", no começo), de
   qualquer pasta:

```bash
english-tracker pull
```

   O navegador abre sozinho pedindo permissão **de leitura**. Autorize com a sua
   conta; a aba avisa que pode fechar e o terminal segue.

Esperado: `Baixado "english-log.md" (modificado em ...)`. O token de leitura fica
em `~/.english-tracker/token.json`.

**A permissão de escrita é pedida só depois, no primeiro `push`** (token separado,
`token-write.json`). São dois consentimentos no navegador porque ler o seu log
não precisa de permissão para escrever no seu Drive.

> ⚠️ **Enquanto o app estiver "Em teste", a autorização vale 7 dias.** É regra do
> Google para consentimento de tipo Externo em status de teste: o refresh token
> expira em uma semana. Consequência prática — mais ou menos toda semana o `pull`
> vai abrir o navegador de novo. Nada se perde, o programa refaz o fluxo sozinho.
> Para acabar com isso é preciso publicar o app (status "Em produção"). O
> controle fica em **Google Auth Platform**, na página **Público-alvo**, num
> bloco "Status da publicação" com o botão **Publicar app** — a documentação do
> Google não descreve essa navegação, então confirme na tela.
> Aceite que a tela de consentimento pode avisar que o app não é verificado; se
> o Google barrar por causa do escopo restrito do Drive, volte para "Em teste" e
> conviva com a re-autorização semanal.
>
> **Isto é opcional e pode esperar.** Faça o sistema funcionar primeiro, com o
> seu e-mail na lista de testadores. Publicar só resolve a fricção semanal, e
> nada depende disso para o dia 1.

---

## Parte 4 — A primeira sessão

```bash
english-tracker prompt            # imprime o prompt do dia 1
```

Isso imprime o prompt no terminal — serve para ler e conferir. Mas para **levar
ao celular**, que é onde a sessão acontece, use o painel:

```bash
english-tracker report
```

Na seção **Próxima sessão** há o botão **Enviar para o WhatsApp**: ele abre o
WhatsApp Web já com o prompt digitado, e você só aperta enviar — a mensagem
aparece no celular na hora. Nada é enviado sem o seu clique; é um link de
conversa (`wa.me`), não a API do WhatsApp.

Para ir direto à conversa com você mesmo, sem passar pelo seletor de contato,
defina o número uma vez (só dígitos, com o 55):

```bash
echo "5551999998888" > ~/.english-tracker/whatsapp
```

Sem número configurado o botão também funciona: abre o seletor, e você escolhe
**Conversar comigo mesmo**.

> Alternativa manual, se preferir: colar o prompt numa nota do Google Keep e
> editar a mesma nota todo dia. Isso não dá para automatizar — a API do Keep tem
> `create`, `get`, `list` e `delete`, e **não tem `update`**.

No telefone:

1. Abra o **Gemini Live** (modo voz).
2. Cole o prompt como primeira mensagem.
3. Fale 15 minutos. Não leia respostas prontas — o objetivo é travar e ser
   corrigido.
   **Espere ser interrompido no meio da frase, por duas razões diferentes.**
   Em pronúncia, ele para, diz o som certo e te faz repetir 3 vezes. Em gramática
   ou palavra errada, ele nomeia a regra em uma linha e te faz **produzir** a frase
   corrigida — e depois uma segunda frase com a mesma regra, para provar que não
   foi sorte. Se os dois erros caem na mesma frase, ele corrige a gramática
   primeiro e volta à pronúncia antes de trocar de assunto.
   Se ele afrouxar, cobre: "you're being soft — check your two zero-tolerance
   regimes". No minuto 8 ele deve dizer quantas correções de pronúncia já fez.
4. **No fim, exija o resumo em voz alta** e ouça se ele diz que salvou no Drive.
   Se ele disser que não conseguiu, anote os erros na hora, de cabeça ou num
   rascunho: você vai precisar deles em 2 minutos.

---

## Parte 5 — Depois da sessão (30 segundos)

```bash
english-tracker pull && english-tracker status
```

Três desfechos possíveis, e o que fazer em cada um:

| O que o `status` diz | Significa | O que fazer |
|---|---|---|
| O dia aparece nas sessões | O professor salvou e o parser entendeu | Nada. Acabou |
| `Dia sem registro: N` | Ele **não** salvou (ou salvou em outro arquivo) | Registrar à mão, abaixo |
| `Registrado, mas ilegível: N` | Salvou num formato que não deu para ler | Registrar à mão, abaixo — o texto original continua no arquivo |

Registrar à mão:

```bash
english-tracker add --day 3
# cole o resumo (ou digite os erros como quiser) e termine com Ctrl-D
```

Ele aceita o formato do contrato de dados e também prosa solta: se não entender,
guarda o texto no log como `Resumo colado` em vez de descartar, avisa que não
extraiu os erros, e sobe **fundindo** com o que estiver no Drive — nunca
substituindo.

No formato certo, para os números entrarem na conta:

```
Erros: [pron] queue; [gram] "depends of" → "depends on"
Acertos: [pron] architecture
Palavras novas: backoff, to retry
Reusou: trade-off
Nota do professor: "Your grammar has a dead letter queue too."
```

Peça sempre o **lado direito** (`→` no erro, `=` na palavra): é ele que vira o
verso do flashcard, e só o professor pode escrevê-lo.

As etiquetas importam: `[pron]` entra na agenda com intervalos mais curtos,
`[gram]` e `[lex]` (palavra errada) têm vaga reservada no `deck`, e `[flu]` marca
travamento. Sem etiqueta funciona, só perde a prioridade — e o parser ainda tenta
adivinhar a classe pelo texto.

As duas linhas do meio são opcionais e valem muito: `Acertos` é o que você
**errava antes e acertou hoje**, `Reusou` é palavra de sessão **anterior** que
você usou sem ser mandado. Elas são o que faz a revisão espaçada avançar — sem
elas o sistema só sabe que um erro não reapareceu, e isso não é a mesma coisa
que você ter acertado.

---

## Parte 6 — A rotina

### O ritual semanal, todo pelo painel

Com o `en serve` aberto, a semana inteira se resolve na tela:

1. **Puxar do Drive** — traz o que o professor escreveu.
2. Se aparecer buraco ou dia ilegível, **Registrar sessão à mão**.
3. **Flashcards** — preencha os versos que faltam (uma vez por semana rende mais
   que no meio da revisão).
4. Leia as três seções que importam: *Onde o inglês falha*, *Dominados* e *Erros
   que se repetem*.
5. **Publicar a semana** — o botão no bloco de pendências.

O painel avisa sozinho quando a **autorização do Google expira** (a cada 7 dias,
por causa do status "Em teste") e quando o **pacote da semana** está esgotado ou
velho. Nos dois casos o botão de resolver está ao lado do aviso. Você não precisa
lembrar de nada disso — só de abrir o painel de vez em quando.

### Opção A: sem o notebook no dia a dia (recomendado)

Se você não está com o note todo dia — que é o caso mais comum — inverta a
ordem: **prepare a semana quando estiver com ele** e deixe o celular resolver o
resto.

```bash
english-tracker prompt --pacote 7 --para-o-drive
```

Isso publica `english-prompt.md` no seu Drive com **a revisão do dia** (para
dizer em voz alta, dois minutos, sem app nenhum) e os **sete próximos prompts**,
um por bloco. No celular: app do Drive → abre o arquivo → copia o bloco do dia → cola no
Gemini Live. Não precisa de terminal, nem de servidor, nem do note ligado.

Pela interface é o botão **A semana**, que ainda manda **um dia por vez para o
WhatsApp** se você preferir tudo no mesmo app.

Para nem precisar lembrar de gerar, instale o timer (`contrib/README.md`): ele
republica o pacote de hora em hora enquanto a máquina estiver ligada.

Nesse arranjo o notebook deixa de ser a máquina de **abrir** o dia e vira a de
**fechar**: registrar o que o professor escreveu, revisar os flashcards, e
regerar o pacote. O que envelhece no pacote é o histórico e a lista de revisão
dentro de cada prompt — o tema do dia está sempre certo.

### Opção B: tudo pelo painel

Um comando, uma vez, e o resto no navegador:

```bash
english-tracker serve
```

Abre `http://127.0.0.1:8765` com o painel, a seção **Revisão de hoje** e uma
barra de botões: **Puxar do
Drive**, **Enviar ao Drive**, **Atualizar**, e um **Registrar sessão à mão** para
quando o professor não salvar. O botão **Enviar para o WhatsApp** leva o prompt
ao celular. Deixe a aba aberta o dia inteiro; para encerrar o servidor, Ctrl-C no
terminal.

Dois botões que parecem iguais e não são:

| Botão | O que faz | Vai à rede? |
|---|---|---|
| **Atualizar** | Relê o log que já está nesta máquina e redesenha a página | Não. Instantâneo |
| **Puxar do Drive** | Busca no Drive o que o professor escreveu e atualiza o local | Sim. É o único |

O cabeçalho diz **quando foi a última sincronização** — é o que responde "o que
estou vendo é de agora ou de ontem?".

**Flashcards**: o botão abre a tela de cartões com o que está vencido. Frente com
o item e a tarefa, verso com a forma certa. Três botões — **Errei** (volta
amanhã), **Já revisei hoje** (sai do baralho de hoje, sem promover a caixa) e
**Próximo**. Cartão sem verso tem um campo para você escrever a forma certa: o
que você escrever vai para o log e sobe para o Drive.

**Clique num quadrado da folha de chamada** para ver o dia: data, tema, erros
corrigidos, palavras novas e a nota do professor. É aí também que fica o
**Apagar este dia**.

O que fica no terminal: só o `serve`. Todo o resto é clique.

### Opção C: comandos

**A revisão de dois minutos**, de manhã, no café — antes ou longe da sessão:

```bash
english-tracker deck
```

Ele lista o que está vencido na repetição espaçada: erros a extinguir e palavras
a fixar. **Diga cada um em voz alta, numa frase sua.** Errar aqui é o objetivo —
é o que traz o item de volta mais cedo. A mesma lista aparece no painel, na
seção "Revisão de hoje".

Detalhe que evita mal-entendido: **o `deck` não marca nada como revisado.** A
agenda avança quando o professor registra `Acertos:` ou `Reusou:` na sessão. O
`deck` é a prática; a evidência vem do diálogo.

**Todo dia, três comandos** (dois minutos somados, fora a sessão):

```bash
english-tracker report      # antes: abre o painel e clica em "Enviar para o WhatsApp"
english-tracker pull        # depois: traz o que o professor escreveu
english-tracker status      # confere se entrou; se não, `add`
```

O `report` gera o painel como arquivo — mostra e tem o botão do WhatsApp, mas os
botões de ação (puxar, enviar, registrar) só funcionam no `serve`, porque um
arquivo estático não tem com quem falar. O `english-tracker prompt` continua
existindo para ler no terminal ou canalizar para outro lugar.

**Uma vez por semana** (domingo, cinco minutos):

```bash
english-tracker report      # abre o painel no navegador
```

O painel é onde se olha o que os números do terminal não mostram: os erros que
mais voltam, os padrões por trás deles, o vocabulário acumulado e a folha de
chamada inteira. Use-o para escolher o que treinar no dia `R` da semana seguinte.

**Se ficar mais de um dia sem rodar:** o `pull` sozinho resolve. Se o Drive tiver
perdido dias que existem no seu cache (o professor pode ter reescrito o arquivo
em vez de acrescentar), o programa **não apaga nada**: funde os dois lados, avisa
em vermelho e manda rodar `push` para devolver ao Drive.

---

## Parte 7 — Atalhos que tiram fricção

No `~/.bashrc`:

```bash
alias en='~/pessoal/english-tracker/.venv/bin/english-tracker'
alias enp='en prompt'                      # o prompt do dia
alias enok='en pull && en status'          # a conferência do pós-sessão
alias enw='en report'                      # o painel como arquivo
alias ens='en serve'                       # o painel interativo, com os botões
alias end='en deck'                        # a revisão de dois minutos
```

Assim não há `activate` nem `cd`: `enp` antes da sessão, `enok` depois.

Para levar o prompt ao celular sem passar pelo mouse:

```bash
en prompt | xclip -selection clipboard     # se tiver xclip instalado
```

---

## Parte 8 — Ver o painel de outro computador

O painel só escuta nesta máquina por padrão. Para abrir de outro lugar, o
caminho seguro é **rede privada** — e não hospedagem na internet.

**Por quê:** o token que protege as ações é servido dentro da própria página.
Quem consegue abrir a página recebe o token, e as ações escrevem no seu Drive.
Numa URL pública, isso é dar acesso ao seu Drive para quem achar o endereço.

**Receita com Tailscale** (grátis para uso pessoal):

1. Instale o Tailscale no notebook e no outro computador, com a mesma conta.
2. No notebook, veja o nome da máquina na rede: `tailscale status`.
3. Suba o painel aberto para a rede privada, em modo leitura:

```bash
en serve --host 0.0.0.0 --host-extra SEU-NOME.ts.net --somente-leitura
```

4. No outro computador, abra `http://SEU-NOME.ts.net:8765`.

Nesse modo o painel mostra tudo — folha de chamada, revisão, flashcards, a
semana — e **recusa qualquer ação** que mude log, Drive ou autorização. Para
registrar sessão, publicar a semana ou renovar autorização, você usa o painel
normal, no notebook.

**Se você quiser abrir de um computador onde não dá para instalar nada**, aí o
caminho é túnel com autenticação na frente:

1. **Cloudflare Tunnel** (grátis) — dá HTTPS e não exige abrir porta no roteador.
2. **Cloudflare Access** (grátis) — põe login com a sua conta Google na frente.
3. E o painel atrás, com as duas travas locais:

```bash
printf 'uma-senha-longa' > ~/.english-tracker/senha && chmod 600 ~/.english-tracker/senha
en serve --host 127.0.0.1 --com-senha --somente-leitura
```

A ordem importa: o login do Google é a tranca principal, a senha é a segunda, e o
modo leitura garante que nem as duas falhando alguém mude seu log. Nunca exponha
sem a primeira: senha em HTTP puro trafega legível.

O notebook precisa estar ligado para o painel. Mas repare que, com ele
desligado, você ainda tem tudo o que o método exige: o **prompt do dia** e a
**revisão** estão no `english-prompt.md` do Drive, e o registro da sessão é o
professor que faz, direto no Drive. O painel é para *fechar* o dia — conferir,
corrigir, publicar a semana seguinte.

---

## Parte 9 — Quando der errado

| Sintoma | Causa | Solução |
|---|---|---|
| `Falta o arquivo de credenciais em ...` | Passo 5 da Parte 3 não foi feito | Salvar o JSON em `~/.english-tracker/credentials.json` |
| `Nenhum arquivo parecido com "english-log"` | O arquivo não existe no Drive, ou está na lixeira | Criar como na Parte 2 |
| `O nome "english-log" não casou exatamente ... Não vou sobrescrever` | O arquivo no Drive tem outro nome | Renomear no Drive para `english-log.md` e rodar `pull`; ou `push --force` se tiver certeza do alvo |
| `... tem conteúdo que não parece um english-log` | O alvo resolvido não é o log | **Não** use `--force` antes de conferir qual arquivo é. Corrija o nome no Drive |
| `Cache local vazio — nada para enviar` | Nunca houve `pull` nem `add` nesta máquina | `english-tracker pull` |
| `english-tracker: comando não encontrado` | O venv não está ativo neste terminal | `source ~/pessoal/english-tracker/.venv/bin/activate`, ou use o caminho completo / o alias da Parte 7 |
| Os botões de ação do painel não fazem nada | Você abriu o arquivo gerado pelo `report`, não o `serve` | Rodar `english-tracker serve` e usar `http://127.0.0.1:8765` |
| `Address already in use` no `serve` | Já há um servidor na porta | Use o que está aberto, ou `serve --porta 8766` |
| O navegador não abre no `pull` | Sessão sem interface gráfica, ou navegador padrão não definido | Rodar num terminal do desktop, não por SSH; o programa precisa abrir a página de consentimento uma vez |
| `Acesso bloqueado: o app não concluiu o processo de verificação` / `Erro 403: access_denied` | O e-mail que você usou não está na lista de testadores | **Google Auth Platform → Público-alvo → Usuários de teste → Adicionar usuários** com aquele e-mail exato, e rode de novo |
| O navegador pede autorização outra vez, sem motivo | O app está "Em teste": o token expira em 7 dias | Autorizar de novo (30 segundos), ou publicar o app — ver o aviso na Parte 3 |
| O navegador diz "app não verificado" | O app não passou por verificação do Google | Só acontece com o app publicado. Em "Em teste", com o e-mail na lista de testadores, não aparece |
| Não encontro a tela de Credenciais | Ela saiu de "APIs e serviços" | **Google Auth Platform → Clientes** (Parte 3, passo 4) |
| `status` mostra um dia que você não fez | O professor escreveu o número errado | Corrija a linha `DIA nn` no arquivo do Drive; dia fora de 1..30 aparece como *Fora do plano* |
| Um dia aparece como ilegível e você sabe que a sessão foi boa | O formato saiu diferente demais | `add --day N` refaz a entrada; o texto antigo continua no arquivo |
| **Registrei um dia sem querer e já enviei ao Drive** | Acontece | Clique no quadrado do dia → **Apagar este dia** (dois cliques, com aviso). No terminal: `english-tracker remove --day N`. O log anterior fica em `~/.english-tracker/backups/` |
| Apaguei um dia e me arrependi | Há cópia de antes de toda escrita | Pegue o conteúdo em `~/.english-tracker/backups/*-pre-remove-diaN.md`, restaure no cache e `push --force` |
| Perdi conteúdo do log | Toda escrita guarda cópia | Veja `~/.english-tracker/backups/`; no Drive, **Arquivo → Histórico de versões** |

---

## O que ainda não funciona (para não procurar)

- **`ENGLISH_TRACKER_START`** existe e nenhuma análise usa: a sequência é contada
  por número de dia do plano, não por calendário. Definir a variável não faz mal
  e não faz efeito. É a primeira melhoria da lista de ideias.
- **`--file` e o Drive não se misturam**: com `--file`, o `add` escreve naquele
  arquivo e não fala com o Drive. Isso é de propósito.
- **A fusão do `push` só acrescenta.** Apagar uma entrada no arquivo local não a
  remove do Drive; para isso existe `push --force`, que substitui o remoto pelo
  local.
