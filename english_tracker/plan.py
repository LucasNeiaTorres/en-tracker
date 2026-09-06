"""O plano de 30 dias, como dado estruturado.

Tipos:
    D = dia a dia      T = técnico (trilha)
    N = notícia        R = revisão
"""

from __future__ import annotations

from dataclasses import dataclass

TYPE_LABELS = {
    "D": "Dia a dia",
    "T": "Técnico",
    "N": "Notícia",
    "R": "Revisão",
}

TRACKS = {
    1: (
        "Spring a fundo",
        "IoC e injeção de dependência, ciclo de vida do bean, auto-configuration "
        "do Boot, Spring Data JPA, tratamento de exceções, profiles",
    ),
    2: (
        "Mensageria",
        "Kafka vs RabbitMQ, producer/consumer, tópicos e partições, consumer group, "
        "idempotência, dead letter queue, garantias de entrega",
    ),
    3: (
        "Testes e CI/CD",
        "JUnit 5, Mockito, unitário vs integração, Testcontainers, cobertura, "
        "pipeline no GitHub Actions, estratégias de release",
    ),
    4: (
        "AWS e Kubernetes",
        "EC2, S3, RDS, SQS, IAM básico, container vs VM, pod, deployment, service, "
        "ingress, ConfigMap/Secret, health checks, observabilidade",
    ),
}


@dataclass(frozen=True)
class PlanDay:
    day: int
    kind: str
    topic: str

    @property
    def week(self) -> int:
        return min((self.day - 1) // 7 + 1, 4)

    @property
    def kind_label(self) -> str:
        return TYPE_LABELS.get(self.kind, self.kind)

    @property
    def track(self) -> str | None:
        if self.kind != "T":
            return None
        return TRACKS.get(self.week, ("", ""))[0]


_RAW: list[tuple[int, str, str]] = [
    (1, "D", "Apresentar-se: rotina, onde mora, o que faz"),
    (2, "T", "Explicar injeção de dependência e por que o Spring usa IoC"),
    (3, "D", "Pedir comida e resolver um problema com o delivery"),
    (4, "T", "Auto-configuration do Spring Boot e o que são starters"),
    (5, "D", "Contar o fim de semana, no passado simples"),
    (6, "N", "Notícia de tecnologia da semana: reagir e opinar"),
    (7, "R", "Revisão: reler o log e refazer os 10 erros mais comuns"),
    (8, "D", "Dar direções, marcar horário, resolver algo por telefone"),
    (9, "T", "Kafka vs RabbitMQ: quando usar cada um"),
    (10, "D", "Viagem: check-in, hotel, problema no voo"),
    (11, "T", "Idempotência e dead letter queue: por que importam"),
    (12, "D", "Contar um filme ou série que assistiu"),
    (13, "N", "Notícia da semana: discordar do autor de propósito"),
    (14, "R", "Revisão semanal"),
    (15, "D", "Debater um assunto leve: trabalho remoto, redes sociais"),
    (16, "T", "Teste unitário vs integração: onde está o limite"),
    (17, "D", "Reclamar de um serviço ruim e exigir solução"),
    (18, "T", "Descrever um pipeline de CI/CD do commit ao deploy"),
    (19, "D", "Planos futuros: carreira, objetivos, mudança"),
    (20, "N", "Notícia da semana: comparar com sua experiência real"),
    (21, "R", "Revisão semanal"),
    (22, "D", "Small talk: puxar assunto num evento"),
    (23, "T", "Explicar sua arquitetura na AWS: quais serviços e por quê"),
    (24, "D", "Resolver um mal-entendido com alguém"),
    (25, "T", "Kubernetes: pod, deployment e service para um junior"),
    (26, "D", "Contar uma história engraçada que aconteceu com você"),
    (27, "N", "Notícia da semana: defender a posição contrária à sua"),
    (28, "R", "Revisão semanal"),
    (29, "T", "Entrevista técnica completa em inglês"),
    (30, "R", "Balanço: gravar 3 min falando livremente e comparar com o dia 1"),
]

PLAN: dict[int, PlanDay] = {d: PlanDay(d, k, t) for d, k, t in _RAW}
TOTAL_DAYS = len(PLAN)


def get(day: int) -> PlanDay | None:
    return PLAN.get(day)


def weeks() -> dict[int, list[PlanDay]]:
    out: dict[int, list[PlanDay]] = {}
    for pd in PLAN.values():
        out.setdefault(pd.week, []).append(pd)
    for v in out.values():
        v.sort(key=lambda p: p.day)
    return out
