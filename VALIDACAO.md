# Validação do english-tracker contra o próprio README

Base: `english-tracker.zip` extraído e executado (Python 3.14.4, Jinja2 3.1.6).
Tudo abaixo foi **verificado rodando**, não inferido da leitura.

---

## Status: os 14 defeitos foram corrigidos

O código extraído do zip virou árvore de trabalho nesta pasta, as correções estão
aplicadas nela, e o pacote atualizado é `english-tracker-corrigido.zip` (o zip
original ficou intacto).

| # | Defeito | Correção |
|---|---|---|
| 1 | `pip install -e .` falhava | `[tool.setuptools.packages.find]` + `package-data`; instalação editável e wheel verificados, template incluído |
| 2 | cabeçalho torto apagava o dia anterior | cabeçalho lido campo por campo (só o número é exigido); linha de campo nunca gruda na entrada anterior |
| 3 | prompt mandava escrever `DD/MM` | `build()` resolve a data de verdade; parâmetro `when` opcional |
| 4 | `push` sobrescrevia sem verificar | alvo por nome exato ou id fixado, conteúdo atual conferido, fusão em vez de substituição, backup antes, `--force` explícito |
| 5 | `add --file X` gravava no cache | `--file` é destino da escrita; sem `--file`, cache |
| 6 | `add` interativo morto e paste descartado | `_ask_list` removido; texto que não casa o formato vai para o log em `Resumo colado`; colar nada não registra nada |
| 7 | `error_themes` mudava de ordem | `sorted(set(...))` + desempate por palavra; teste roda com 4 `PYTHONHASHSEED` diferentes |
| 8 | dia fora de 1..30 inflava estatística | `Report.unknown_days`, fora das contas e visível no painel |
| 9 | vermelho com dois significados | dia técnico passou para `--tech` (caneta azul); vermelho só do professor |
| 10 | escopo OAuth do Drive inteiro para tudo | `drive.readonly` na leitura, `drive` só na escrita, tokens separados |
| 11 | miudezas (`__main__`, deriva do README) | guarda `if __name__`; README e AGENTS atualizados |
| 12 | erro em lista virava sessão vazia | rótulo com continuação em bullet/numerada; entrada sem conteúdo é `sem-conteudo` e não conta como feita |
| 13 | nada reversível | `backups/` datado antes de toda escrita, dos dois lados; `pull` funde em vez de sobrescrever quando o remoto perdeu dias |
| 14 | placeholder `<mistake>` virava erro | descartado no parser |

Suíte: **21 → 48 testes**, com três arquivos novos —
`tests/test_formatos_do_modelo.py` (as formas que a outra IA escreve),
`tests/test_drive.py` (fusão e backup) e `tests/test_cli.py` (o `add`, que não
tinha teste nenhum).

Três coisas apareceram **durante** a correção e foram junto: um cabeçalho com dia
de 4+ dígitos ainda contaminava a entrada anterior (a mesma brecha do defeito 2,
por outro caminho); o painel listava o dia fora do plano e o dia ilegível em
"Últimas sessões", como se fossem sessões; e o `status` escrevia "1 palavras".
As duas primeiras só apareceram olhando a tela renderizada, não o HTML.

O que **não** foi mexido, porque é ideia e não defeito: calendário a partir do
`start_date`, comando `doctor`, comando `week`, exportação de flashcards.

---

## Veredicto

O sistema faz o que o README promete e a arquitetura está coerente com a decisão
central declarada ("nunca assumir que a sessão foi registrada"). O que existe de
código é enxuto, legível e sem gordura.

Há, porém, **um defeito de empacotamento que quebra o primeiro comando da
instalação** e um conjunto de caminhos que violam a própria decisão central —
falham em silêncio, gravando dado errado com cara de dado certo. São exatamente a
classe de problema que o projeto foi construído para não ter.

O mais grave deles decorre da premissa do projeto: **quem escreve o arquivo é
outra IA**. A tolerância do parser está calibrada para ruído de *formatação*
(travessão ou dois-pontos, língua, ano ausente), mas não para variação de
*estrutura* — que é justamente o que um LLM produz. E o pior desfecho não é
perder a entrada: é aceitá-la com o conteúdo vazio, porque isso se lê como um dia
limpo. Ver defeito 12, que é o de maior gravidade da lista.

---

## O que confere

| Afirmação do README | Resultado |
|---|---|
| 21 testes passam | ✅ `21 passed in 0.03s` |
| `sample` tem o dia 5 faltando de propósito | ✅ detectado: `Dia sem registro: 5` |
| `next_day` é o primeiro buraco, não o último+1 | ✅ com dias 1,2,3,4,6 feitos, aponta 5 |
| Parser aceita cabeçalho sem separador (`DIA 15`) | ✅ |
| Parser aceita rótulos em inglês, dia repetido (última vence), data sem ano | ✅ |
| `normalize()` agrupa acento/maiúscula/pontuação | ✅ 3x "esqueci o -s", 2x "architecture" |
| Tokens de cor e tipografia do painel | ✅ template bate com a tabela do README |
| `push()` recusa Google Doc; `_find` sem paginação | ✅ ambos como documentados |
| `dashboard-exemplo.html` corresponde ao gerado hoje | ✅ (salvo a ordem de um chip — ver defeito 7) |

---

## Defeitos

Numerados por ordem de descoberta. Por **gravidade** a ordem é: 12, 2, 13, 1, 4, 3, 5, 6, 7, 8, 9, 10, 11.

### 1. `pip install -e .` não funciona — é o primeiro comando do README

```
error: Multiple top-level packages discovered in a flat-layout: ['sample', 'english_tracker'].
```

O setuptools moderno (78.1.1 aqui) trata `sample/` como um segundo pacote de topo
e recusa o build. Vale para `build_wheel` **e** `build_editable`, ou seja, tanto
`pip install .` quanto `pip install -e .`. O bloco de arranque do `AGENTS.md`
morre na primeira linha pelo mesmo motivo.

Junto disso: não há `package-data`, então o `templates/dashboard.html` não entra
no wheel — instalação não-editável geraria `TemplateNotFound` no `report`.

Correção verificada (4 linhas em `pyproject.toml`, wheel gerado com o template dentro):

```toml
[tool.setuptools.packages.find]
include = ["english_tracker*"]

[tool.setuptools.package-data]
english_tracker = ["templates/*.html"]
```

### 2. Cabeçalho `DIA` malformado apaga o dia anterior (parser.py:86-114)

Quando uma linha começa com `DIA n` mas não casa o padrão completo, ela não é
tratada como cabeçalho — cai como corpo da entrada **anterior**. E aí a linha
`Erros:` daquela sessão **sobrescreve** os erros da sessão anterior.

Reproduzido:

```
DIA 01 — 02/09 — Tipo: D — Tema: um      →  Entry(day=1, errors=['erro do dia 2'])
Erros: erro do dia 1
DIA 02 - DD/MM - Tipo: D - Tema: dois        (o dia 2 desaparece)
Erros: erro do dia 2
```

Ou seja: perde-se a sessão nova **e** corrompe-se a antiga, sem uma linha de
aviso. Formas que o parser rejeita hoje, todas plausíveis vindas de um LLM:

| Entrada | Resultado |
|---|---|
| `DIA 07 - DD/MM - Tipo: R - Tema: x` | ❌ perdido |
| `DIA 08 — 10/09 — Tipo: Técnico — Tema: x` (tipo por extenso) | ❌ perdido |
| `DIA 11 (12/09) — Tipo: T — Tema: x` (data em parêntese) | ❌ perdido |
| `**DIA 12 — 13/09 — Tipo: T — Tema: x**` (negrito markdown) | ❌ perdido |
| `## DIA 14 — ...` / `- DIA 13 — ...` | ❌ perdido |
| `DIA 10 — Tema: x — Tipo: T` (ordem trocada) | ⚠️ aceito, mas o tipo entra no tema |

A regra "linhas não reconhecidas são ignoradas em silêncio" é sadia para o
preâmbulo educado do modelo. Ela **não deveria valer para uma linha que começa
com DIA/DAY**: isso é uma sessão, e sessão que o parser não entende tem de
aparecer em vermelho na folha de chamada, como buraco de tipo diferente
("registrado, mas ilegível"). Duas mudanças resolvem: (a) se casar
`_looks_like_header` e não casar o padrão completo, fechar a entrada corrente e
guardar a linha como anomalia; (b) nunca deixar linha de campo grudar na entrada
anterior depois de um cabeçalho falhado.

### 3. O prompt manda o professor escrever `DD/MM` literal (prompt.py:26, 67)

`build()` passa `date_hint="DD/MM"`, então o modelo recebe o formato exato com um
placeholder no lugar da data. Se ele copiar o molde ao pé da letra — e modelo
copia molde —, sai um cabeçalho que o parser rejeita, caindo no defeito 2. Passe
a data real (`date.today()`, ou a data planejada do dia quando o `start_date`
entrar em uso).

### 4. `push` sobrescreve arquivo inteiro sem verificar o que está lá (drive.py:65-80, 145)

Dois riscos somados:

- **Alvo errado.** `_find` busca `name contains 'english-log'` no Drive todo,
  ordena por modificação e pega o primeiro. Depois `files().update` **substitui o
  conteúdo inteiro** do que achou. Qualquer arquivo cujo nome contenha a string
  (um `english-log-2025`, um `english-logistica`) pode ser zerado. O README
  reconhece o risco na leitura; na escrita ele é destrutivo.
- **Conteúdo mais velho vence.** `add` monta o texto a partir do cache local
  (cli.py:117-120) e `push` sobe isso como verdade. Se o professor escreveu no
  Drive depois do seu último `pull`, o `push` apaga a entrada dele. Não há merge,
  nem checagem de versão/ETag.

Correções na direção da própria filosofia do projeto: casar nome exato, gravar o
`fileId` no `~/.english-tracker/` na primeira resolução, e no `push` baixar o
remoto, parsear os dois, unir por dia (última entrada vence, como já é a regra) e
recusar se o remoto tiver dia que o local não tem — a menos de um `--force`
explícito. Um backup do remoto antes de cada sobrescrita custa cinco linhas e
protege o único arquivo que importa.

### 5. `add --file X` lê X e escreve no cache (cli.py:29 vs 117-120)

Verificado: `add --file sample/english-log.md --offline --day 5` diagnosticou
certo (leu o sample, viu o buraco), mas gravou em
`~/.english-tracker/english-log.md`, que passou a conter **só o dia 5**. O sample
ficou intacto. Combinado com o defeito 4, esse cache de uma entrada é uma bomba
armada para o próximo `push`. Ou `--file` também é destino de escrita, ou `add`
recusa `--file`.

### 6. O `add` interativo é código morto, e o texto colado é descartado (cli.py:98-114, 133-138)

`sys.stdin.read()` consome o stdin; os `input()` de `_ask_list` que vêm depois
levantam `EOFError` e devolvem lista vazia. Rodando com pipe, a saída é literal:

```
Erros (separados por ;): Palavras novas (separadas por ,):
DIA 05 — 02/09 — Tipo: D — Tema: Contar o fim de semana, no passado simples
Erros: —
```

E se o texto colado não casa o formato, ele é **jogado fora inteiro** — nem em
`raw` fica. O mecanismo que existe justamente porque o modelo falha registra uma
sessão vazia com aparência de sessão registrada. Guardar o texto colado (como
`Nota` ou bloco `raw:`) e só perguntar quando `sys.stdin.isatty()` resolve.
A instrução na tela ("termine com uma linha vazia dupla") também é falsa: só EOF
encerra.

### 7. `error_themes` muda de ordem entre execuções (analytics.py:139)

`counter.update(set(keywords(raw)))` — a ordem de iteração do `set` de strings
varia por causa da randomização de hash, e o `most_common` desempata por ordem de
inserção. Quatro execuções deram três ordens diferentes para o mesmo log; é o
único diff entre o `dashboard-exemplo.html` e o painel gerado hoje. Basta
`sorted(set(...))` e desempate por palavra.

### 8. Dia fora de 1..30 conta erro mas não conta sessão (analytics.py:63 vs 86-90)

`done_days` filtra por `plan.PLAN`, mas `top_errors`, `vocab` e `total_errors`
varrem todas as entradas. Um `DIA 45` digitado errado infla as correções sem
aparecer como sessão e sem nenhum aviso. Mesma família do defeito 2: merece ser
anomalia visível, não silêncio.

### 9. O vermelho está com dois significados (dashboard.html:98, 125)

`AGENTS.md` regra 5: "vermelho é sempre o professor: erro, buraco, anotação. Não
use vermelho para outra coisa." Mas `.cell.done.kind-T` e o swatch da legenda
pintam **dia técnico** com `--pen`. Na folha de chamada, célula vermelha cheia
(técnico feito) fica ao lado de célula vermelha cortada (buraco). Ou o dia
técnico ganha cor própria, ou a regra do AGENTS precisa ser reescrita — hoje o
código contradiz o documento.

### 10. Escopo OAuth é o Drive inteiro (config.py:23)

`auth/drive` dá leitura e escrita em tudo, para um app que mexe em um arquivo.
`drive.file` não serve (quem cria o arquivo é o professor), mas dá para reduzir o
raio: fixar o `fileId`, nunca criar mais de uma vez, e usar escopo somente
leitura no fluxo que só lê. Relevante porque o defeito 4 transforma escopo largo
em dano real.

### 11. Miudezas

- `__main__.py` executa no import (sem `if __name__ == "__main__"`): qualquer
  importação do módulo roda a CLI.
- O README lista os campos de `Report` sem `errors_per_day` e `generated_at`.
- O README diz que erros se separam por `;`: o parser também aceita `|` e `•`, e
  vocabulário também por `;`.

### 12. Erros em lista viram sessão registrada com zero erros (parser.py:103-114)

O parser só lê o valor que está **na mesma linha** do rótulo. Um LLM que escreve
markdown num arquivo do Drive quase sempre quebra em lista. Reproduzido:

| O que o professor escreve | O que o tracker registra |
|---|---|
| `Erros:` + bullets `- a` / `- b` nas linhas seguintes | sessão feita, **erros=[] vocab=[]** |
| `**Erros:** a; b` (rótulo em negrito) | sessão feita, **erros=[]** |
| `Erros:` + lista numerada `1. a` | sessão feita, **erros=[]** |

Este é o pior modo de falha do sistema inteiro, e é pior que o defeito 2. No
defeito 2 o dia desaparece — e desaparecer é visível: vira buraco vermelho na
folha de chamada, que é a verificação que justifica o projeto. Aqui o dia
**conta como feito**, a sequência avança, o painel fica limpo e o prompt do dia
seguinte sai sem os erros recorrentes. O aluno vê progresso e perde exatamente o
dado pelo qual o sistema existe. A verificação central não pega isso porque ela
compara *presença de dia*, não *presença de conteúdo*.

Duas correções, ambas pequenas:

- **Continuação de rótulo:** se a linha do rótulo vem vazia, consumir as linhas
  seguintes que começam com `-`, `*`, `•` ou `n.` até a próxima linha em branco,
  rótulo ou cabeçalho. Aceitar rótulo em negrito/itálico é uma alternância no
  padrão.
- **Entrada sem conteúdo é anomalia, não sucesso:** dia registrado com zero erros
  *e* zero vocabulário *e* nota vazia é sinal de parse falhado, não de sessão
  perfeita. Tem de aparecer em vermelho, ao lado dos buracos, com rótulo próprio
  ("registrado, mas ilegível"). É a extensão natural da decisão central: hoje ela
  desconfia da ausência do dia, e precisa desconfiar também da ausência de
  conteúdo.

### 13. Nada é reversível: não existe backup, e o `pull` sobrescreve o cache

`grep` em `english_tracker/` não encontra backup, cópia ou `.bak` em lugar
nenhum. `cmd_pull` (cli.py:161) e `drive.load` (drive.py:165) gravam
`remote.text` sobre o cache **sem nenhuma checagem**.

Com um LLM do outro lado, isso é o problema, não um detalhe. O prompt pede
*append* ("Append that summary to the Google Drive file"), mas um modelo com
ferramenta de Drive pode perfeitamente **reescrever** o arquivo com o bloco do
dia — é o comportamento mais comum quando a ferramenta é "escrever arquivo" e não
"acrescentar ao arquivo". Nesse cenário o Drive fica com uma entrada só e, no
`status` seguinte, o cache local — a única outra cópia — é sobrescrito pela
versão truncada. Não há caminho de recuperação no programa.

Correções, por ordem de custo: (a) o `pull`/`load` compara os dias do remoto com
os do cache e **avisa em vermelho** quando o remoto tem menos dias, em vez de
sobrescrever calado; (b) toda escrita no cache guarda a versão anterior em
`~/.english-tracker/backups/<timestamp>`; (c) o `doctor` mostra a contagem de
dias das duas pontas. Vale registrar no README que o Drive tem histórico de
revisões pela UI — hoje é a única rede de proteção e ela não está documentada.

### 14. O placeholder do prompt entra como erro real

`Erros: <mistake>; <mistake>` é aceito e vira dois erros chamados `<mistake>`,
que sobem para `top_errors`, contam em `total_errors` e são colados no prompt do
dia seguinte como erro a treinar. Mesma origem do defeito 3: o molde do prompt é
copiável ao pé da letra. Descartar valor entre `<`/`>` no parser custa uma linha.

---

## Ideias de melhoria

**Fazer o calendário existir.** `Settings.start_date` e `rest_weekdays` estão em
`config.py` sem consumidor, e o README já aponta o caminho. Com data real dá para
separar duas coisas que hoje são a mesma: *buraco* (sessão que devia estar no log
e não está) e *atraso* (dia que ainda não chegou). O "você pulou terça" e a
sequência por dia de calendário vêm de graça depois disso.

**Um comando `doctor`.** A desconfiança do projeto para no parser: ela não cobre
a fronteira com o Drive, que é onde o dado se perde. Um `english-tracker doctor`
que mostre credencial encontrada, arquivo resolvido (nome, id, mimeType, data de
modificação), quantos candidatos casaram a busca e quais linhas do log ficaram
ilegíveis põe a decisão central no lugar onde ela ainda não está.

**`push` que funde em vez de sobrescrever.** É o defeito 4 visto como recurso: o
log passa a ser append-only por construção, e aí o `add` offline deixa de ser
arriscado. Backup do remoto em `~/.english-tracker/backups/` antes de cada
escrita.

**Ensinar o formato por exemplo, não por molde.** Em vez do gabarito com
`<mistake>` e `DD/MM`, embutir no prompt a **última entrada real do log** como
exemplo a imitar, com a data do dia já resolvida. Modelo copia exemplo melhor do
que preenche placeholder — e isso ataca a causa do defeito 3 pelo lado do prompt,
não só pelo lado do parser.

**Comando `week`.** Já está na lista do README e é barato: `_history` mais um
recorte de sete dias, com os erros que voltaram na semana, pronto para colar num
chat de texto e pedir análise escrita (que é justamente o que o Gemini Live não
faz bem).

**Flashcards.** `review_deck()` é o começo; um `--csv` no formato do Anki fecha o
ciclo de vocabulário sem construir nada novo.

**Onde os testes não chegam.** A suíte cobre bem `parser.py` e `analytics.py` —
e o README está certo em dizer que é ali que dói. Mas os defeitos 2, 4, 5 e 6 são
todos em `cli.py`/`drive.py`, que não têm um teste. Se for escrever um só, o de
maior retorno é o do defeito 2: cabeçalho inválido não pode corromper a entrada
anterior.
