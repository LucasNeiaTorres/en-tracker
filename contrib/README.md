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

O computador sempre ligado roda o painel **`--offline`**: ele nunca fala com o
Google. Isso resolve o problema que derruba qualquer automação nesta pilha — a
autorização do Google expira a cada 7 dias e precisa de um navegador para
renovar. Sem falar com o Google, não há o que expirar.

Ele serve o log que está no disco. Quem coloca o log lá é o notebook, que é onde
a autorização mora. E como o painel também vai `--somente-leitura`, nada que se
faça nele muda coisa alguma.

    notebook ──(pull do Drive, add, push)──> Drive
       │
       └──(rsync do log)──> PC sempre ligado ──> painel, leitura, na sua rede

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

**3. A senha do painel** (ela é a tranca do acesso pela rede):

```bash
mkdir -p ~/.english-tracker
printf 'uma-senha-longa-e-sua' > ~/.english-tracker/senha
chmod 600 ~/.english-tracker/senha
```

**4. Um log inicial, só para o painel ter o que mostrar** (o de verdade chega no
passo 8):

```bash
./.venv/bin/python sample/gerar-exemplo.py > ~/.english-tracker/english-log.md
```

**5. Subir à mão primeiro, para ver funcionando:**

```bash
./.venv/bin/english-tracker --offline serve --host 0.0.0.0 --sem-abrir \
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
systemctl --user daemon-reload
systemctl --user enable --now english-tracker-painel.service
systemctl --user enable --now english-tracker-atualiza.timer

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

**8. Mandar o log para lá** depois de cada sincronização com o Drive. Primeiro,
acesso por SSH sem senha:

```bash
# a chave já existe se você gerou uma antes; senão:
ssh-keygen -t ed25519 -C "notebook" -f ~/.ssh/id_ed25519 -N ""
ssh-copy-id USUARIO@IP-DO-PC
ssh USUARIO@IP-DO-PC 'echo ok'
```

Depois acrescente a cópia ao serviço que já puxa o Drive de hora em hora, no fim
do `~/.config/systemd/user/english-tracker-pacote.service`:

```ini
ExecStart=-/usr/bin/rsync -a %h/.english-tracker/english-log.md USUARIO@IP-DO-PC:.english-tracker/english-log.md
```

O `-` na frente faz o systemd ignorar a falha: o PC pode estar desligado, e isso
não deve derrubar o resto. Depois:

```bash
systemctl --user daemon-reload
systemctl --user start english-tracker-pacote.service
journalctl --user -u english-tracker-pacote.service -n 20 --no-pager
```

---

## O que esperar, e o que não esperar

O painel do PC sempre ligado é **leitura**: folha de chamada, revisão,
flashcards, a semana. Os botões de agir não aparecem, e as rotas de escrita
respondem 403 mesmo se alguém chamar direto.

Registrar sessão, publicar a semana e renovar a autorização do Google continuam
no notebook — é lá que o log e os tokens moram.

O log no PC estará tão atualizado quanto o último `rsync`, que acontece de hora
em hora **com o notebook ligado**. Se você ficar dias sem abrir o notebook, o
painel remoto mostra o estado daquele dia. Para a sessão diária isso não faz
diferença: o que você precisa fora de casa é o `english-prompt.md` no Drive, que
não depende de nenhuma das duas máquinas.

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
