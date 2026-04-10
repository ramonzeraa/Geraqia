from django.contrib import admin
from .models import PDFDocument, Disciplina, Questao, ProvaAntiga, TentativaQuestao


@admin.register(PDFDocument)
class PDFDocumentAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'usuario', 'data_upload', 'processado']
    list_filter = ['processado', 'data_upload', 'usuario']
    search_fields = ['titulo', 'conteudo_extraido']
    readonly_fields = ['data_upload']


@admin.register(Disciplina)
class DisciplinaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'peso', 'questoes_prova']
    list_editable = ['peso', 'questoes_prova']


@admin.register(Questao)
class QuestaoAdmin(admin.ModelAdmin):
    list_display = [
        'disciplina', 'nivel_dificuldade', 'tipo', 
        'total_tentativas', 'total_acertos', 'taxa_acerto'
    ]
    list_filter = ['disciplina', 'nivel_dificuldade', 'tipo', 'data_criacao']
    search_fields = ['enunciado', 'disciplina__nome']
    readonly_fields = ['data_criacao', 'total_tentativas', 'total_acertos', 'taxa_acerto']
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('disciplina', 'nivel_dificuldade', 'tipo')
        }),
        ('Conteúdo da Questão', {
            'fields': ('enunciado', 'alternativas', 'resposta_correta', 'explicacao')
        }),
        ('Detalhes Adicionais', {
            'fields': ('justificativa_alternativas', 'referencia_pdf', 'pdf_origem')
        }),
        ('Estatísticas', {
            'fields': ('total_tentativas', 'total_acertos', 'taxa_acerto'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TentativaQuestao)
class TentativaQuestaoAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'questao', 'resposta_escolhida', 'acertou', 'data_tentativa']
    list_filter = ['acertou', 'data_tentativa', 'questao__disciplina']
    search_fields = ['usuario__username', 'questao__enunciado']
    readonly_fields = ['data_tentativa']


@admin.register(ProvaAntiga)
class ProvaAntigaAdmin(admin.ModelAdmin):
    list_display = [
        'titulo', 'ano', 'banca', 'tipo', 'total_questoes', 
        'get_disciplinas_count', 'get_quantidade_questoes', 'processado', 'data_upload'
    ]
    list_filter = ['banca', 'tipo', 'ano', 'processado', 'data_upload']
    search_fields = ['titulo', 'observacoes']
    readonly_fields = [
        'data_upload', 'data_processamento', 'total_questoes',
        'disciplinas_identificadas', 'distribuicao_questoes', 'quantidade_questoes_por_disciplina', 'padroes_recorrencia'
    ]
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('titulo', 'ano', 'banca', 'tipo', 'arquivo_pdf')
        }),
        ('Configuração de Questões', {
            'fields': ('quantidade_total_questoes',),
            'classes': ('collapse',)
        }),
        ('Análise Automática', {
            'fields': ('processado', 'data_processamento', 'total_questoes'),
            'classes': ('collapse',)
        }),
        ('Disciplinas Identificadas', {
            'fields': ('disciplinas_identificadas',),
            'classes': ('collapse',)
        }),
        ('Distribuição de Questões', {
            'fields': ('distribuicao_questoes',),
            'classes': ('collapse',)
        }),
        ('Quantidade de Questões por Disciplina', {
            'fields': ('quantidade_questoes_por_disciplina',),
            'classes': ('collapse',)
        }),
        ('Padrões de Recorrência', {
            'fields': ('padroes_recorrencia',),
            'classes': ('collapse',)
        }),
        ('Conteúdo e Observações', {
            'fields': ('conteudo_texto', 'observacoes'),
            'classes': ('collapse',)
        }),
        ('Metadados', {
            'fields': ('data_upload',),
            'classes': ('collapse',)
        }),
    )
    
    def get_disciplinas_count(self, obj):
        """Retorna o número de disciplinas identificadas"""
        return obj.get_disciplinas_count()
    get_disciplinas_count.short_description = 'Disciplinas'
    get_disciplinas_count.admin_order_field = 'disciplinas_identificadas'
    
    def get_quantidade_questoes(self, obj):
        """Retorna a quantidade de questões por disciplina"""
        if obj.quantidade_questoes_por_disciplina:
            total = sum(obj.quantidade_questoes_por_disciplina.values())
            return f"{total} questões"
        return "Não processado"
    get_quantidade_questoes.short_description = 'Qtd. Questões'
    get_quantidade_questoes.admin_order_field = 'quantidade_questoes_por_disciplina'