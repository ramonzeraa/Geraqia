import re
import hashlib
import unicodedata
from django.conf import settings
import google.generativeai as genai

# Configuração da API do Google Gemini
genai.configure(api_key=settings.GEMINI_API_KEY)

class PDFProcessor:
    """Classe para processamento de PDFs"""
    
    @staticmethod
    def calcular_hash_arquivo(arquivo):
        """Calcula hash SHA-256 de um arquivo"""
        arquivo.seek(0)  # Volta para o início do arquivo
        hash_obj = hashlib.sha256()
        for chunk in iter(lambda: arquivo.read(4096), b""):
            hash_obj.update(chunk)
        arquivo.seek(0)  # Volta para o início novamente
        return hash_obj.hexdigest()
    
    @staticmethod
    def verificar_duplicata(hash_arquivo):
        """Verifica se já existe um PDF com o mesmo hash"""
        from .models import PDFDocument
        try:
            return PDFDocument.objects.get(hash_arquivo=hash_arquivo)
        except PDFDocument.DoesNotExist:
            return None
    
    @staticmethod
    def extrair_texto_pdf(arquivo):
        """Extrai texto de um arquivo PDF"""
        import fitz  # PyMuPDF
        
        try:
            doc = fitz.open(stream=arquivo.read(), filetype="pdf")
            texto = ""
            
            for pagina in doc:
                texto += pagina.get_text()
            
            doc.close()
            return texto
        except Exception as e:
            raise Exception(f"Erro ao extrair texto do PDF: {str(e)}")


class QuestaoDeduplicator:
    """Classe para gerenciar duplicatas de questões"""
    
    @staticmethod
    def normalizar_texto(texto):
        """Normaliza texto para comparação (remove acentos, espaços extras, etc.)"""
        if not texto:
            return ""
        
        # Remove acentos
        texto = unicodedata.normalize('NFD', texto)
        texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
        
        # Converte para minúsculas
        texto = texto.lower()
        
        # Remove caracteres especiais e espaços extras
        texto = re.sub(r'[^\w\s]', '', texto)
        texto = re.sub(r'\s+', ' ', texto).strip()
        
        return texto
    
    @staticmethod
    def calcular_hash_questao(enunciado, alternativas, resposta_correta):
        """Calcula hash único baseado no conteúdo da questão"""
        # Normaliza o enunciado
        enunciado_normalizado = QuestaoDeduplicator.normalizar_texto(enunciado)
        
        # Normaliza as alternativas (ordena para ser consistente)
        alternativas_normalizadas = []
        if isinstance(alternativas, list):
            alternativas_normalizadas = [QuestaoDeduplicator.normalizar_texto(alt) for alt in alternativas]
        elif isinstance(alternativas, dict):
            alternativas_normalizadas = [QuestaoDeduplicator.normalizar_texto(alt) for alt in alternativas.values()]
        
        # Ordena as alternativas para ser consistente independente da ordem
        alternativas_normalizadas.sort()
        
        # Cria string única para hash
        conteudo_para_hash = f"{enunciado_normalizado}|{'|'.join(alternativas_normalizadas)}|{resposta_correta.upper()}"
        
        # Calcula hash SHA-256
        return hashlib.sha256(conteudo_para_hash.encode('utf-8')).hexdigest()
    
    @staticmethod
    def verificar_duplicata_questao(enunciado, alternativas, resposta_correta, disciplina=None):
        """Verifica se já existe uma questão similar"""
        from .models import Questao
        
        # Calcula hash da questão
        hash_questao = QuestaoDeduplicator.calcular_hash_questao(enunciado, alternativas, resposta_correta)
        
        # Busca por questões com o mesmo hash
        try:
            questao_existente = Questao.objects.get(hash_conteudo=hash_questao)
            return questao_existente
        except Questao.DoesNotExist:
            pass
        
        # Busca por questões com enunciado muito similar (fallback)
        enunciado_normalizado = QuestaoDeduplicator.normalizar_texto(enunciado)
        
        # Busca questões da mesma disciplina se especificada
        queryset = Questao.objects.all()
        if disciplina:
            queryset = queryset.filter(disciplina=disciplina)
        
        # Verifica similaridade com outras questões
        for questao in queryset:
            enunciado_existente_normalizado = QuestaoDeduplicator.normalizar_texto(questao.enunciado)
            
            # Calcula similaridade simples (percentual de palavras em comum)
            palavras_nova = set(enunciado_normalizado.split())
            palavras_existente = set(enunciado_existente_normalizado.split())
            
            if len(palavras_nova) > 0 and len(palavras_existente) > 0:
                palavras_comuns = palavras_nova.intersection(palavras_existente)
                similaridade = len(palavras_comuns) / max(len(palavras_nova), len(palavras_existente))
                
                # Se mais de 80% das palavras são iguais, considera duplicata
                if similaridade > 0.8:
                    return questao
        
        return None
    
    @staticmethod
    def marcar_hash_questao(questao):
        """Marca uma questão com seu hash de conteúdo"""
        hash_conteudo = QuestaoDeduplicator.calcular_hash_questao(
            questao.enunciado, 
            questao.alternativas, 
            questao.resposta_correta
        )
        questao.hash_conteudo = hash_conteudo
        questao.save(update_fields=['hash_conteudo'])
        return hash_conteudo


class QuestaoGenerator:
    """Classe para geração de questões usando IA - versão simplificada"""
    
    @staticmethod
    def _get_instrucoes_por_nivel(nivel_dificuldade):
        """Retorna instruções específicas baseadas no nível de dificuldade"""
        instrucoes = {
            'fixacao': """
            NÍVEL FIXAÇÃO - CONTEÚDO DO PDF:
            • Foque em conceitos básicos e definições diretas do conteúdo
            • Questões de memorização e compreensão literal
            • Use terminologia exata do texto
            • Alternativas devem testar conhecimento direto do material
            """,
            
            'medio': """
            NÍVEL MÉDIO - APLICAÇÃO LÓGICA:
            • Combine conceitos do conteúdo com aplicação prática
            • Questões que exigem raciocínio e interpretação
            • Use cenários práticos relacionados ao conteúdo
            • Teste capacidade de análise e síntese
            • Alternativas devem incluir distratores inteligentes
            """,
            
            'dificil': """
            NÍVEL DIFÍCIL - LÓGICA + RACIOCÍNIO APLICADO:
            • Questões complexas que exigem múltiplas etapas de raciocínio
            • Integre diferentes conceitos do conteúdo
            • Use situações-problema desafiadoras
            • Teste capacidade de análise crítica e julgamento
            • Alternativas devem ser muito plausíveis e exigir conhecimento profundo
            • Inclua questões que testem aplicação em contextos específicos
            """,
            
            'nivel_banca': """
            NÍVEL BANCA - QUESTÃO REAL DE CONCURSO:
            • Questões no padrão de bancas como IDECAN, CESPE, FGV, VUNESP
            • Máxima complexidade e sofisticação
            • Integre conhecimentos de diferentes áreas relacionadas
            • Use linguagem técnica precisa e formal
            • Questões que testem competências avançadas
            • Alternativas devem ser extremamente plausíveis e exigir domínio total
            • Inclua questões de interpretação de dados, gráficos, tabelas
            • Teste capacidade de resolução de problemas complexos
            """
        }
        return instrucoes.get(nivel_dificuldade, instrucoes['medio'])
    
    @staticmethod
    def gerar_questoes(conteudo_pdf, disciplina, topico, nivel_dificuldade, quantidade, pdf_origem, tipos_questoes=None):
        """Gera questões a partir do conteúdo do PDF"""
        from .models import Questao
        
        try:
            # Tenta diferentes modelos do Gemini
            modelos_disponiveis = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
            model = None
            
            for modelo_nome in modelos_disponiveis:
                try:
                    model = genai.GenerativeModel(modelo_nome)
                    break
                except Exception:
                    continue
            
            if not model:
                raise Exception("Nenhum modelo do Gemini está disponível no momento")
            
            questoes_criadas = []
            
            # Se nenhum tipo foi especificado, usa os padrões
            if not tipos_questoes:
                tipos_questoes = ['multipla_escolha', 'afirmacoes_variadas', 'verdadeiro_falso']
            
            # Calcula quantas questões gerar para cada tipo
            quantidade_por_tipo = quantidade // len(tipos_questoes)
            resto = quantidade % len(tipos_questoes)
            
            for i, tipo in enumerate(tipos_questoes):
                # Adiciona uma questão extra para os primeiros tipos se houver resto
                quantidade_tipo = quantidade_por_tipo + (1 if i < resto else 0)
                
                if quantidade_tipo > 0:
                    if tipo == 'multipla_escolha':
                        questoes_tipo = QuestaoGenerator._gerar_questoes_multipla_escolha(
                            model, conteudo_pdf, disciplina, nivel_dificuldade, quantidade_tipo, pdf_origem
                        )
                        questoes_criadas.extend(questoes_tipo)
                    elif tipo == 'certo_errado':
                        questoes_tipo = QuestaoGenerator._gerar_questoes_certo_errado(
                            model, conteudo_pdf, disciplina, nivel_dificuldade, quantidade_tipo, pdf_origem
                        )
                        questoes_criadas.extend(questoes_tipo)
                    elif tipo == 'afirmacoes':
                        questoes_tipo = QuestaoGenerator._gerar_questoes_afirmacoes(
                            model, conteudo_pdf, disciplina, nivel_dificuldade, quantidade_tipo, pdf_origem
                        )
                        questoes_criadas.extend(questoes_tipo)
                    elif tipo == 'afirmacoes_variadas':
                        questoes_tipo = QuestaoGenerator._gerar_questoes_afirmacoes_variadas(
                            model, conteudo_pdf, disciplina, nivel_dificuldade, quantidade_tipo, pdf_origem
                        )
                        questoes_criadas.extend(questoes_tipo)
                    elif tipo == 'verdadeiro_falso':
                        questoes_tipo = QuestaoGenerator._gerar_questoes_vf(
                            model, conteudo_pdf, disciplina, nivel_dificuldade, quantidade_tipo, pdf_origem
                        )
                        questoes_criadas.extend(questoes_tipo)
            
            return questoes_criadas
            
        except Exception as e:
            error_str = str(e)
            if "404" in error_str and "models" in error_str:
                raise Exception(f"Modelo da API Gemini não encontrado. Erro: {error_str}")
            elif "quota" in error_str.lower() or "429" in error_str:
                raise Exception(f"Limite de cota da API Gemini atingido. Tente novamente em algumas horas ou considere fazer upgrade da conta.")
            else:
                raise Exception(f"Erro ao gerar questões: {error_str}")
    
    @staticmethod
    def _gerar_questoes_afirmacoes_variadas(model, conteudo_pdf, disciplina, nivel_dificuldade, quantidade, pdf_origem):
        """Gera questões de afirmações com alternativas variadas"""
        from .models import Questao
        
        # Prompt para geração de questões de afirmações variadas
        prompt = f"""
        Você é um especialista em {disciplina.nome} com vasta experiência em concursos públicos e precisa criar {quantidade} questões de afirmações com alternativas variadas baseadas no conteúdo fornecido.
        
        CONTEÚDO DO PDF:
        {conteudo_pdf[:3000]}
        
        INSTRUÇÕES ESPECÍFICAS POR NÍVEL:
        
        {QuestaoGenerator._get_instrucoes_por_nivel(nivel_dificuldade)}
        
        REQUISITOS TÉCNICOS:
        1. Crie questões REAIS e INTELIGENTES baseadas no conteúdo acima
        2. Use terminologia técnica apropriada para {disciplina.nome}
        3. Cada questão deve ter 3-5 afirmações (I, II, III, IV, V)
        4. As afirmações devem ser sobre o mesmo tópico/conceito
        5. Algumas afirmações devem ser verdadeiras, outras falsas
        6. Inclua justificativa técnica detalhada para a resposta correta
        7. As alternativas devem ser variadas e criativas, não genéricas
        8. Evite questões óbvias ou muito simples
        9. Priorize aplicação prática e raciocínio lógico
        
        FORMATO DE RESPOSTA (JSON):
        {{
            "questoes": [
                {{
                    "enunciado": "Questão específica e técnica sobre o conteúdo",
                    "afirmacoes": [
                        "Primeira afirmação técnica sobre o tópico",
                        "Segunda afirmação técnica sobre o tópico",
                        "Terceira afirmação técnica sobre o tópico",
                        "Quarta afirmação técnica sobre o tópico (opcional)",
                        "Quinta afirmação técnica sobre o tópico (opcional)"
                    ],
                    "instrucao_tipo": "correto",
                    "instrucao_texto": "Está CORRETO o que se afirma:",
                    "resposta_correta": "A",
                    "justificativa": "Explicação técnica detalhada baseada no conteúdo"
                }}
            ]
        }}
        
        TIPOS DE INSTRUÇÃO DISPONÍVEIS:
        - "correto": "Está CORRETO o que se afirma"
        - "incorreto": "Está INCORRETO o que se afirma"
        - "corretos": "Estão CORRETOS os itens"
        - "incorretos": "Estão INCORRETOS os itens"
        - "correto_nos": "Está CORRETO o que se afirma nos itens"
        - "incorreto_nos": "Está INCORRETO o que se afirma nos itens"
        
        IMPORTANTE: Responda APENAS com o JSON, sem texto adicional.
        """
        
        # Gera as questões usando IA
        response = model.generate_content(prompt)
        questoes_criadas = []
        
        # Processa a resposta da IA
        try:
            # Tenta extrair JSON da resposta
            response_text = response.text
            
            # Procura por padrão JSON na resposta
            import json
            import re
            
            # Busca por padrão JSON na resposta
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_data = json.loads(json_match.group())
                questoes_ia = json_data.get('questoes', [])
                
                # Cria questões baseadas na resposta da IA
                for i, questao_data in enumerate(questoes_ia[:quantidade]):
                    enunciado = questao_data.get('enunciado', f'Questão {i+1} sobre {disciplina.nome}')
                    afirmacoes = questao_data.get('afirmacoes', [])
                    instrucao_tipo = questao_data.get('instrucao_tipo', 'correto')
                    instrucao_texto = questao_data.get('instrucao_texto', 'Está CORRETO o que se afirma:')
                    resposta_correta = questao_data.get('resposta_correta', 'A')
                    
                    # Cria a questão temporariamente para gerar alternativas variadas
                    questao_temp = Questao(
                        afirmacoes=afirmacoes,
                        tipo='afirmacoes_variadas'
                    )
                    alternativas = questao_temp.gerar_alternativas_variadas()
                    
                    # Verifica se já existe uma questão similar
                    questao_duplicada = QuestaoDeduplicator.verificar_duplicata_questao(
                        enunciado, alternativas, resposta_correta, disciplina
                    )
                    
                    if questao_duplicada:
                        print(f"Questão de afirmações variadas duplicada detectada: {enunciado[:50]}... (ID: {questao_duplicada.id})")
                        continue  # Pula esta questão
                    
                    # Cria a questão se não for duplicata
                    questao = Questao.objects.create(
                        enunciado=enunciado,
                        alternativas=alternativas,
                        resposta_correta=resposta_correta,
                        explicacao=questao_data.get('justificativa', 'Explicação da resposta'),
                        disciplina=disciplina,
                        nivel_dificuldade=nivel_dificuldade,
                        pdf_origem=pdf_origem,
                        tipo='afirmacoes_variadas',
                        afirmacoes=afirmacoes,
                        instrucao_tipo=instrucao_tipo,
                        instrucao_texto=instrucao_texto
                    )
                    
                    # Marca a questão com seu hash
                    QuestaoDeduplicator.marcar_hash_questao(questao)
                    questoes_criadas.append(questao)
            else:
                # Se não conseguir extrair JSON, cria questões básicas baseadas no conteúdo do PDF
                raise Exception("Resposta da IA não contém JSON válido")
                
        except Exception as e:
            # Fallback: cria questões básicas baseadas no conteúdo do PDF
            print(f"Erro ao processar resposta da IA para afirmações variadas: {e}")
            print(f"Resposta da IA: {response.text[:500]}...")
            
            # Extrai palavras-chave do PDF para criar questões mais relevantes
            palavras_chave = conteudo_pdf.split()[:20]  # Primeiras 20 palavras
            palavras_unicas = list(set(palavras_chave))[:10]  # Remove duplicatas
            
            for i in range(quantidade):
                enunciado = f"Com base no conteúdo sobre {', '.join(palavras_unicas[:3])}, analise as afirmações:"
                afirmacoes = [
                    f"Afirmação relacionada a {palavras_unicas[0] if palavras_unicas else 'conteúdo'}",
                    f"Afirmação relacionada a {palavras_unicas[1] if len(palavras_unicas) > 1 else 'conteúdo'}",
                    f"Afirmação relacionada a {palavras_unicas[2] if len(palavras_unicas) > 2 else 'conteúdo'}"
                ]
                
                # Cria questão temporária para gerar alternativas variadas
                questao_temp = Questao(
                    afirmacoes=afirmacoes,
                    tipo='afirmacoes_variadas'
                )
                alternativas = questao_temp.gerar_alternativas_variadas()
                resposta_correta = "A"
                
                # Verifica se já existe uma questão similar
                questao_duplicada = QuestaoDeduplicator.verificar_duplicata_questao(
                    enunciado, alternativas, resposta_correta, disciplina
                )
                
                if questao_duplicada:
                    print(f"Questão de afirmações variadas duplicada detectada (fallback): {enunciado[:50]}... (ID: {questao_duplicada.id})")
                    continue  # Pula esta questão
                
                # Cria a questão se não for duplicata
                questao = Questao.objects.create(
                    enunciado=enunciado,
                    alternativas=alternativas,
                    resposta_correta=resposta_correta,
                    explicacao=f"Explicação baseada no conteúdo sobre {', '.join(palavras_unicas[:3])}",
                    disciplina=disciplina,
                    nivel_dificuldade=nivel_dificuldade,
                    pdf_origem=pdf_origem,
                    tipo='afirmacoes_variadas',
                    afirmacoes=afirmacoes,
                    instrucao_tipo='correto',
                    instrucao_texto='Está CORRETO o que se afirma:'
                )
                
                # Marca a questão com seu hash
                QuestaoDeduplicator.marcar_hash_questao(questao)
                questoes_criadas.append(questao)
        
        return questoes_criadas
    
    @staticmethod
    def _gerar_questoes_vf(model, conteudo_pdf, disciplina, nivel_dificuldade, quantidade, pdf_origem):
        """Gera questões V ou F com sequência"""
        from .models import Questao
        
        # Prompt para geração de questões V ou F
        prompt = f"""
        Você é um especialista em {disciplina.nome} com vasta experiência em concursos públicos e precisa criar {quantidade} questões de Verdadeiro ou Falso com sequência baseadas no conteúdo fornecido.
        
        CONTEÚDO DO PDF:
        {conteudo_pdf[:3000]}
        
        INSTRUÇÕES ESPECÍFICAS POR NÍVEL:
        
        {QuestaoGenerator._get_instrucoes_por_nivel(nivel_dificuldade)}
        
        REQUISITOS TÉCNICOS:
        1. Crie questões REAIS e INTELIGENTES baseadas no conteúdo acima
        2. Use terminologia técnica apropriada para {disciplina.nome}
        3. Cada questão deve ter 4 afirmações (I, II, III, IV)
        4. As afirmações devem ser sobre o mesmo tópico/conceito
        5. Algumas afirmações devem ser verdadeiras (V), outras falsas (F)
        6. Inclua justificativa técnica detalhada para a sequência correta
        7. A sequência correta deve ser uma combinação de V e F (ex: V-V-F-V)
        8. Evite questões óbvias ou muito simples
        9. Priorize aplicação prática e raciocínio lógico
        10. As afirmações devem testar conhecimento profundo e aplicação
        
        FORMATO DE RESPOSTA (JSON):
        {{
            "questoes": [
                {{
                    "enunciado": "Questão específica e técnica sobre o conteúdo",
                    "afirmacoes": [
                        "Primeira afirmação técnica sobre o tópico",
                        "Segunda afirmação técnica sobre o tópico",
                        "Terceira afirmação técnica sobre o tópico",
                        "Quarta afirmação técnica sobre o tópico"
                    ],
                    "instrucao_vf": "a sequência correta obtida no sentido de cima para baixo",
                    "sequencia_resposta": "V-V-F-V",
                    "resposta_correta": "A",
                    "justificativa": "Explicação técnica detalhada baseada no conteúdo"
                }}
            ]
        }}
        
        IMPORTANTE: Responda APENAS com o JSON, sem texto adicional.
        """
        
        # Gera as questões usando IA
        response = model.generate_content(prompt)
        questoes_criadas = []
        
        # Processa a resposta da IA
        try:
            # Tenta extrair JSON da resposta
            response_text = response.text
            
            # Procura por padrão JSON na resposta
            import json
            import re
            
            # Busca por padrão JSON na resposta
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_data = json.loads(json_match.group())
                questoes_ia = json_data.get('questoes', [])
                
                # Cria questões baseadas na resposta da IA
                for i, questao_data in enumerate(questoes_ia[:quantidade]):
                    enunciado = questao_data.get('enunciado', f'Questão {i+1} sobre {disciplina.nome}')
                    afirmacoes = questao_data.get('afirmacoes', [])
                    instrucao_vf = questao_data.get('instrucao_vf', 'a sequência correta obtida no sentido de cima para baixo')
                    sequencia_resposta = questao_data.get('sequencia_resposta', 'V-V-F-V')
                    resposta_correta = questao_data.get('resposta_correta', 'A')
                    
                    # Cria a questão temporariamente para gerar alternativas V/F
                    questao_temp = Questao(
                        afirmacoes=afirmacoes,
                        tipo='verdadeiro_falso'
                    )
                    alternativas = questao_temp.gerar_alternativas_vf()
                    
                    # Garante que as alternativas sejam únicas
                    alternativas_unicas = []
                    for alt in alternativas:
                        if alt not in alternativas_unicas:
                            alternativas_unicas.append(alt)
                    alternativas = alternativas_unicas[:5]  # Máximo 5 alternativas
                    
                    # Verifica se já existe uma questão similar
                    questao_duplicada = QuestaoDeduplicator.verificar_duplicata_questao(
                        enunciado, alternativas, resposta_correta, disciplina
                    )
                    
                    if questao_duplicada:
                        print(f"Questão V/F duplicada detectada: {enunciado[:50]}... (ID: {questao_duplicada.id})")
                        continue  # Pula esta questão
                    
                    # Cria a questão se não for duplicata
                    questao = Questao.objects.create(
                        enunciado=enunciado,
                        alternativas=alternativas,
                        resposta_correta=resposta_correta,
                        explicacao=questao_data.get('justificativa', 'Explicação da resposta'),
                        disciplina=disciplina,
                        nivel_dificuldade=nivel_dificuldade,
                        pdf_origem=pdf_origem,
                        tipo='verdadeiro_falso',
                        afirmacoes=afirmacoes,
                        instrucao_vf=instrucao_vf,
                        sequencia_resposta=sequencia_resposta
                    )
                    
                    # Marca a questão com seu hash
                    QuestaoDeduplicator.marcar_hash_questao(questao)
                    questoes_criadas.append(questao)
            else:
                # Se não conseguir extrair JSON, cria questões básicas baseadas no conteúdo do PDF
                raise Exception("Resposta da IA não contém JSON válido")
                
        except Exception as e:
            # Fallback: cria questões básicas baseadas no conteúdo do PDF
            print(f"Erro ao processar resposta da IA para questões V/F: {e}")
            print(f"Resposta da IA: {response.text[:500]}...")
            
            # Extrai palavras-chave do PDF para criar questões mais relevantes
            palavras_chave = conteudo_pdf.split()[:20]  # Primeiras 20 palavras
            palavras_unicas = list(set(palavras_chave))[:10]  # Remove duplicatas
            
            for i in range(quantidade):
                enunciado = f"Com base no conteúdo sobre {', '.join(palavras_unicas[:3])}, analise as afirmações:"
                afirmacoes = [
                    f"Afirmação relacionada a {palavras_unicas[0] if palavras_unicas else 'conteúdo'}",
                    f"Afirmação relacionada a {palavras_unicas[1] if len(palavras_unicas) > 1 else 'conteúdo'}",
                    f"Afirmação relacionada a {palavras_unicas[2] if len(palavras_unicas) > 2 else 'conteúdo'}",
                    f"Afirmação relacionada a {palavras_unicas[3] if len(palavras_unicas) > 3 else 'conteúdo'}"
                ]
                
                # Cria questão temporária para gerar alternativas V/F
                questao_temp = Questao(
                    afirmacoes=afirmacoes,
                    tipo='verdadeiro_falso'
                )
                alternativas = questao_temp.gerar_alternativas_vf()
                
                # Garante que as alternativas sejam únicas
                alternativas_unicas = []
                for alt in alternativas:
                    if alt not in alternativas_unicas:
                        alternativas_unicas.append(alt)
                alternativas = alternativas_unicas[:5]  # Máximo 5 alternativas
                
                resposta_correta = "A"
                sequencia_resposta = "V-V-F-V"
                
                # Verifica se já existe uma questão similar
                questao_duplicada = QuestaoDeduplicator.verificar_duplicata_questao(
                    enunciado, alternativas, resposta_correta, disciplina
                )
                
                if questao_duplicada:
                    print(f"Questão V/F duplicada detectada (fallback): {enunciado[:50]}... (ID: {questao_duplicada.id})")
                    continue  # Pula esta questão
                
                # Cria a questão se não for duplicata
                questao = Questao.objects.create(
                    enunciado=enunciado,
                    alternativas=alternativas,
                    resposta_correta=resposta_correta,
                    explicacao=f"Explicação baseada no conteúdo sobre {', '.join(palavras_unicas[:3])}",
                    disciplina=disciplina,
                    nivel_dificuldade=nivel_dificuldade,
                    pdf_origem=pdf_origem,
                    tipo='verdadeiro_falso',
                    afirmacoes=afirmacoes,
                    instrucao_vf='a sequência correta obtida no sentido de cima para baixo',
                    sequencia_resposta=sequencia_resposta
                )
                
                # Marca a questão com seu hash
                QuestaoDeduplicator.marcar_hash_questao(questao)
                questoes_criadas.append(questao)
        
        return questoes_criadas
    
    @staticmethod
    def _gerar_questoes_multipla_escolha(model, conteudo_pdf, disciplina, nivel_dificuldade, quantidade, pdf_origem):
        """Gera questões de múltipla escolha"""
        from .models import Questao
        
        # Prompt para geração de questões de múltipla escolha
        prompt = f"""
        Você é um especialista em {disciplina.nome} com vasta experiência em concursos públicos e precisa criar {quantidade} questões de múltipla escolha baseadas no conteúdo fornecido.
        
        CONTEÚDO DO PDF:
        {conteudo_pdf[:3000]}
        
        INSTRUÇÕES ESPECÍFICAS POR NÍVEL:
        
        {QuestaoGenerator._get_instrucoes_por_nivel(nivel_dificuldade)}
        
        REQUISITOS TÉCNICOS:
        1. Crie questões REAIS e INTELIGENTES baseadas no conteúdo acima
        2. Use terminologia técnica apropriada para {disciplina.nome}
        3. Cada questão deve ter 5 alternativas (A, B, C, D, E)
        4. Apenas UMA alternativa deve estar correta
        5. As alternativas incorretas devem ser plausíveis mas erradas
        6. Inclua justificativa técnica detalhada para a resposta correta
        7. Evite questões óbvias ou muito simples
        8. Priorize aplicação prática e raciocínio lógico
        
        FORMATO DE RESPOSTA (JSON):
        {{
            "questoes": [
                {{
                    "enunciado": "Questão específica e técnica sobre o conteúdo",
                    "alternativas": {{
                        "A": "Alternativa técnica e plausível",
                        "B": "Alternativa técnica e plausível", 
                        "C": "Alternativa técnica e plausível",
                        "D": "Alternativa técnica e plausível",
                        "E": "Alternativa técnica e plausível"
                    }},
                    "resposta_correta": "A",
                    "justificativa": "Explicação técnica detalhada baseada no conteúdo"
                }}
            ]
        }}
        
        IMPORTANTE: Responda APENAS com o JSON, sem texto adicional.
        """
        
        # Gera as questões usando IA
        response = model.generate_content(prompt)
        questoes_criadas = []
        
        # Processa a resposta da IA
        try:
            # Tenta extrair JSON da resposta
            response_text = response.text
            
            # Procura por JSON na resposta
            import json
            import re
            
            # Busca por padrão JSON na resposta
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_data = json.loads(json_match.group())
                questoes_ia = json_data.get('questoes', [])
                
                # Cria questões baseadas na resposta da IA
                for i, questao_data in enumerate(questoes_ia[:quantidade]):
                    enunciado = questao_data.get('enunciado', f'Questão {i+1} sobre {disciplina.nome}')
                    alternativas = list(questao_data.get('alternativas', {}).values()) if questao_data.get('alternativas') else ["Alternativa A", "Alternativa B", "Alternativa C", "Alternativa D", "Alternativa E"]
                    resposta_correta = questao_data.get('resposta_correta', 'A')
                    
                    # Verifica se já existe uma questão similar
                    questao_duplicada = QuestaoDeduplicator.verificar_duplicata_questao(
                        enunciado, alternativas, resposta_correta, disciplina
                    )
                    
                    if questao_duplicada:
                        print(f"Questão duplicada detectada: {enunciado[:50]}... (ID: {questao_duplicada.id})")
                        continue  # Pula esta questão
                    
                    # Cria a questão se não for duplicata
                    questao = Questao.objects.create(
                        enunciado=enunciado,
                        alternativas=alternativas,
                        resposta_correta=resposta_correta,
                        explicacao=questao_data.get('justificativa', 'Explicação da resposta'),
                        disciplina=disciplina,
                        nivel_dificuldade=nivel_dificuldade,
                        pdf_origem=pdf_origem,
                        tipo='multipla_escolha'
                    )
                    
                    # Marca a questão com seu hash
                    QuestaoDeduplicator.marcar_hash_questao(questao)
                    questoes_criadas.append(questao)
            else:
                # Se não conseguir extrair JSON, cria questões baseadas no conteúdo
                raise Exception("Resposta da IA não contém JSON válido")
                
        except Exception as e:
            # Fallback: cria questões básicas baseadas no conteúdo do PDF
            print(f"Erro ao processar resposta da IA: {e}")
            print(f"Resposta da IA: {response.text[:500]}...")
            
            # Extrai palavras-chave do PDF para criar questões mais relevantes
            palavras_chave = conteudo_pdf.split()[:20]  # Primeiras 20 palavras
            palavras_unicas = list(set(palavras_chave))[:10]  # Remove duplicatas
            
            for i in range(quantidade):
                enunciado = f"Com base no conteúdo sobre {', '.join(palavras_unicas[:3])}, qual é a alternativa correta?"
                alternativas = [
                    f"Alternativa relacionada a {palavras_unicas[0] if palavras_unicas else 'conteúdo'}",
                    f"Alternativa relacionada a {palavras_unicas[1] if len(palavras_unicas) > 1 else 'conteúdo'}",
                    f"Alternativa relacionada a {palavras_unicas[2] if len(palavras_unicas) > 2 else 'conteúdo'}",
                    f"Alternativa relacionada a {palavras_unicas[3] if len(palavras_unicas) > 3 else 'conteúdo'}",
                    f"Alternativa relacionada a {palavras_unicas[4] if len(palavras_unicas) > 4 else 'conteúdo'}"
                ]
                resposta_correta = "A"
                
                # Verifica se já existe uma questão similar
                questao_duplicada = QuestaoDeduplicator.verificar_duplicata_questao(
                    enunciado, alternativas, resposta_correta, disciplina
                )
                
                if questao_duplicada:
                    print(f"Questão duplicada detectada (fallback): {enunciado[:50]}... (ID: {questao_duplicada.id})")
                    continue  # Pula esta questão
                
                # Cria a questão se não for duplicata
                questao = Questao.objects.create(
                    enunciado=enunciado,
                    alternativas=alternativas,
                    resposta_correta=resposta_correta,
                    explicacao=f"Explicação baseada no conteúdo sobre {', '.join(palavras_unicas[:3])}",
                    disciplina=disciplina,
                    nivel_dificuldade=nivel_dificuldade,
                    pdf_origem=pdf_origem,
                    tipo='multipla_escolha'
                )
                
                # Marca a questão com seu hash
                QuestaoDeduplicator.marcar_hash_questao(questao)
                questoes_criadas.append(questao)
        
        return questoes_criadas
    
    @staticmethod
    def _gerar_questoes_afirmacoes(model, conteudo_pdf, disciplina, nivel_dificuldade, quantidade, pdf_origem):
        """Gera questões de afirmações"""
        from .models import Questao
        
        # Prompt para geração de questões de afirmações
        prompt = f"""
        Você é um especialista em {disciplina.nome} e precisa criar {quantidade} questões de afirmações baseadas no conteúdo fornecido.
        
        CONTEÚDO DO PDF:
        {conteudo_pdf[:3000]}
        
        INSTRUÇÕES:
        1. Crie questões REAIS e INTELIGENTES baseadas no conteúdo acima
        2. Use terminologia técnica apropriada para {disciplina.nome}
        3. Nível de dificuldade: {nivel_dificuldade}
        4. Cada questão deve ter 3-5 afirmações (I, II, III, IV, V)
        5. As afirmações devem ser sobre o mesmo tópico/conceito
        6. Algumas afirmações devem ser verdadeiras, outras falsas
        7. Inclua justificativa técnica para a resposta correta
        
        FORMATO DE RESPOSTA (JSON):
        {{
            "questoes": [
                {{
                    "enunciado": "Questão específica e técnica sobre o conteúdo",
                    "afirmacoes": [
                        "Primeira afirmação técnica sobre o tópico",
                        "Segunda afirmação técnica sobre o tópico",
                        "Terceira afirmação técnica sobre o tópico",
                        "Quarta afirmação técnica sobre o tópico (opcional)",
                        "Quinta afirmação técnica sobre o tópico (opcional)"
                    ],
                    "instrucao_tipo": "correto",
                    "instrucao_texto": "Está CORRETO o que se afirma:",
                    "resposta_correta": "A",
                    "justificativa": "Explicação técnica detalhada baseada no conteúdo"
                }}
            ]
        }}
        
        TIPOS DE INSTRUÇÃO DISPONÍVEIS:
        - "correto": "Está CORRETO o que se afirma"
        - "incorreto": "Está INCORRETO o que se afirma"
        - "corretos": "Estão CORRETOS os itens"
        - "incorretos": "Estão INCORRETOS os itens"
        - "correto_nos": "Está CORRETO o que se afirma nos itens"
        - "incorreto_nos": "Está INCORRETO o que se afirma nos itens"
        
        RESPOSTAS POSSÍVEIS:
        - "A": Apenas no item I
        - "B": Apenas no item II
        - "C": Apenas nos itens I e II (se houver 3+ afirmações)
        - "D": Em todos os itens (se houver 3+ afirmações)
        - "E": Nenhum item (se houver apenas 2 afirmações)
        
        IMPORTANTE: Responda APENAS com o JSON, sem texto adicional.
        """
        
        # Gera as questões usando IA
        response = model.generate_content(prompt)
        questoes_criadas = []
        
        # Processa a resposta da IA
        try:
            # Tenta extrair JSON da resposta
            response_text = response.text
            
            # Procura por JSON na resposta
            import json
            import re
            
            # Busca por padrão JSON na resposta
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_data = json.loads(json_match.group())
                questoes_ia = json_data.get('questoes', [])
                
                # Cria questões baseadas na resposta da IA
                for i, questao_data in enumerate(questoes_ia[:quantidade]):
                    enunciado = questao_data.get('enunciado', f'Questão {i+1} sobre {disciplina.nome}')
                    afirmacoes = questao_data.get('afirmacoes', [])
                    instrucao_tipo = questao_data.get('instrucao_tipo', 'correto')
                    instrucao_texto = questao_data.get('instrucao_texto', 'Está CORRETO o que se afirma:')
                    resposta_correta = questao_data.get('resposta_correta', 'A')
                    
                    # Gera alternativas baseadas no número de afirmações
                    num_afirmacoes = len(afirmacoes)
                    alternativas = []
                    
                    if num_afirmacoes >= 2:
                        alternativas.append("Apenas no item I")
                        alternativas.append("Apenas no item II")
                        
                        if num_afirmacoes >= 3:
                            alternativas.append("Apenas nos itens I e II")
                            alternativas.append("Em todos os itens")
                        else:
                            alternativas.append("Em todos os itens")
                            alternativas.append("Nenhum item")
                    
                    # Verifica se já existe uma questão similar
                    questao_duplicada = QuestaoDeduplicator.verificar_duplicata_questao(
                        enunciado, alternativas, resposta_correta, disciplina
                    )
                    
                    if questao_duplicada:
                        print(f"Questão de afirmações duplicada detectada: {enunciado[:50]}... (ID: {questao_duplicada.id})")
                        continue  # Pula esta questão
                    
                    # Cria a questão se não for duplicata
                    questao = Questao.objects.create(
                        enunciado=enunciado,
                        alternativas=alternativas,
                        resposta_correta=resposta_correta,
                        explicacao=questao_data.get('justificativa', 'Explicação da resposta'),
                        disciplina=disciplina,
                        nivel_dificuldade=nivel_dificuldade,
                        pdf_origem=pdf_origem,
                        tipo='afirmacoes',
                        afirmacoes=afirmacoes,
                        instrucao_tipo=instrucao_tipo,
                        instrucao_texto=instrucao_texto
                    )
                    
                    # Marca a questão com seu hash
                    QuestaoDeduplicator.marcar_hash_questao(questao)
                    questoes_criadas.append(questao)
            else:
                # Se não conseguir extrair JSON, cria questões básicas baseadas no conteúdo do PDF
                raise Exception("Resposta da IA não contém JSON válido")
                
        except Exception as e:
            # Fallback: cria questões básicas baseadas no conteúdo do PDF
            print(f"Erro ao processar resposta da IA para afirmações: {e}")
            print(f"Resposta da IA: {response.text[:500]}...")
            
            # Extrai palavras-chave do PDF para criar questões mais relevantes
            palavras_chave = conteudo_pdf.split()[:20]  # Primeiras 20 palavras
            palavras_unicas = list(set(palavras_chave))[:10]  # Remove duplicatas
            
            for i in range(quantidade):
                enunciado = f"Com base no conteúdo sobre {', '.join(palavras_unicas[:3])}, analise as afirmações:"
                afirmacoes = [
                    f"Afirmação relacionada a {palavras_unicas[0] if palavras_unicas else 'conteúdo'}",
                    f"Afirmação relacionada a {palavras_unicas[1] if len(palavras_unicas) > 1 else 'conteúdo'}",
                    f"Afirmação relacionada a {palavras_unicas[2] if len(palavras_unicas) > 2 else 'conteúdo'}"
                ]
                alternativas = ["Apenas no item I", "Apenas no item II", "Em todos os itens", "Nenhum item"]
                resposta_correta = "A"
                
                # Verifica se já existe uma questão similar
                questao_duplicada = QuestaoDeduplicator.verificar_duplicata_questao(
                    enunciado, alternativas, resposta_correta, disciplina
                )
                
                if questao_duplicada:
                    print(f"Questão de afirmações duplicada detectada (fallback): {enunciado[:50]}... (ID: {questao_duplicada.id})")
                    continue  # Pula esta questão
                
                # Cria a questão se não for duplicata
                questao = Questao.objects.create(
                    enunciado=enunciado,
                    alternativas=alternativas,
                    resposta_correta=resposta_correta,
                    explicacao=f"Explicação baseada no conteúdo sobre {', '.join(palavras_unicas[:3])}",
                    disciplina=disciplina,
                    nivel_dificuldade=nivel_dificuldade,
                    pdf_origem=pdf_origem,
                    tipo='afirmacoes',
                    afirmacoes=afirmacoes,
                    instrucao_tipo='correto',
                    instrucao_texto='Está CORRETO o que se afirma:'
                )
                
                # Marca a questão com seu hash
                QuestaoDeduplicator.marcar_hash_questao(questao)
                questoes_criadas.append(questao)
        
        return questoes_criadas


class ProvaAntigaAnalyzer:
    """Classe para análise de provas antigas"""
    
    DISCIPLINAS_PATTERNS = {
        'Língua Portuguesa': [
            r'LÍNGUA\s+PORTUGUESA',
            r'PORTUGUÊS',
            r'LINGUA\s+PORTUGUESA'
        ],
        'Matemática': [
            r'MATEMÁTICA',
            r'MATEMATICA'
        ],
        'Química': [
            r'QUÍMICA',
            r'QUIMICA'
        ],
        'Física': [
            r'FÍSICA',
            r'FISICA'
        ],
        'Biologia': [
            r'BIOLOGIA'
        ],
        'Noções de Informática': [
            r'INFORMÁTICA',
            r'INFORMATICA',
            r'NOÇÕES\s+DE\s+INFORMÁTICA'
        ],
        'Noções de Agenda Ambiental': [
            r'AGENDA\s+AMBIENTAL',
            r'AMBIENTAL'
        ],
        'PDPM': [
            r'PDPM'
        ],
        'Legislação': [
            r'LEGISLAÇÃO',
            r'LEGISLACAO',
            r'LEI'
        ],
        'Emergência Pré Hospitalar': [
            r'EMERGÊNCIA\s+PRÉ\s+HOSPITALAR',
            r'EMERGENCIA\s+PRE\s+HOSPITALAR',
            r'PRÉ\s+HOSPITALAR',
            r'PRE\s+HOSPITALAR'
        ]
    }
    
    @classmethod
    def analisar_prova(cls, prova_antiga):
        """Analisa uma prova antiga"""
        try:
            conteudo = prova_antiga.conteudo_texto
            if not conteudo:
                return False
            
            # Identifica disciplinas
            disciplinas_identificadas = cls._identificar_disciplinas(conteudo)
            
            # Salva disciplinas identificadas
            prova_antiga.disciplinas_identificadas = disciplinas_identificadas
            prova_antiga.total_questoes = len(disciplinas_identificadas)
            prova_antiga.processado = True
            prova_antiga.save()
            
            return True
            
        except Exception as e:
            print(f"Erro ao analisar prova: {str(e)}")
            return False
    
    @classmethod
    def _identificar_disciplinas(cls, conteudo):
        """Identifica disciplinas no conteúdo"""
        disciplinas_encontradas = {}
        
        for disciplina, patterns in cls.DISCIPLINAS_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, conteudo, re.IGNORECASE):
                    disciplinas_encontradas[disciplina] = True
                    break
        
        return disciplinas_encontradas
    
    @classmethod
    def _extrair_secao_disciplina(cls, conteudo, disciplina):
        """Extrai seção de uma disciplina específica"""
        patterns = cls.DISCIPLINAS_PATTERNS.get(disciplina, [])
        
        for pattern in patterns:
            match = re.search(pattern, conteudo, re.IGNORECASE | re.MULTILINE)
            if match:
                start_pos = match.start()
                # Busca próxima disciplina ou fim do documento
                next_disciplina_pos = len(conteudo)
                for other_disciplina, other_patterns in cls.DISCIPLINAS_PATTERNS.items():
                    if other_disciplina != disciplina:
                        for other_pattern in other_patterns:
                            next_match = re.search(other_pattern, conteudo[start_pos:], re.IGNORECASE | re.MULTILINE)
                            if next_match:
                                next_disciplina_pos = min(next_disciplina_pos, start_pos + next_match.start())
                
                return conteudo[start_pos:start_pos + next_disciplina_pos]
        
        return None
    
    @classmethod
    def _contar_questoes_na_secao(cls, secao):
        """Conta questões em uma seção específica - versão simplificada"""
        # Conta alternativas (A, B, C, D, E) e divide por 5
        alternativas = len(re.findall(r'^[A-E]\s*\)', secao, re.MULTILINE))
        return alternativas // 5 if alternativas > 0 else 0
    
    @classmethod
    def analisar_padroes_recorrencia(cls, prova_antiga):
        """Analisa padrões de recorrência na prova - versão simplificada"""
        return {}
    
    @classmethod
    def analisar_contabilidade_detalhada(cls, prova_antiga):
        """Função de teste para contabilizar questões - versão simplificada"""
        conteudo = prova_antiga.conteudo_texto
        disciplinas_identificadas = cls._identificar_disciplinas(conteudo)
        
        print("=" * 80)
        print("ANÁLISE DETALHADA DE CONTABILIDADE DE QUESTÕES")
        print("=" * 80)
        print(f"Prova: {prova_antiga.titulo}")
        print(f"Quantidade Total Informada: {prova_antiga.quantidade_total_questoes}")
        print(f"Disciplinas Identificadas: {len(disciplinas_identificadas)}")
        
        total_geral = 0
        
        for disciplina in disciplinas_identificadas.keys():
            print(f"\n📚 DISCIPLINA: {disciplina}")
            print("-" * 50)
            
            # Extrai seção da disciplina
            secao = cls._extrair_secao_disciplina(conteudo, disciplina)
            
            if secao:
                # Contagem simples por alternativas
                alternativas = len(re.findall(r'^[A-E]\s*\)', secao, re.MULTILINE))
                questoes = alternativas // 5 if alternativas > 0 else 0
                total_geral += questoes
                
                print(f"✅ Total de Questões: {questoes}")
                print(f"📊 Alternativas Encontradas: {alternativas}")
            else:
                print("❌ Seção não encontrada")
        
        print("\n" + "=" * 80)
        print("RESUMO GERAL")
        print("=" * 80)
        print(f"Total de Questões Contabilizadas: {total_geral}")
        print(f"Quantidade Informada: {prova_antiga.quantidade_total_questoes}")
        print(f"Diferença: {total_geral - (prova_antiga.quantidade_total_questoes or 0)}")
        print("=" * 80)
        
        return {
            'total_contabilizado': total_geral,
            'quantidade_informada': prova_antiga.quantidade_total_questoes,
            'diferenca': total_geral - (prova_antiga.quantidade_total_questoes or 0)
        }
    
    @classmethod
    def detectar_quantidade_real_questoes(cls, prova_antiga):
        """Detecta a quantidade real de questões - versão simplificada"""
        conteudo = prova_antiga.conteudo_texto
        
        print("=" * 80)
        print("DETECÇÃO INTELIGENTE DE QUANTIDADE DE QUESTÕES")
        print("=" * 80)
        print(f"Prova: {prova_antiga.titulo}")
        
        # Conta alternativas e divide por 5
        alternativas = len(re.findall(r'^[A-E]\s*\)', conteudo, re.MULTILINE))
        quantidade_estimada = alternativas // 5 if alternativas > 0 else 0
        
        # Limita a 80 questões
        if quantidade_estimada > 80:
            quantidade_estimada = 80
        
        print(f"🔍 Alternativas encontradas: {alternativas}")
        print(f"📊 Questões estimadas: {quantidade_estimada}")
        print("=" * 80)
        
        return {
            'quantidade_estimada': quantidade_estimada,
            'alternativas_encontradas': alternativas
        }
