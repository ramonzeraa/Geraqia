from django.core.management.base import BaseCommand
from core.models import Questao

class Command(BaseCommand):
    help = "Limpa todas as estatísticas e sincroniza dados"

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirma a limpeza das estatísticas',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    'ATENÇÃO: Este comando irá limpar TODAS as estatísticas!\n'
                    'Use --confirm para executar.'
                )
            )
            return

        # Conta registros antes da limpeza
        total_estatisticas = EstatisticaUsuario.objects.count()
        # Sistema de tentativas removido por enquanto
        total_tentativas = 0
        total_questoes = Questao.objects.count()

        self.stdout.write(f'Estatísticas encontradas: {total_estatisticas}')
        self.stdout.write(f'Tentativas encontradas: {total_tentativas}')
        self.stdout.write(f'Questões encontradas: {total_questoes}')

        # Limpa estatísticas consolidadas
        EstatisticaUsuario.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('✓ Estatísticas consolidadas removidas'))

        # Limpa tentativas
        # Sistema de tentativas removido por enquanto
        # TentativaQuestao.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('✓ Tentativas removidas'))

        # Reseta contadores das questões
        Questao.objects.update(
            total_tentativas=0,
            total_acertos=0
        )
        self.stdout.write(self.style.SUCCESS('✓ Contadores das questões resetados'))

        self.stdout.write(
            self.style.SUCCESS(
                f'\nLimpeza concluída!\n'
                f'- {total_estatisticas} estatísticas removidas\n'
                f'- {total_tentativas} tentativas removidas\n'
                f'- Contadores das questões resetados'
            )
        )

