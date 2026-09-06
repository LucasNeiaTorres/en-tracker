# Ideias para o english-tracker — o projeto, não o código

Escrito depois de ler o README, rodar o sistema e corrigir os 14 defeitos. Aqui
não se fala de bug: fala-se do **método de estudo**, do **loop de uso** e dos
**riscos do projeto**. Ordenado por retorno, não por dificuldade.

---

## 1. O furo operacional: o prompt nasce no notebook e a sessão acontece no celular

> **Resolvido (2026-09-02).** Três camadas: o `serve` tornou o painel interativo,
> o botão **Enviar para o WhatsApp** leva o prompt do dia ao celular, e o
> **pacote da semana** (`prompt --pacote 7 --para-o-drive`, página `/semana`,
> timer do systemd em `contrib/`) tira o notebook do caminho diário — o prompt de
> um dia só muda quando o log muda, então a semana inteira pode ser preparada
> antes. O que segue abaixo era o diagnóstico, que monta um link `wa.me` com o prompt codificado e abre o
> WhatsApp Web com o texto digitado. Restou um clique (o "enviar"), na máquina
> onde você já está — em vez de um copiar-e-colar de 3 mil caracteres entre
> dispositivos. O que segue abaixo continua valendo como alternativa e como
> caminho para eliminar o clique.

O `english-tracker prompt` imprime no terminal do Linux. O Gemini Live roda no
telefone. Todo dia, para estudar, é preciso levar um texto de 2 mil caracteres de
uma máquina para a outra — e nenhum hábito diário sobrevive a um passo de
copiar-e-colar entre dispositivos.

Isso não é inconveniência, é a causa de morte mais provável do projeto. Vale
mais do que qualquer coisa que ainda se possa fazer no parser.

**Duas rotas, as duas usando o que já está autorizado.** O prompt tem ~3.100
caracteres e 34 linhas: é um arquivo de texto pequeno.

1. **Arquivo no Drive** — menor esforço. `drive.push` e a autenticação já
   existem; um `prompt --para-o-drive` grava `english-prompt.md` ao lado do log,
   sobrescrevendo a cada dia. O app do Drive no telefone abre e copia. Nenhum
   escopo novo, nenhuma autorização nova.
2. **Tarefa no Google Tasks** — resolve dois problemas de uma vez. A API aceita
   conta pessoal, o campo de notas cabe o prompt, e tarefa tem **hora**: além de
   transportar, ela **avisa** no celular que é hora de estudar. Isso ataca junto
   o risco de "horário não ancorado" da tabela do §10, que é a causa clássica de
   morte de hábito diário. Custo: um escopo a mais no mesmo app em modo de teste.

**Enquanto não existir:** cole o prompt numa nota do Google Keep e edite essa
mesma nota todo dia, à mão. ⚠️ E note que essa parte **não tem como ser
automatizada**: a API do Keep expõe `create`, `get`, `list` e `delete`, e **não
tem `update`** — nenhum programa edita nota existente. Por isso as rotas acima
são Drive e Tasks, não Keep.

## 2. O painel mede atividade, não progresso

> **Feito em parte (2026-09-02).** A mortalidade de erro existe: a agenda de
> revisão espaçada dá a cada item uma caixa, e quem sobrevive a todos os
> intervalos entra na seção **Dominados** do painel. Continua pendente o **tipo
> do erro** (pronúncia / gramática / vocabulário / travamento) e a **gravação
> mensal**, que não é software.

Sessões, sequência, correções, palavras: tudo isso mede **volume**. O número de
correções pode até **subir** com a melhora, porque quem fala mais e sobre assunto
mais difícil erra mais. Hoje não há nenhum número no painel que responda "meu
inglês melhorou?".

Três instrumentos baratos, em ordem de valor:

**Mortalidade de erro.** O dado já está no `ErrorGroup.days`: falta usá-lo ao
contrário. Em vez de só "quantas vezes esse erro voltou", mostrar **há quantos
dias ele não aparece**. Erro que sumiu por 10 dias está morto; erro que voltou
ontem é o trabalho de verdade. Uma seção "erros que morreram" é a única coisa no
painel que seria evidência de progresso — e o contador atual, sozinho, premia
justamente a repetição.

**Tipo do erro.** Pronúncia, gramática, falta de vocabulário e travamento são
quatro problemas diferentes, com quatro remédios diferentes, e hoje entram todos
no mesmo balde. Pedir ao professor um marcador (`[pron]`, `[gram]`, `[vocab]`,
`[travei]`) e agrupar por ele diz **em que** o inglês falha — o
`error_themes`, que conta palavra dentro do texto do erro, é um proxy fraco disso.

**Gravação mensal.** O dia 30 já pede três minutos de fala livre para comparar
com o dia 1. Faça isso todo mês e **guarde o áudio**. É a única prova que não
depende do que um modelo escreveu sobre você.

## 3. Vocabulário exposto não é vocabulário adquirido

> **Feito (2026-09-02).** O contrato ganhou a linha `Reusou:`, e ela alimenta a
> agenda: palavra reusada avança de intervalo, palavra nunca reusada volta a ser
> cobrada. No log de teste, "to roll out" ficou 9 dias atrasada enquanto
> "backoff", reusada duas vezes, só voltava em 6.

O painel conta as palavras que o **professor deu**. O que importa é quais delas o
**aluno usou depois, sozinho**. São coisas muito diferentes: a primeira mede
exposição, a segunda mede aquisição.

**O que fazer:** uma linha a mais no contrato de dados — `Reusou: backoff, to
roll out` — que o professor preenche quando o aluno emprega, sem ser mandado, uma
palavra de sessão anterior. O painel passa a ter duas colunas: recebidas e
incorporadas. É a métrica mais honesta que este sistema pode ter por uma linha de
texto.

## 4. A escrita está no objetivo e fora do plano

A primeira frase do README diz "fala e escreve mal". O plano tem 30 dias de voz e
zero de escrita. E escrever é a metade que:

- rende mais rápido, porque é assíncrona e cabe em 10 minutos;
- um modelo de texto corrige **melhor** que um de voz (é o contrário da
  pronúncia, que foi o motivo de escolher o Gemini Live);
- aparece no trabalho dele todo dia — `CHANGELOG`, descrição de MR, comentário de
  chamado, e-mail.

**O que fazer:** um dia por semana (ou o dia `R`, que hoje é revisão pura) vira
escrita: 150 palavras sobre algo técnico que ele fez na semana, corrigido em
texto, com os erros entrando **no mesmo log**. O painel não precisa saber que
foram escritos; erro é erro. Custo: dez minutos por semana e um bloco novo em
`MODE_BLOCKS`.

## 5. Os temas técnicos deveriam vir do trabalho real

Os dias `T` pedem para explicar injeção de dependência, Kafka, Kubernetes — bom
material genérico de entrevista. Mas o inglês de maior valor imediato é o **do
próprio domínio de trabalho**: explicar por que uma mudança num módulo
compartilhado afeta os outros serviços que dependem dele, narrar uma análise de
causa-raiz, defender uma decisão de contrato de integração.

Isso muda a natureza do estudo: em vez de treinar para uma entrevista
hipotética, treina-se exatamente o que se teria de dizer numa reunião real, com o
vocabulário que se vai reusar na semana.

**O que fazer:** um arquivo `temas.md` onde se anota, durante a semana, o assunto
que apareceu no trabalho — e um `prompt --tema "<assunto>"` para sobrepor o tema
do plano. Versão ambiciosa: puxar o título direto do rastreador de tarefas que
você já usa. O ganho não é técnico, é de aderência: estudar o que serve hoje é o
que faz voltar amanhã.

## 6. O dia 31 é um precipício

O plano tem forma de desafio: 30 dias, balanço final, fim. Isso é ótimo para
começar e péssimo para continuar — e fluência em fala não responde a 30 dias,
responde a meses. No dia 31 o `status` vai dizer "Plano concluído" e não haverá
próximo passo.

**O que fazer:** tratar os 30 dias como **temporada**, não como curso. A
temporada 2 se monta sozinha a partir do que a temporada 1 produziu: os erros
ainda vivos viram os dias `R`, os temas do trabalho viram os dias `T`, e o painel
passa a contar dias acumulados em vez de `n/30`. Em código é pouco — `plan.py`
ganha um número de ciclo. Em resultado é a diferença entre um desafio cumprido e
um hábito.

## 7. Fora da sessão, não existe retenção

> **Feito (2026-09-02).** Existe o `english-tracker deck` e a seção "Revisão de
> hoje" no painel: repetição espaçada de dois minutos, com intervalos de 1, 3, 7,
> 16 e 30 dias de calendário, derivada do próprio log. A revisão deixou de ser
> um tipo de dia (17% do plano, quatro recuperações em trinta dias) e virou
> camada diária.

O ciclo hoje é: falar, ser corrigido, esquecer. Quinze minutos de voz sem nenhuma
recuperação depois perde a maior parte — e o argumento do plano ("erro com carga
emocional gruda") é verdadeiro, mas resolve a **codificação**, não a
**recuperação**.

**O que fazer:** o `review_deck()` já existe no `analytics.py` e ninguém usa. Um
`english-tracker deck` que imprima cinco frases — não palavras, **frases** — a
serem ditas em voz alta, montadas a partir dos erros **ainda vivos**, dá dois
minutos de recuperação espaçada por dia, sem app, sem tela, no café. É o melhor
retorno por linha de código do projeto todo.

## 8. Quando o professor falha, registrar tem de custar 15 segundos

O `add` pede o resumo colado no formato do contrato. Às onze da noite, depois de
uma sessão que não foi salva, isso não vai acontecer: ele vai fechar o terminal e
o dia vira buraco — buraco falso, que suja justamente a métrica que o sistema
existe para proteger.

**O que fazer:** duas saídas, ambas honestas.

- `add --erros "esqueci o -s; travei em prejudicar"` direto no argumento, sem
  stdin e sem formato.
- `add --sem-detalhe`, que registra "fiz a sessão, não tenho o resumo". Não é o
  sistema **presumindo** que a sessão houve — é o aluno **afirmando**, o que é
  outra coisa. Vira um quarto estado na folha de chamada: feito, buraco,
  ilegível, e **feito sem detalhe**.

## 9. Duas linhas no prompt que aumentam a obediência do professor

O README já sabe que sessão longa faz o modelo relaxar as regras. Dois reforços
custam duas linhas:

- **Pedir que ele declare as regras antes de começar**, em uma linha cada. Modelo
  que reafirma a restrição cumpre mais a restrição.
- **Auto-checagem no meio**: "no minuto 8, diga quantas correções você já fez".
  Se ele disser "duas", ele mesmo percebe que afrouxou.

E uma mudança de registro ao longo do plano: o sarcasmo é excelente por três dias
e cansa na terceira semana. As semanas 3 e 4 pedem menos palhaçada e mais
exigência — o `MODE_BLOCKS` já é por tipo de dia; podia ser por semana também.

## 9-A. O escopo do Drive tem uma alternativa, com um porém sério

Hoje o programa pede `drive.readonly` para ler e `drive` para escrever. A
documentação do Google classifica os dois como **restritos**: eles "require
restricted scope OAuth App Verification", o app tem de se encaixar numa das
categorias elegíveis (backup/sync, produtividade e educação, relatório e
segurança), e há avaliação de segurança por terceiro se os dados forem
armazenados ou transmitidos.

Publicar o app, portanto, **não é preencher formulário**: exige domínio próprio
verificado, política de privacidade e termos hospedados, vídeo de demonstração
e revisão manual — para um programa de um único usuário. O caminho realista é
ficar "Em teste" e reautorizar a cada 7 dias (30 segundos, e o programa refaz o
fluxo sozinho).

Existe um escopo que evita tudo isso: **`drive.file`**, que é não-sensível e dá
acesso apenas aos arquivos que **o próprio app criou**. Com ele, publicar o app
não exige verificação, e a autorização não expira em uma semana.

**O porém, que é grave:** com `drive.file` o programa fica **cego** para
qualquer arquivo que ele não tenha criado. Se o professor, em vez de acrescentar
ao arquivo, criar um `english-log` novo — coisa que um modelo com ferramenta de
escrita faz sem avisar —, o tracker não vê nada e não consegue nem diagnosticar:
diria "nenhum arquivo parecido no seu Drive" enquanto o texto existe, ali, em
outro arquivo. Trocaria uma fricção semanal por uma cegueira silenciosa, e
cegueira silenciosa é exatamente o que este projeto foi feito para não ter.

**Mas a cegueira tem antídoto, e isso muda o cálculo.** O app não pode *ver* o
arquivo que não criou, e não pode ser calado a respeito: se o arquivo que ele
conhece não recebe conteúdo novo há N dias, isso é um aviso —
"nada novo há 3 dias; confira se o professor não criou outro arquivo". Cegueira
silenciosa é inaceitável neste projeto; **suspeita ruidosa** é exatamente o
princípio dele. Com esse aviso, `drive.file` deixa de ser um risco escondido e
passa a ser um risco declarado.

**Recomendação:** manter `drive.readonly`/`drive` enquanto o sistema estiver
sendo posto de pé, porque funciona hoje e o custo é um clique por semana. Se a
re-autorização semanal se mostrar a fricção que derruba o hábito, migrar para
`drive.file` — trocando o escopo, deixando o `push` criar o arquivo, e
implementando o aviso de estagnação **junto**, não depois.

## 10. Riscos do projeto (não do código)

| Risco | Por que importa | Mitigação |
|---|---|---|
| O plano é hostage de um produto | Gemini Live pode mudar comportamento, cota ou preço | O prompt é portável e o log é texto puro. **Mantenha assim**: nada de acoplar o tracker ao Gemini |
| Autorização do Google expira em 7 dias | App "Em teste" + escopo restrito. Um passo manual por semana num hábito diário | Publicar o app (botão na página **Público-alvo**), se o Google permitir sem verificação — ver §9-A |
| Horário não ancorado | 15 min/dia sem gatilho fixo morre na semana 2 | Prender a um hábito que já existe: café, deslocamento, depois da daily |
| Sem custo social | Sequência num terminal é fácil de abandonar | Um parágrafo por semana enviado a alguém (colega, esposa, gestor). Custo de faltar deixa de ser zero |
| Auto-avaliação por modelo | O professor elogia com facilidade | A gravação mensal é o contrapeso. Áudio não bajula |
| Critério de sucesso indefinido | "falar melhor" não é falsificável, então nunca se conclui | Ver abaixo |

## 11. Falta um critério de sucesso — e ele é do projeto, não do software

O sistema mede tudo, menos se o objetivo foi atingido, porque o objetivo não está
escrito em nenhum lugar. Sem isso não há como parar, nem como saber que valeu.

Escolha **um** alvo verificável, com data, e ponha no painel:

- "em 60 dias, uma entrevista técnica de 20 minutos em inglês sem recorrer ao
  português";
- ou "descrever um MR real em inglês e ter a descrição revisada por alguém";
- ou "uma reunião de 30 minutos com cliente estrangeiro sem travar".

O primeiro é o mais fácil de arbitrar (o próprio dia 29 do plano já é isso) e o
segundo é o que tem uso imediato no trabalho.

---

## Se for pegar só três

| Ideia | Custo | Por que esta |
|---|---|---|
| **Prompt no Drive** (§1) | 1 função, plumbing já existe | Remove o único passo diário que depende de força de vontade |
| **Mortalidade de erro** (§2) | ~20 linhas em `analytics.py` + uma seção no painel | É a única coisa que transforma o painel em medida de progresso |
| **`deck` de dois minutos** (§7) | `review_deck()` já está escrito | Retenção é onde o método está mais frágil, e é a mudança mais barata |

As três juntas mudam o projeto de "registro de um desafio de 30 dias" para
"instrumento de um hábito com evidência de progresso" — sem tocar na decisão de
arquitetura que sustenta ele.
