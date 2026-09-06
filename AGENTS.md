# Contexto para agentes de IA

Leia o `README.md` inteiro antes de mexer em qualquer coisa. Ele tem o porquê do
projeto, o contrato de dados e as decisões que não devem ser revertidas.

O essencial, se você só puder ler uma coisa:

1. **O sistema nunca assume que uma sessão foi registrada — nem que o conteúdo
   dela foi entendido.** Um modelo diz que salvou no Drive e não salvou; e escreve
   num formato que o parser pode não ler. A verificação tem três desfechos: feito,
   **buraco** (cortado a vermelho) e **registrado mas ilegível** (borda tracejada
   vermelha, `status = "sem-conteudo"`), que não conta como feito. Não remova
   nenhum dos três nem os torne silenciosos.
2. **O parser é a parte frágil, e quem escreve para ele é outra IA.** Ele absorve
   variação de *formatação* em silêncio (bullet, negrito, cabeçalho markdown, tipo
   por extenso, placeholder do molde) e **nunca** absorve variação de *estrutura*.
   Rode `python -m pytest tests/ -q` (48 testes) depois de qualquer mudança em
   `parser.py` ou `analytics.py` — `tests/test_formatos_do_modelo.py` é o arquivo
   que existe só para isso.
3. **`sample/english-log.md` tem o dia 5 faltando de propósito.** É o caso de
   teste da detecção de buraco. Não conserte.
4. **Amplie o parser, nunca o substitua.** Entradas antigas precisam continuar
   casando ou o histórico se perde.
5. **O painel é uma folha corrigida a caneta vermelha.** Vermelho (`--pen`) é
   sempre o professor: erro, buraco, dia ilegível, anotação. Não use vermelho para
   outra coisa — o dia técnico tem a caneta azul do aluno (`--tech`) justamente
   por isso.
6. **Escrever no Drive é a operação perigosa.** `push` funde (não substitui),
   exige alvo por nome exato ou id fixado, recusa arquivo que não parece um
   english-log e guarda backup antes. `--force` é a saída consciente disso. Não
   simplifique isso de volta para um `files().update` direto.

Rodar sem configurar nada:

```bash
pip install -e . && python -m pytest tests/ -q
english-tracker --file sample/english-log.md --offline status
english-tracker --file sample/english-log.md --offline report --no-open
```
