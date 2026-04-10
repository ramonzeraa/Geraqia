from django.core.management.base import BaseCommand
from core.models import Questao
from core.services import QuestaoGenerator
import hashlib

class Command(BaseCommand):
    help = "Popula hashes das questões existentes para controle de duplicatas"

    def handle(self, *args, **options):
        questoes_sem_hash = Questao.objects.filter(hash_conteudo__isnull=True)
        total = questoes_sem_hash.count()
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS('Todas as questões já possuem hash.'))
            return
        
        self.stdout.write(f'Processando {total} questões...')
        
        processados = 0
        duplicatas = 0
        
        for questao in questoes_sem_hash:
            try:
                # Calcula hash do enunciado
                hash_conteudo = QuestaoGenerator()._calcular_hash_questao(questao.enunciado)
                
                # Verifica se já existe questão com este hash
                if Questao.objects.filter(hash_conteudo=hash_conteudo).exclude(id=questao.id).exists():
                    self.stdout.write(self.style.WARNING(f'⚠ Duplicata detectada: Questão {questao.id}'))
                    duplicatas += 1
                else:
                    questao.hash_conteudo = hash_conteudo
                    questao.save()
                    processados += 1
                    self.stdout.write(f'✓ Questão {questao.id}')
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Erro na questão {questao.id}: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS(
            f'Processamento concluído: {processados} processadas, {duplicatas} duplicatas detectadas'
        ))

