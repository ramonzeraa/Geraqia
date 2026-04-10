from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
import json


class PDFDocument(models.Model):
    """Modelo para armazenar documentos PDF e seu conteúdo extraído"""
    titulo = models.CharField(max_length=200, verbose_name="Título")
    arquivo = models.FileField(upload_to='pdfs/', verbose_name="Arquivo PDF")
    conteudo_extraido = models.TextField(verbose_name="Conteúdo Extraído")
    data_upload = models.DateTimeField(auto_now_add=True, verbose_name="Data de Upload")
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Usuário")
    processado = models.BooleanField(default=False, verbose_name="Processado")
    disciplina = models.ForeignKey('Disciplina', on_delete=models.CASCADE, null=True, blank=True, verbose_name="Disciplina")
    materia = models.CharField(max_length=200, null=True, blank=True, verbose_name="Matéria/Assunto")
    hash_arquivo = models.CharField(max_length=64, unique=True, null=True, blank=True, verbose_name="Hash do Arquivo", help_text="SHA-256 do arquivo para detecção de duplicatas")
    tamanho_arquivo = models.BigIntegerField(null=True, blank=True, verbose_name="Tamanho do Arquivo (bytes)")
    
    class Meta:
        verbose_name = "Documento PDF"
        verbose_name_plural = "Documentos PDF"
        ordering = ['-data_upload']
    
    def __str__(self):
        return self.titulo


class Disciplina(models.Model):
    """Modelo para disciplinas do concurso"""
    codigo = models.CharField(max_length=50, unique=True, verbose_name="Código")
    nome = models.CharField(max_length=100, verbose_name="Nome")
    peso = models.IntegerField(default=1, verbose_name="Peso")
    questoes_prova = models.IntegerField(default=0, verbose_name="Questões na Prova")
    
    class Meta:
        verbose_name = "Disciplina"
        verbose_name_plural = "Disciplinas"
        ordering = ['nome']
    
    def __str__(self):
        return self.nome




class Questao(models.Model):
    """Modelo para questões geradas pela IA"""
    NIVEL_CHOICES = [
        ('fixacao', 'Fixação - Conteúdo do PDF'),
        ('medio', 'Médio - Aplicação Lógica'),
        ('dificil', 'Difícil - Lógica + Raciocínio Aplicado'),
        ('nivel_banca', 'Nível da Banca - Questão Real'),
    ]
    
    TIPO_CHOICES = [
        ('multipla_escolha', 'Múltipla Escolha'),
        ('certo_errado', 'Certo/Errado'),
        ('afirmacoes', 'Afirmações'),
        ('afirmacoes_variadas', 'Afirmações com Alternativas Variadas'),
        ('verdadeiro_falso', 'Verdadeiro ou Falso com Sequência'),
    ]
    
    INSTRUCAO_TIPO_CHOICES = [
        ('correto', 'Está CORRETO o que se afirma'),
        ('incorreto', 'Está INCORRETO o que se afirma'),
        ('corretos', 'Estão CORRETOS os itens'),
        ('incorretos', 'Estão INCORRETOS os itens'),
        ('correto_nos', 'Está CORRETO o que se afirma nos itens'),
        ('incorreto_nos', 'Está INCORRETO o que se afirma nos itens'),
    ]
    
    enunciado = models.TextField(verbose_name="Enunciado")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='multipla_escolha', verbose_name="Tipo")
    alternativas = models.JSONField(verbose_name="Alternativas")  # Lista de alternativas
    resposta_correta = models.CharField(max_length=1, verbose_name="Resposta Correta")
    explicacao = models.TextField(verbose_name="Explicação")
    justificativa_alternativas = models.JSONField(default=dict, verbose_name="Justificativa das Alternativas")
    referencia_pdf = models.TextField(blank=True, null=True, verbose_name="Referência no PDF")
    
    disciplina = models.ForeignKey(Disciplina, on_delete=models.CASCADE, verbose_name="Disciplina")
    nivel_dificuldade = models.CharField(max_length=20, choices=NIVEL_CHOICES, verbose_name="Nível de Dificuldade")
    
    pdf_origem = models.ForeignKey(PDFDocument, on_delete=models.CASCADE, verbose_name="PDF de Origem")
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name="Data de Criação")
    
    # Estatísticas
    total_tentativas = models.IntegerField(default=0, verbose_name="Total de Tentativas")
    total_acertos = models.IntegerField(default=0, verbose_name="Total de Acertos")
    
    # Controle de duplicatas
    hash_conteudo = models.CharField(max_length=64, unique=True, null=True, blank=True, verbose_name="Hash do Conteúdo", help_text="Hash SHA-256 do enunciado para evitar duplicatas")
    
    # Campos específicos para questões de afirmações
    afirmacoes = models.JSONField(null=True, blank=True, verbose_name="Afirmações", help_text="Lista de afirmações para questões do tipo 'Afirmações'")
    instrucao_tipo = models.CharField(max_length=20, choices=INSTRUCAO_TIPO_CHOICES, null=True, blank=True, verbose_name="Tipo de Instrução", help_text="Tipo de instrução para questões de afirmações")
    instrucao_texto = models.CharField(max_length=200, null=True, blank=True, verbose_name="Texto da Instrução", help_text="Texto personalizado da instrução")
    
    # Campos específicos para questões V ou F com sequência
    sequencia_resposta = models.CharField(max_length=10, null=True, blank=True, verbose_name="Sequência V/F", help_text="Sequência de V/F para questões do tipo 'Verdadeiro ou Falso' (ex: V-V-F-V)")
    instrucao_vf = models.CharField(max_length=200, null=True, blank=True, verbose_name="Instrução V/F", help_text="Instrução específica para questões V/F (ex: 'a sequência correta obtida no sentido de cima para baixo')")
    
    class Meta:
        verbose_name = "Questão"
        verbose_name_plural = "Questões"
        ordering = ['-data_criacao']
    
    def __str__(self):
        return f"{self.disciplina.nome} - {self.get_nivel_dificuldade_display()}"
    
    @property
    def taxa_acerto(self):
        """Calcula a taxa de acerto da questão"""
        if self.total_tentativas == 0:
            return 0
        return round((self.total_acertos / self.total_tentativas) * 100, 2)
    
    def get_alternativas_display(self):
        """Retorna as alternativas formatadas para exibição"""
        if isinstance(self.alternativas, list):
            return {chr(65 + i): alt for i, alt in enumerate(self.alternativas)}
        return self.alternativas
    
    def get_afirmacoes_display(self):
        """Retorna as afirmações formatadas para exibição"""
        if not self.afirmacoes:
            return []
        if isinstance(self.afirmacoes, list):
            return {f"{i+1}": afirmacao for i, afirmacao in enumerate(self.afirmacoes)}
        return self.afirmacoes
    
    def get_instrucao_display(self):
        """Retorna o texto da instrução formatado"""
        if self.instrucao_texto:
            return self.instrucao_texto
        if self.instrucao_tipo:
            return dict(self.INSTRUCAO_TIPO_CHOICES).get(self.instrucao_tipo, "Está CORRETO o que se afirma:")
        return "Está CORRETO o que se afirma:"
    
    def gerar_alternativas_variadas(self):
        """Gera alternativas variadas para questões de afirmações"""
        if not self.afirmacoes or len(self.afirmacoes) < 2:
            return []
        
        import random
        num_afirmacoes = len(self.afirmacoes)
        alternativas = []
        
        # Gera diferentes combinações de afirmações
        combinacoes_possiveis = []
        
        # Combinações individuais
        for i in range(num_afirmacoes):
            combinacoes_possiveis.append(f"{i+1}, apenas.")
        
        # Combinações de pares
        for i in range(num_afirmacoes):
            for j in range(i+1, num_afirmacoes):
                if num_afirmacoes > 2:
                    combinacoes_possiveis.append(f"{i+1} e {j+1}, apenas.")
                else:
                    combinacoes_possiveis.append(f"{i+1} e {j+1}.")
        
        # Combinações de três (se houver 4+ afirmações)
        if num_afirmacoes >= 4:
            for i in range(num_afirmacoes):
                for j in range(i+1, num_afirmacoes):
                    for k in range(j+1, num_afirmacoes):
                        combinacoes_possiveis.append(f"{i+1}, {j+1} e {k+1}.")
        
        # Combinação de todas
        if num_afirmacoes >= 3:
            todas = ", ".join([str(i+1) for i in range(num_afirmacoes)])
            combinacoes_possiveis.append(f"{todas}.")
        
        # Embaralha e pega 4 alternativas
        random.shuffle(combinacoes_possiveis)
        alternativas = combinacoes_possiveis[:4]
        
        # Garante que temos pelo menos 4 alternativas
        while len(alternativas) < 4:
            alternativas.append(f"{random.randint(1, num_afirmacoes)}, apenas.")
        
        return alternativas
    
    def gerar_alternativas_vf(self):
        """Gera alternativas para questões V ou F com sequência"""
        if not self.afirmacoes or len(self.afirmacoes) < 2:
            return []
        
        import random
        num_afirmacoes = len(self.afirmacoes)
        alternativas = []
        sequencias_geradas = set()
        
        # Gera todas as possíveis sequências de V/F
        todas_sequencias = []
        for i in range(2 ** num_afirmacoes):
            sequencia = ""
            for j in range(num_afirmacoes):
                if i & (1 << j):
                    sequencia += "V"
                else:
                    sequencia += "F"
            todas_sequencias.append(sequencia)
        
        # Embaralha as sequências para ter variedade
        random.shuffle(todas_sequencias)
        
        # Pega as primeiras 5 sequências únicas
        for sequencia in todas_sequencias:
            if sequencia not in sequencias_geradas:
                alternativas.append(sequencia)
                sequencias_geradas.add(sequencia)
                if len(alternativas) >= 5:
                    break
        
        # Se não temos 5 sequências únicas, gera mais aleatoriamente
        while len(alternativas) < 5:
            sequencia = ""
            for _ in range(num_afirmacoes):
                sequencia += random.choice(['V', 'F'])
            if sequencia not in sequencias_geradas:
                alternativas.append(sequencia)
                sequencias_geradas.add(sequencia)
        
        return alternativas[:5]  # Garante que retorna exatamente 5 alternativas




class TentativaQuestao(models.Model):
    """Modelo para rastrear tentativas de resolução de questões"""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Usuário")
    questao = models.ForeignKey(Questao, on_delete=models.CASCADE, verbose_name="Questão")
    resposta_escolhida = models.CharField(max_length=1, verbose_name="Resposta Escolhida")
    acertou = models.BooleanField(verbose_name="Acertou")
    data_tentativa = models.DateTimeField(auto_now_add=True, verbose_name="Data da Tentativa")
    
    class Meta:
        verbose_name = "Tentativa de Questão"
        verbose_name_plural = "Tentativas de Questões"
        ordering = ['-data_tentativa']
        unique_together = ['usuario', 'questao']  # Uma tentativa por usuário por questão
    
    def __str__(self):
        return f"{self.usuario.username} - {self.questao.id} - {'Acertou' if self.acertou else 'Errou'}"


class ProvaAntiga(models.Model):
    """Modelo para armazenar provas antigas da IDECAN e outras bancas"""
    TIPO_CHOICES = [
        ('prova_oficial', 'Prova Oficial'),
        ('simulado', 'Simulado'),
        ('edital', 'Edital'),
        ('outro', 'Outro'),
    ]
    
    BANCA_CHOICES = [
        ('idecan', 'IDECAN'),
        ('cespe', 'CESPE'),
        ('fcc', 'FCC'),
        ('fcc', 'FGV'),
        ('outro', 'Outro'),
    ]
    
    titulo = models.CharField(max_length=300, verbose_name="Título da Prova")
    ano = models.IntegerField(verbose_name="Ano")
    banca = models.CharField(max_length=50, choices=BANCA_CHOICES, default='idecan', verbose_name="Banca")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='prova_oficial', verbose_name="Tipo")
    arquivo_pdf = models.FileField(upload_to='provas_antigas/', verbose_name="Arquivo PDF")
    conteudo_texto = models.TextField(blank=True, null=True, verbose_name="Conteúdo Extraído")
    data_upload = models.DateTimeField(auto_now_add=True, verbose_name="Data de Upload")
    
    # Análise automática
    disciplinas_identificadas = models.JSONField(default=dict, blank=True, verbose_name="Disciplinas Identificadas")
    padroes_recorrencia = models.JSONField(default=dict, blank=True, verbose_name="Padrões de Recorrência")
    distribuicao_questoes = models.JSONField(default=dict, blank=True, verbose_name="Distribuição de Questões")
    total_questoes = models.IntegerField(default=0, verbose_name="Total de Questões")
    quantidade_questoes_por_disciplina = models.JSONField(default=dict, blank=True, verbose_name="Quantidade de Questões por Disciplina")
    quantidade_total_questoes = models.IntegerField(blank=True, null=True, verbose_name="Quantidade Total de Questões (1-80)")
    
    # Metadados
    processado = models.BooleanField(default=False, verbose_name="Processado")
    data_processamento = models.DateTimeField(blank=True, null=True, verbose_name="Data de Processamento")
    observacoes = models.TextField(blank=True, null=True, verbose_name="Observações")
    
    class Meta:
        verbose_name = "Prova Antiga"
        verbose_name_plural = "Provas Antigas"
        ordering = ['-ano', '-data_upload']
    
    def __str__(self):
        return f"{self.titulo} ({self.ano}) - {self.get_banca_display()}"
    
    def get_disciplinas_count(self):
        """Retorna o número de disciplinas identificadas"""
        return len(self.disciplinas_identificadas) if self.disciplinas_identificadas else 0
    
    def get_questoes_por_disciplina(self, disciplina_nome):
        """Retorna o número de questões de uma disciplina específica"""
        if self.distribuicao_questoes and disciplina_nome in self.distribuicao_questoes:
            return self.distribuicao_questoes[disciplina_nome]
        return 0