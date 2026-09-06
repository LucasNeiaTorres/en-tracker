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

Se o projeto não estiver em `~/Downloads/english-tracker`, ajuste os dois
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

Ele serve o log que já está no disco. Quem coloca o log lá é o outro computador
(um `rsync`, o Syncthing, um cliente de Drive — o que você preferir). E como o
painel também vai `--somente-leitura`, nada que se faça nele muda coisa alguma.

    notebook  ──(sessões, add, push)──>  Drive  ──(sync)──>  PC sempre ligado
                                                              └─ painel, leitura

### Instalação

```bash
git clone git@github.com:SEU-USUARIO/english-tracker.git ~/english-tracker
cd ~/english-tracker
python3 -m venv .venv && ./.venv/bin/pip install -e .

printf 'uma-senha-longa' > ~/.english-tracker/senha
chmod 600 ~/.english-tracker/senha

mkdir -p ~/.config/systemd/user
cp contrib/english-tracker-painel.service   ~/.config/systemd/user/
cp contrib/english-tracker-atualiza.service ~/.config/systemd/user/
cp contrib/english-tracker-atualiza.timer   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now english-tracker-painel.service
systemctl --user enable --now english-tracker-atualiza.timer

# para os serviços continuarem rodando sem você logado na máquina
sudo loginctl enable-linger $USER
```

O timer verifica o GitHub a cada 15 minutos, faz `git pull --ff-only`, reinstala
e reinicia o painel. Se você não empurrou nada, o `pull` não faz nada e o painel
nem é tocado.

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
