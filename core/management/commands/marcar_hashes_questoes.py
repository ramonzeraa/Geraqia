from django.core.management.base import BaseCommand
from core.models import Questao
from core.services import QuestaoDeduplicator


class Command(BaseCommand):
    help = 'Marca todas as questões existentes com hash de conteúdo para detecção de duplicatas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra o que seria feito sem executar as alterações',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        questoes_sem_hash = Questao.objects.filter(hash_conteudo__isnull=True)
        total_questoes = questoes_sem_hash.count()
        
        if total_questoes == 0:
            self.stdout.write(
                self.style.SUCCESS('Todas as questões já possuem hash de conteúdo!')
            )
            return
        
        self.stdout.write(f'Encontradas {total_questoes} questões sem hash de conteúdo.')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('Modo dry-run: Nenhuma alteração será feita.')
            )
            return
        
        # Marca questões com hash
        questoes_processadas = 0
        for questao in questoes_sem_hash:
            try:
                QuestaoDeduplicator.marcar_hash_questao(questao)
                questoes_processadas += 1
                
                if questoes_processadas % 100 == 0:
                    self.stdout.write(f'Processadas {questoes_processadas} questões...')
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Erro ao processar questão {questao.id}: {e}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Processamento concluído! {questoes_processadas} questões marcadas com hash.'
            )
        )
