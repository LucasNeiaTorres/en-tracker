# contrib — automação opcional

## Publicar o pacote de prompts sozinho

O objetivo: **não precisar do notebook todo dia.** O timer roda de hora em hora
enquanto a máquina estiver ligada, puxa o log do Drive e republica lá o arquivo
`english-prompt.md` com os próximos sete dias. No celular, você abre o Drive e
copia o bloco do dia.

```bash
mkdir -p ~/.config/systemd/user
cp contrib/english-tracker-pacote.service ~/.config/systemd/user/
cp contrib/english-tracker-pacote.timer   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now english-tracker-pacote.timer

systemctl --user list-timers english-tracker-pacote.timer   # quando roda de novo
journalctl --user -u english-tracker-pacote.service -n 30   # o que aconteceu
```

Se o projeto não estiver em `~/pessoal/english-tracker`, ajuste os dois
`ExecStart` do `.service`.

### O que vai falhar, e quando

**A autorização do Google expira a cada 7 dias** enquanto o app estiver com
status "Em teste" — é regra do Google, não do programa. Quando isso acontecer, o
`pull` do timer falha em silêncio (o `-` no `ExecStart` faz o pacote ser gerado
do cache local mesmo assim) e você precisa rodar `english-tracker pull` uma vez,
à mão, para reautorizar no navegador.

Sintoma: o `english-prompt.md` no Drive para de refletir as sessões novas.
Diagnóstico: `journalctl --user -u english-tracker-pacote.service | grep -i cred`.


---

## Rodar o painel em outro computador (o "sempre ligado")

O deploy aqui é **puxado, não empurrado**. O GitHub não alcança uma máquina atrás
de NAT, e abrir porta para ele seria trocar um problema pequeno por um grande:
quem puxa é o próprio computador, de tempos em tempos.

### A forma da coisa

O computador sempre ligado puxa o log **direto do Drive**, com **conta de
serviço** — que não pede navegador e não expira em 7 dias, e é o que torna
automação desatendida possível. Um timer roda `pull` a cada 15 minutos; o painel
serve o que está no disco.

O painel do servidor é **completo**, com os botões: a senha é a tranca. Isso o
torna um segundo escritor, e a operação perigosa disso — apagar dia, que
**substitui** o arquivo do Drive em vez de fundir — passou a partir do conteúdo
fresco do Drive, não do cache local. Sem isso, apagar um dia numa máquina com
cache de 15 minutos levaria junto qualquer sessão chegada no intervalo.

⚠️ Com botões, a senha deixou de ser conforto: ela é o único obstáculo entre a
sua rede e o seu log. Use uma senha longa, e lembre que ela **viaja em HTTP puro**
na LAN. Para sair de casa, `tailscale serve` põe HTTPS na frente.

    notebook ──(add, push, publicar a semana)──> Drive <──(pull a cada 15min)── servidor
                                                              │
                                                              └─> painel, leitura, na sua rede

Antes isto era um `rsync` do notebook para o servidor, o que amarrava o painel a
o notebook estar ligado. Com a conta de serviço, o servidor se vira sozinho.

---

## Passo a passo

### No PC que vai ficar ligado

**1. Requisitos:** Linux com systemd, Python 3.10+, git. Confirme:

```bash
python3 --version && git --version && systemctl --user --version | head -1
```

**2. Clonar e instalar:**

```bash
mkdir -p ~/pessoal && cd ~/pessoal
git clone https://github.com/LucasNeiaTorres/en-tracker.git english-tracker
cd english-tracker
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"          # o [dev] traz o pytest
./.venv/bin/python -m pytest tests/ -q       # esperado: 151 passed
```

**3a. A chave da conta de serviço.** No navegador **desta máquina**, console do
Google Cloud → sua conta de serviço → *Chaves* → *Adicionar chave* → *Criar
nova* → JSON. Uma chave **por máquina**, para poder revogar uma sem derrubar a
outra:

```bash
mkdir -p ~/.english-tracker
mv ~/Downloads/*-*.json ~/.english-tracker/service-account.json
chmod 600 ~/.english-tracker/service-account.json
```

Os arquivos `english-log.md` e `english-prompt.md` já devem estar compartilhados
com o e-mail da conta (feito uma vez, vale para todas as chaves).

**3b. A senha do painel** (ela é a tranca do acesso pela rede):

```bash
mkdir -p ~/.english-tracker
printf 'uma-senha-longa-e-sua' > ~/.english-tracker/senha
chmod 600 ~/.english-tracker/senha
```

> ⚠️ **Se você seguiu uma versão anterior deste guia**, ela mandava gerar o
> exemplo fictício em `~/.english-tracker/english-log.md`. Apague antes de
> continuar, senão o painel mostra 11 sessões que nunca existiram:
> `rm ~/.english-tracker/english-log.md`

**4. Puxar o log de verdade** (é também o teste da chave — tem de funcionar sem
abrir navegador nenhum):

```bash
./.venv/bin/english-tracker pull && ./.venv/bin/english-tracker status
```

**5. Subir à mão primeiro, para ver funcionando:**

```bash
./.venv/bin/english-tracker serve --host 0.0.0.0 --sem-abrir \
    --somente-leitura --com-senha
```

Deve imprimir o aviso de que está ouvindo fora da máquina e que o modo leitura
está ligado. Em outro terminal, `curl -u x:SUA-SENHA http://127.0.0.1:8765/ | head -3`.
Depois Ctrl-C.

**6. Instalar como serviço, para subir sozinho:**

```bash
mkdir -p ~/.config/systemd/user
cp contrib/english-tracker-painel.service   ~/.config/systemd/user/
cp contrib/english-tracker-atualiza.service ~/.config/systemd/user/
cp contrib/english-tracker-atualiza.timer   ~/.config/systemd/user/
cp contrib/english-tracker-sync.service     ~/.config/systemd/user/
cp contrib/english-tracker-sync.timer       ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now english-tracker-painel.service
systemctl --user enable --now english-tracker-atualiza.timer
systemctl --user enable --now english-tracker-sync.timer

# sem isto, os serviços morrem quando você desloga
sudo loginctl enable-linger $USER

systemctl --user status english-tracker-painel.service --no-pager | head -8
```

**7. Deixar a porta passar no firewall** (só se houver firewall ativo):

```bash
sudo ufw allow from 192.168.0.0/16 to any port 8765 proto tcp   # ajuste sua faixa
hostname -I                                                      # anote o IP
```

De outro computador da mesma rede: `http://IP-DESSE-PC:8765` — o IP que o próprio
serviço imprime na partida (`systemctl --user status ... | tail -6`). O navegador
pede usuário e senha num diálogo dele, **antes** da página: usuário pode ser
qualquer coisa, a senha é a do passo 3.

Se você for acessar por um **nome** em vez de IP (o nome da máquina no Tailscale,
por exemplo), acrescente-o à unidade: `--host-extra nome.seu-tailnet.ts.net`. O
painel confere o cabeçalho `Host` e recusa o que não conhece — é a defesa contra
um site externo apontar um domínio dele para o seu IP privado. Os IPs e o nome
desta máquina já entram sozinhos.

### No notebook

Nada a fazer: ele continua sendo onde você registra sessão, revisa os cartões e
publica a semana. O servidor pega tudo pelo Drive.

Se você tinha acrescentado a linha do `rsync` ao
`english-tracker-pacote.service`, pode removê-la — ela não é mais necessária.

---

## O que esperar, e o que não esperar

O painel do PC sempre ligado é **leitura**: folha de chamada, revisão,
flashcards, a semana. Os botões de agir não aparecem, e as rotas de escrita
respondem 403 mesmo se alguém chamar direto.

Registrar sessão, publicar a semana e renovar a autorização do Google continuam
no notebook — é lá que o log e os tokens moram.

O log no servidor fica no máximo 15 minutos atrás do Drive, **independente do
notebook**. Se o professor escrever a sessão hoje e você não abrir o notebook por
uma semana, o painel do servidor já mostra a sessão — porque ele lê do Drive, não
do notebook.

Tudo pode ser feito dos dois lados: registrar sessão, apagar dia, preencher verso,
publicar a semana. As escritas comuns são por **fusão** (nada se perde se as duas
máquinas agirem), e a única que substitui — apagar dia — confere o Drive antes.

### Para abrir de fora da sua rede

Use **Tailscale** (grátis, uso pessoal): instale nas duas pontas, e o endereço
passa a ser o nome da máquina no seu tailnet, sem expor nada na internet. Se
precisar mesmo de URL pública, veja a seção "Ver o painel de outro computador"
do `README.md` — e nunca sem autenticação na frente.

---

## Diagnóstico rápido

| Sintoma | Onde olhar |
|---|---|
| Painel não sobe | `journalctl --user -u english-tracker-painel.service -n 30` |
| "não há senha configurada" | passo 3: o arquivo `~/.english-tracker/senha` |
| Não abre de outro PC | firewall (passo 7) e se o `--host 0.0.0.0` está no serviço |
| Painel mostra dados velhos | o `rsync` do passo 8; veja o journal no notebook |
| Serviço morre ao deslogar | faltou `loginctl enable-linger` |

### CI/CD com runner próprio, se você quiser o deploy imediato

O `git pull` de 15 em 15 minutos é o suficiente para um projeto de uma pessoa.
Se quiser que o deploy aconteça no instante do push, instale um **self-hosted
runner** do GitHub Actions nesse computador: ele conversa com o GitHub por
conexão de saída, então funciona atrás de NAT do mesmo jeito.

🚫 **Não faça isso com o repositório público.** Num repositório público qualquer
pessoa abre um pull request, e o runner executaria o código dela na sua máquina —
com o seu usuário, no seu disco, na sua rede. É um dos poucos erros de
configuração que entregam a máquina inteira.

Com repositório público, use o `git pull` do timer acima: ele é de saída, não
executa nada de terceiros, e quinze minutos de atraso não fazem diferença aqui.
