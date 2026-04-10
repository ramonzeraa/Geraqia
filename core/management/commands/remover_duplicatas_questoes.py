from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Questao, TentativaQuestao
from core.services import QuestaoDeduplicator


class Command(BaseCommand):
    help = 'Remove questões duplicadas, mantendo a mais antiga e transferindo tentativas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra o que seria feito sem executar as alterações',
        )
        parser.add_argument(
            '--similaridade',
            type=float,
            default=0.8,
            help='Limite de similaridade para considerar duplicata (0.0 a 1.0)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limite_similaridade = options['similaridade']
        
        self.stdout.write('Buscando questões duplicadas...')
        
        # Busca questões com hash duplicado
        questoes_com_hash = Questao.objects.filter(hash_conteudo__isnull=False)
        hashes_duplicados = {}
        
        for questao in questoes_com_hash:
            hash_conteudo = questao.hash_conteudo
            if hash_conteudo not in hashes_duplicados:
                hashes_duplicados[hash_conteudo] = []
            hashes_duplicados[hash_conteudo].append(questao)
        
        # Filtra apenas hashes com duplicatas
        hashes_duplicados = {k: v for k, v in hashes_duplicados.items() if len(v) > 1}
        
        if not hashes_duplicados:
            self.stdout.write(
                self.style.SUCCESS('Nenhuma duplicata exata encontrada!')
            )
        else:
            self.stdout.write(f'Encontrados {len(hashes_duplicados)} grupos de duplicatas exatas.')
        
        # Busca duplicatas por similaridade
        questoes_duplicadas_similaridade = []
        questoes_processadas = set()
        
        for questao in questoes_com_hash:
            if questao.id in questoes_processadas:
                continue
                
            questoes_processadas.add(questao.id)
            
            # Busca questões similares
            questoes_similares = []
            for outra_questao in questoes_com_hash:
                if outra_questao.id in questoes_processadas:
                    continue
                    
                # Calcula similaridade
                enunciado_normalizado = QuestaoDeduplicator.normalizar_texto(questao.enunciado)
                outra_enunciado_normalizado = QuestaoDeduplicator.normalizar_texto(outra_questao.enunciado)
                
                palavras_questao = set(enunciado_normalizado.split())
                palavras_outra = set(outra_enunciado_normalizado.split())
                
                if len(palavras_questao) > 0 and len(palavras_outra) > 0:
                    palavras_comuns = palavras_questao.intersection(palavras_outra)
                    similaridade = len(palavras_comuns) / max(len(palavras_questao), len(palavras_outra))
                    
                    if similaridade >= limite_similaridade:
                        questoes_similares.append(outra_questao)
                        questoes_processadas.add(outra_questao.id)
            
            if questoes_similares:
                questoes_duplicadas_similaridade.append([questao] + questoes_similares)
        
        total_duplicatas = len(hashes_duplicados) + len(questoes_duplicadas_similaridade)
        
        if total_duplicatas == 0:
            self.stdout.write(
                self.style.SUCCESS('Nenhuma duplicata encontrada!')
            )
            return
        
        self.stdout.write(f'Total de grupos de duplicatas encontrados: {total_duplicatas}')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('Modo dry-run: Nenhuma alteração será feita.')
            )
            self._mostrar_duplicatas(hashes_duplicados, questoes_duplicadas_similaridade)
            return
        
        # Remove duplicatas
        questoes_removidas = 0
        tentativas_transferidas = 0
        
        with transaction.atomic():
            # Remove duplicatas exatas (mesmo hash)
            for hash_conteudo, questoes in hashes_duplicados.items():
                # Ordena por data de criação (mantém a mais antiga)
                questoes_ordenadas = sorted(questoes, key=lambda x: x.data_criacao)
                questao_mantida = questoes_ordenadas[0]
                questoes_para_remover = questoes_ordenadas[1:]
                
                for questao_remover in questoes_para_remover:
                    # Transfere tentativas para a questão mantida
                    tentativas = TentativaQuestao.objects.filter(questao=questao_remover)
                    for tentativa in tentativas:
                        # Verifica se já existe tentativa do mesmo usuário na questão mantida
                        tentativa_existente = TentativaQuestao.objects.filter(
                            usuario=tentativa.usuario,
                            questao=questao_mantida
                        ).first()
                        
                        if tentativa_existente:
                            # Se já existe, mantém a mais recente
                            if tentativa.data_tentativa > tentativa_existente.data_tentativa:
                                tentativa_existente.resposta_escolhida = tentativa.resposta_escolhida
                                tentativa_existente.acertou = tentativa.acertou
                                tentativa_existente.data_tentativa = tentativa.data_tentativa
                                tentativa_existente.save()
                            # Remove a tentativa duplicada
                            tentativa.delete()
                        else:
                            # Transfere a tentativa
                            tentativa.questao = questao_mantida
                            tentativa.save()
                            tentativas_transferidas += 1
                    
                    # Remove a questão duplicada
                    questao_remover.delete()
                    questoes_removidas += 1
            
            # Remove duplicatas por similaridade
            for grupo in questoes_duplicadas_similaridade:
                # Ordena por data de criação (mantém a mais antiga)
                questoes_ordenadas = sorted(grupo, key=lambda x: x.data_criacao)
                questao_mantida = questoes_ordenadas[0]
                questoes_para_remover = questoes_ordenadas[1:]
                
                for questao_remover in questoes_para_remover:
                    # Transfere tentativas para a questão mantida
                    tentativas = TentativaQuestao.objects.filter(questao=questao_remover)
                    for tentativa in tentativas:
                        # Verifica se já existe tentativa do mesmo usuário na questão mantida
                        tentativa_existente = TentativaQuestao.objects.filter(
                            usuario=tentativa.usuario,
                            questao=questao_mantida
                        ).first()
                        
                        if tentativa_existente:
                            # Se já existe, mantém a mais recente
                            if tentativa.data_tentativa > tentativa_existente.data_tentativa:
                                tentativa_existente.resposta_escolhida = tentativa.resposta_escolhida
                                tentativa_existente.acertou = tentativa.acertou
                                tentativa_existente.data_tentativa = tentativa.data_tentativa
                                tentativa_existente.save()
                            # Remove a tentativa duplicada
                            tentativa.delete()
                        else:
                            # Transfere a tentativa
                            tentativa.questao = questao_mantida
                            tentativa.save()
                            tentativas_transferidas += 1
                    
                    # Remove a questão duplicada
                    questao_remover.delete()
                    questoes_removidas += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Limpeza concluída! {questoes_removidas} questões removidas, '
                f'{tentativas_transferidas} tentativas transferidas.'
            )
        )
    
    def _mostrar_duplicatas(self, hashes_duplicados, questoes_duplicadas_similaridade):
        """Mostra as duplicatas encontradas"""
        self.stdout.write('\n=== DUPLICATAS EXATAS (mesmo hash) ===')
        for hash_conteudo, questoes in hashes_duplicados.items():
            self.stdout.write(f'Hash: {hash_conteudo[:16]}...')
            for questao in questoes:
                self.stdout.write(f'  - ID {questao.id}: {questao.enunciado[:50]}...')
        
        self.stdout.write('\n=== DUPLICATAS POR SIMILARIDADE ===')
        for i, grupo in enumerate(questoes_duplicadas_similaridade):
            self.stdout.write(f'Grupo {i+1}:')
            for questao in grupo:
                self.stdout.write(f'  - ID {questao.id}: {questao.enunciado[:50]}...')
