from django.core.management.base import BaseCommand
from core.models import Questao
from core.services import EstatisticaService
from django.db import transaction

class Command(BaseCommand):
    help = "Sincroniza estatísticas consolidadas baseado nas tentativas existentes"

    def handle(self, *args, **options):
        # Limpa estatísticas existentes
        EstatisticaUsuario.objects.all().delete()
        self.stdout.write('Estatísticas antigas removidas')

        # Busca todas as tentativas
        # Sistema de tentativas removido por enquanto
        tentativas = []
        
        if not tentativas:
            self.stdout.write(self.style.WARNING('Sistema de tentativas desabilitado'))
            return

        self.stdout.write(f'Processando {tentativas.count()} tentativas...')

        # Agrupa por usuário e disciplina
        estatisticas_por_usuario_disciplina = {}
        
        for tentativa in tentativas:
            usuario = tentativa.usuario
            disciplina = tentativa.questao.disciplina
            chave = (usuario.id, disciplina.id)
            
            if chave not in estatisticas_por_usuario_disciplina:
                estatisticas_por_usuario_disciplina[chave] = {
                    'usuario': usuario,
                    'disciplina': disciplina,
                    'total_tentativas': 0,
                    'total_acertos': 0,
                    'total_erros': 0,
                    'por_nivel': {}
                }
            
            # Atualiza totais gerais
            estatisticas_por_usuario_disciplina[chave]['total_tentativas'] += 1
            if tentativa.acertou:
                estatisticas_por_usuario_disciplina[chave]['total_acertos'] += 1
            else:
                estatisticas_por_usuario_disciplina[chave]['total_erros'] += 1
            
            # Atualiza por nível
            nivel = tentativa.questao.nivel_dificuldade
            if nivel not in estatisticas_por_usuario_disciplina[chave]['por_nivel']:
                estatisticas_por_usuario_disciplina[chave]['por_nivel'][nivel] = {
                    'tentativas': 0,
                    'acertos': 0
                }
            
            estatisticas_por_usuario_disciplina[chave]['por_nivel'][nivel]['tentativas'] += 1
            if tentativa.acertou:
                estatisticas_por_usuario_disciplina[chave]['por_nivel'][nivel]['acertos'] += 1

        # Cria estatísticas consolidadas
        with transaction.atomic():
            for (usuario_id, disciplina_id), dados in estatisticas_por_usuario_disciplina.items():
                estatistica = EstatisticaUsuario.objects.create(
                    usuario=dados['usuario'],
                    disciplina=dados['disciplina'],
                    total_questoes_tentadas=dados['total_tentativas'],
                    total_acertos=dados['total_acertos'],
                    total_erros=dados['total_erros']
                )
                
                # Preenche dados por nível
                for nivel, valores in dados['por_nivel'].items():
                    tentativas_field = f'tentativas_{nivel}'
                    acertos_field = f'acertos_{nivel}'
                    
                    setattr(estatistica, tentativas_field, valores['tentativas'])
                    setattr(estatistica, acertos_field, valores['acertos'])
                
                estatistica.save()
                
                self.stdout.write(
                    f'✓ {dados["usuario"].username} - {dados["disciplina"].nome}: '
                    f'{dados["total_acertos"]}/{dados["total_tentativas"]} acertos'
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSincronização concluída! '
                f'{len(estatisticas_por_usuario_disciplina)} estatísticas criadas.'
            )
        )

