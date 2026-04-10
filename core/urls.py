from django.urls import path
from . import views
from . import views_afirmacoes

app_name = 'core'

urlpatterns = [
    # Páginas principais
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Upload e geração de questões
    path('upload-pdf/', views.upload_pdf, name='upload_pdf'),
    path('gerar-questoes/<int:pdf_id>/', views.gerar_questoes, name='gerar_questoes'),
    
    # Questões
    path('questoes/', views.listar_questoes, name='listar_questoes'),
    path('resolver-questao/<int:questao_id>/', views.resolver_questao, name='resolver_questao'),
    path('resultado-questao/<int:questao_id>/<str:resposta>/<str:acertou>/', views.resultado_questao, name='resultado_questao'),
    
    # Questões de Afirmações
    path('resolver-questao-afirmacoes/<int:questao_id>/', views_afirmacoes.resolver_questao_afirmacoes, name='resolver_questao_afirmacoes'),
    
    # Estatísticas
    path('estatisticas/<int:disciplina_id>/', views.estatisticas_disciplina, name='estatisticas_disciplina'),
    
    # Backup
    path('criar-backup/', views.criar_backup, name='criar_backup'),
    
    # API Status
    path('api-status/', views.api_status, name='api_status'),
    
    # PDFs Duplicados
    path('pdfs-duplicados/', views.pdfs_duplicados, name='pdfs_duplicados'),
    
    # Provas Antigas
    path('provas-antigas/', views.listar_provas_antigas, name='listar_provas_antigas'),
    path('upload-prova-antiga/', views.upload_prova_antiga, name='upload_prova_antiga'),
    path('prova-antiga/<int:prova_id>/', views.detalhar_prova_antiga, name='detalhar_prova_antiga'),
    path('processar-prova-antiga/<int:prova_id>/', views.processar_prova_antiga, name='processar_prova_antiga'),
    path('testar-contabilidade/<int:prova_id>/', views.testar_contabilidade, name='testar_contabilidade'),
    path('detectar-quantidade/<int:prova_id>/', views.detectar_quantidade_questoes, name='detectar_quantidade_questoes'),
    
    # AJAX
    path('ajax/buscar-topicos/', views.ajax_buscar_topicos, name='ajax_buscar_topicos'),
    path('ajax/buscar-materias/', views.ajax_buscar_materias, name='ajax_buscar_materias'),
]
