from django.core.management.base import BaseCommand
from core.models import Disciplina

DISCIPLINAS = [
    ("lingua_portuguesa", "Língua Portuguesa", 1, 10),
    ("matematica", "Matemática", 1, 5),
    ("quimica", "Química", 1, 10),
    ("fisica", "Física", 1, 10),
    ("biologia", "Biologia", 1, 5),
    ("nocoes_informatica", "Noções de Informática", 1, 5),
    ("nocoes_agenda_ambiental", "Noções de Agenda Ambiental", 1, 5),
    ("pdpm", "PDPM", 1, 5),
    ("legislacao", "Legislação", 1, 10),
    ("emergencia_pre_hospitalar", "Emergência Pré Hospitalar", 4, 10),
]

class Command(BaseCommand):
    help = "Popula as disciplinas com pesos e quantidades"

    def handle(self, *args, **options):
        criadas = 0
        atualizadas = 0
        for codigo, nome, peso, qtd in DISCIPLINAS:
            obj, created = Disciplina.objects.update_or_create(
                codigo=codigo,
                defaults={"nome": nome, "peso": peso, "questoes_prova": qtd}
            )
            if created:
                criadas += 1
            else:
                atualizadas += 1
        self.stdout.write(self.style.SUCCESS(
            f"Disciplinas: {criadas} criadas, {atualizadas} atualizadas."
        ))

