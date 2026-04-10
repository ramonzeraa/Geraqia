from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg, Case, When, BooleanField
from django.conf import settings
import json

from .models import PDFDocument, Disciplina, Questao, ProvaAntiga, TentativaQuestao
from .services import PDFProcessor, ProvaAntigaAnalyzer, QuestaoGenerator
from .forms import PDFUploadForm, QuestaoFilterForm, ProvaAntigaUploadForm


def home(request):
    """Página inicial do sistema"""
    if request.user.is_authenticated:
        # Estatísticas básicas
        total_questoes = Questao.objects.count()
        total_pdfs = PDFDocument.objects.count()
        total_provas_antigas = ProvaAntiga.objects.count()
        
        # Estatísticas do usuário
        tentativas_usuario = TentativaQuestao.objects.filter(usuario=request.user)
        total_tentativas = tentativas_usuario.count()
        total_acertos = tentativas_usuario.filter(acertou=True).count()
        taxa_acerto_geral = (total_acertos / total_tentativas * 100) if total_tentativas > 0 else 0
        
        # Ranking de disciplinas - UMA entrada por disciplina, sem duplicatas
        ranking_disciplinas = []
        disciplinas_com_tentativas = tentativas_usuario.values_list('questao__disciplina', flat=True).distinct()
        disciplinas_processadas = set()  # Para evitar duplicatas
        
        for disciplina_id in disciplinas_com_tentativas:
            if disciplina_id in disciplinas_processadas:
                continue  # Pular se já processou esta disciplina
                
            disciplina = Disciplina.objects.get(id=disciplina_id)
            disciplinas_processadas.add(disciplina_id)
            
            tentativas_disc = tentativas_usuario.filter(questao__disciplina=disciplina)
            acertos_disc = tentativas_disc.filter(acertou=True).count()
            total_disc = tentativas_disc.count()
            pontos_totais = acertos_disc * 10  # Sistema de pontuação simples
            
            # Buscar matérias reais desta disciplina
            pdfs_da_disciplina = PDFDocument.objects.filter(disciplina=disciplina, materia__isnull=False).exclude(materia='')
            materias_reais = pdfs_da_disciplina.values_list('materia', flat=True).distinct()
            
            ranking_disciplinas.append({
                'disciplina': disciplina,
                'total_acertos': acertos_disc,
                'total_questoes_tentadas': total_disc,
                'pontos_totais': pontos_totais,
                'materias': list(materias_reais)  # Lista das matérias reais
            })
        
        # Ordenar por pontos
        ranking_disciplinas.sort(key=lambda x: x['pontos_totais'], reverse=True)
        
        context = {
            'total_questoes': total_questoes,
            'total_pdfs': total_pdfs,
            'total_provas_antigas': total_provas_antigas,
            'total_tentativas': total_tentativas,
            'total_acertos': total_acertos,
            'taxa_acerto_geral': round(taxa_acerto_geral, 1),
            'ranking_disciplinas': ranking_disciplinas,
            'disciplinas': Disciplina.objects.all(),
        }
    else:
        context = {
            'disciplinas': Disciplina.objects.all(),
        }
    
    return render(request, 'core/home.html', context)


@login_required
def upload_pdf(request):
    """Upload de arquivos PDF"""
    if request.method == 'POST':
        form = PDFUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                arquivo = request.FILES['arquivo']
                pdf_processor = PDFProcessor()
                
                # Calcula hash do arquivo
                hash_arquivo = pdf_processor.calcular_hash_arquivo(arquivo)
                
                # Verifica se já existe um PDF com o mesmo hash
                pdf_existente = pdf_processor.verificar_duplicata(hash_arquivo)
                
                if pdf_existente:
                    # PDF já existe, reutiliza o conteúdo existente
                    messages.info(request, f'PDF já existe no sistema! Reutilizando conteúdo de "{pdf_existente.titulo}".')
                    
                    # Atualiza os metadados do PDF existente se necessário
                    pdf_existente.disciplina = form.cleaned_data.get('disciplina')
                    pdf_existente.materia = form.cleaned_data.get('materia')
                    pdf_existente.save()
                    
                    # Usa o PDF existente para gerar questões
                    pdf_doc = pdf_existente
                    
                    messages.success(request, 'PDF reutilizado com sucesso! Você pode gerar questões a partir do conteúdo existente.')
                else:
                    # PDF novo, processa normalmente
                    conteudo_extraido = pdf_processor.extrair_texto_pdf(arquivo)
                    
                    # Salva o documento
                    pdf_doc = form.save(commit=False)
                    pdf_doc.usuario = request.user
                    pdf_doc.conteudo_extraido = conteudo_extraido
                    pdf_doc.processado = True
                    pdf_doc.hash_arquivo = hash_arquivo
                    pdf_doc.tamanho_arquivo = arquivo.size
                    pdf_doc.save()
                    
                    messages.success(request, 'PDF enviado e processado com sucesso!')
                
                return redirect('core:gerar_questoes', pdf_id=pdf_doc.id)
                
            except Exception as e:
                messages.error(request, f'Erro ao processar PDF: {str(e)}')
    else:
        form = PDFUploadForm()
    
    return render(request, 'core/upload_pdf.html', {'form': form})


@login_required
def gerar_questoes(request, pdf_id):
    """Geração de questões a partir de PDF"""
    pdf_doc = get_object_or_404(PDFDocument, id=pdf_id, usuario=request.user)
    
    if request.method == 'POST':
        try:
            disciplina_id = request.POST.get('disciplina')
            topico_id = request.POST.get('topico')
            nivel_dificuldade = request.POST.get('nivel_dificuldade')
            quantidade = int(request.POST.get('quantidade', 5))
            tipos_questoes = request.POST.getlist('tipos_questoes')
            
            # Se nenhum tipo foi selecionado, usa os padrões
            if not tipos_questoes:
                tipos_questoes = ['multipla_escolha', 'afirmacoes_variadas', 'verdadeiro_falso']
            
            disciplina = get_object_or_404(Disciplina, id=disciplina_id)
            topico = get_object_or_404(Topico, id=topico_id) if topico_id else None
            
            # Gera questões usando IA
            questoes_criadas = QuestaoGenerator.gerar_questoes(
                conteudo_pdf=pdf_doc.conteudo_extraido,
                disciplina=disciplina,
                topico=topico,
                nivel_dificuldade=nivel_dificuldade,
                quantidade=quantidade,
                pdf_origem=pdf_doc,
                tipos_questoes=tipos_questoes
            )
            
            messages.success(request, f'{len(questoes_criadas)} questões geradas com sucesso!')
            return redirect('core:listar_questoes')
            
        except Exception as e:
            error_str = str(e)
            if "quota" in error_str.lower() or "429" in error_str:
                messages.error(request, 'Limite de cota da API Gemini atingido. Tente novamente em algumas horas ou considere fazer upgrade da conta.')
                return redirect('core:api_status')
            else:
                messages.error(request, f'Erro ao gerar questões: {error_str}')
    
    # Busca tópicos da disciplina selecionada
    disciplina_id = request.GET.get('disciplina')
    topicos = []
    if disciplina_id:
        topicos = Topico.objects.filter(disciplina_id=disciplina_id)
    
    context = {
        'pdf_doc': pdf_doc,
        'disciplinas': Disciplina.objects.all(),
        'topicos': topicos,
        'niveis_dificuldade': settings.NIVEIS_DIFICULDADE,
        'tipos_questoes_selecionados': ['multipla_escolha', 'afirmacoes_variadas', 'verdadeiro_falso']  # Padrão marcado
    }
    
    return render(request, 'core/gerar_questoes.html', context)


@login_required
def listar_questoes(request):
    """Lista todas as questões com filtros e ordenação otimizada."""
    form = QuestaoFilterForm(request.GET)
    # Começamos com o QuerySet base, sem executar a consulta ainda
    questoes = Questao.objects.select_related('disciplina').all()

    # Aplica os filtros do formulário
    if form.is_valid():
        disciplina = form.cleaned_data.get('disciplina')
        materia = form.cleaned_data.get('materia')
        nivel_dificuldade = form.cleaned_data.get('nivel_dificuldade')
        tipo = form.cleaned_data.get('tipo')
        busca = form.cleaned_data.get('busca')

        if disciplina:
            questoes = questoes.filter(disciplina=disciplina)
        if materia:
            # Filtra questões baseado na matéria do PDF de origem
            questoes = questoes.filter(pdf_origem__materia__icontains=materia)
        if nivel_dificuldade:
            questoes = questoes.filter(nivel_dificuldade=nivel_dificuldade)
        if tipo:
            questoes = questoes.filter(tipo=tipo)
        if busca:
            questoes = questoes.filter(
                Q(enunciado__icontains=busca) | Q(disciplina__nome__icontains=busca)
            )
        
        # Debug temporário para verificar os tipos disponíveis
        print(f"DEBUG: Filtro tipo aplicado: {tipo}")
        print(f"DEBUG: Tipos disponíveis: {list(questoes.values_list('tipo', flat=True).distinct())}")

    mostrar_respondidas = request.GET.get('mostrar_respondidas', 'false').lower() == 'true'
    
    # ---- LÓGICA PRINCIPAL CORRIGIDA E OTIMIZADA ----
    
    questoes_finais = None
    total_nao_respondidas = 0
    total_respondidas = 0

    if request.user.is_authenticated:
        # Pega os IDs das questões respondidas pelo usuário
        questoes_respondidas_ids = list(TentativaQuestao.objects.filter(usuario=request.user).values_list('questao_id', flat=True))

        # Calcula os totais antes de filtrar para a paginação
        # Nota: Usamos o QuerySet 'questoes' já filtrado pelo formulário
        total_respondidas = questoes.filter(id__in=questoes_respondidas_ids).count()
        total_nao_respondidas = questoes.exclude(id__in=questoes_respondidas_ids).count()

        if mostrar_respondidas:
            # Anota cada questão como respondida ou não
            questoes_finais = questoes.annotate(
                foi_respondida=Case(
                    When(id__in=questoes_respondidas_ids, then=True),
                    default=False,
                    output_field=BooleanField()
                )
            # Ordena: não respondidas primeiro (False), depois as respondidas (True), e então randomiza
            ).order_by('foi_respondida', '?')
        else:
            # Se não for para mostrar, apenas exclui e randomiza
            questoes_finais = questoes.exclude(id__in=questoes_respondidas_ids).order_by('?')
    else:
        # Para usuários não logados, apenas randomiza o queryset filtrado
        questoes_finais = questoes.order_by('?')
        total_nao_respondidas = questoes.count() # Para o não logado, todas são "não respondidas"

    # ---- PAGINAÇÃO (AGORA FUNCIONA CORRETAMENTE) ----
    # O Paginator é aplicado no QuerySet final, que nunca virou uma lista
    paginator = Paginator(questoes_finais, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # É importante passar os IDs para o template para a lógica de exibição
    questoes_respondidas_ids_set = set()
    if request.user.is_authenticated:
        # Passamos um 'set' para o template, que é muito rápido para verificações 'in'
        questoes_respondidas_ids_set = set(questoes_respondidas_ids)

    context = {
        'form': form,
        'page_obj': page_obj,
        'questoes': page_obj, # Passa o objeto da página para o loop no template
        'mostrar_respondidas': mostrar_respondidas,
        'total_nao_respondidas': total_nao_respondidas,
        'total_respondidas': total_respondidas,
        'questoes_respondidas_ids': questoes_respondidas_ids_set, # Passa o set para o template
    }
    
    return render(request, 'core/listar_questoes.html', context)

@login_required
def resolver_questao(request, questao_id):
    """Interface para resolver uma questão específica"""
    questao = get_object_or_404(Questao, id=questao_id)
    
    if request.method == 'POST':
        try:
            resposta_escolhida = request.POST.get('resposta')
            tempo_resposta = int(request.POST.get('tempo_resposta', 0))
            
            if not resposta_escolhida:
                messages.error(request, 'Selecione uma resposta!')
                return redirect('core:resolver_questao', questao_id=questao_id)
            
            # Verifica se a resposta está correta
            resposta_correta = questao.resposta_correta
            acertou = resposta_escolhida == resposta_correta
            
            # Redireciona para página de resultado simples
            return redirect('core:resultado_questao', questao_id=questao_id, resposta=resposta_escolhida, acertou=acertou)
            
        except Exception as e:
            messages.error(request, f'Erro ao registrar resposta: {str(e)}')
    
    # Busca próxima questão não respondida pelo usuário
    if request.user.is_authenticated:
        questoes_respondidas_ids = list(TentativaQuestao.objects.filter(usuario=request.user).values_list('questao_id', flat=True))
        questoes_nao_respondidas = Questao.objects.exclude(id=questao_id).exclude(id__in=questoes_respondidas_ids)
        proxima_questao = questoes_nao_respondidas.order_by('?').first()
        
        # Se não houver questões não respondidas, pega qualquer questão que não seja a atual
        if not proxima_questao:
            proxima_questao = Questao.objects.exclude(id=questao_id).order_by('?').first()
    else:
        # Para usuários não logados, pega qualquer questão que não seja a atual
        proxima_questao = Questao.objects.exclude(id=questao_id).order_by('?').first()
    
    context = {
        'questao': questao,
        'proxima_questao': proxima_questao,
        'alternativas_display': questao.get_alternativas_display(),
    }
    
    return render(request, 'core/resolver_questao.html', context)


@login_required
def resultado_questao(request, questao_id, resposta, acertou):
    """Mostra resultado da tentativa de resolução - versão simplificada"""
    questao = get_object_or_404(Questao, id=questao_id)
    
    # Converte string para boolean
    acertou_bool = acertou.lower() == 'true'
    
    # Salva ou atualiza a tentativa do usuário
    tentativa, created = TentativaQuestao.objects.update_or_create(
        usuario=request.user,
        questao=questao,
        defaults={
            'resposta_escolhida': resposta,
            'acertou': acertou_bool
        }
    )
    
    # Atualiza estatísticas da questão
    questao.total_tentativas += 1
    if acertou_bool:
        questao.total_acertos += 1
    questao.save()
    
    # Busca próxima questão não respondida pelo usuário
    questoes_respondidas_ids = list(TentativaQuestao.objects.filter(usuario=request.user).values_list('questao_id', flat=True))
    
    # Busca questões não respondidas, excluindo a atual
    questoes_nao_respondidas = Questao.objects.exclude(
        id=questao_id
    ).exclude(
        id__in=questoes_respondidas_ids
    )
    
    # Tenta pegar uma questão não respondida aleatória
    proxima_questao = questoes_nao_respondidas.order_by('?').first()
    
    # Se não houver questões não respondidas, pega qualquer questão que não seja a atual
    if not proxima_questao:
        proxima_questao = Questao.objects.exclude(id=questao_id).order_by('?').first()
    
    context = {
        'questao': questao,
        'resposta_escolhida': resposta,
        'acertou': acertou_bool,
        'proxima_questao': proxima_questao,
    }
    
    return render(request, 'core/resultado_questao.html', context)


@login_required
def dashboard(request):
    """Dashboard com estatísticas completas"""
    # Filtros de data
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    
    # Estatísticas básicas
    total_questoes = Questao.objects.count()
    
    # Estatísticas do usuário
    tentativas_usuario = TentativaQuestao.objects.filter(usuario=request.user)
    total_tentativas = tentativas_usuario.count()
    total_acertos = tentativas_usuario.filter(acertou=True).count()
    taxa_acerto = (total_acertos / total_tentativas * 100) if total_tentativas > 0 else 0
    
    # Aplicar filtros de data se fornecidos
    if data_inicio:
        tentativas_usuario = tentativas_usuario.filter(data_tentativa__date__gte=data_inicio)
    if data_fim:
        tentativas_usuario = tentativas_usuario.filter(data_tentativa__date__lte=data_fim)
    
    # Estatísticas por disciplina - apenas disciplinas com tentativas
    estatisticas_disciplinas = []
    disciplinas_com_tentativas = tentativas_usuario.values_list('questao__disciplina', flat=True).distinct()
    
    for disciplina_id in disciplinas_com_tentativas:
        disciplina = Disciplina.objects.get(id=disciplina_id)
        tentativas_disc = tentativas_usuario.filter(questao__disciplina=disciplina)
        acertos_disc = tentativas_disc.filter(acertou=True).count()
        total_disc = tentativas_disc.count()
        taxa_disc = (acertos_disc / total_disc * 100) if total_disc > 0 else 0
        
        estatisticas_disciplinas.append({
            'disciplina_nome': disciplina.nome,
            'tentativas': total_disc,
            'acertos': acertos_disc,
            'erros': total_disc - acertos_disc,
            'taxa_acerto': round(taxa_disc, 1),
            'pontos': acertos_disc * 10  # Sistema de pontuação simples
        })
    
    # Ordenar por taxa de acerto
    estatisticas_disciplinas.sort(key=lambda x: x['taxa_acerto'], reverse=True)
    
    # Estatísticas hierárquicas - UMA entrada por disciplina com todas as matérias
    estatisticas_hierarquicas = []
    disciplinas_processadas = set()  # Para evitar duplicatas
    
    for disciplina_id in disciplinas_com_tentativas:
        if disciplina_id in disciplinas_processadas:
            continue  # Pular se já processou esta disciplina
            
        disciplina = Disciplina.objects.get(id=disciplina_id)
        disciplinas_processadas.add(disciplina_id)
        
        tentativas_disc = tentativas_usuario.filter(questao__disciplina=disciplina)
        acertos_disc = tentativas_disc.filter(acertou=True).count()
        total_disc = tentativas_disc.count()
        taxa_disc = (acertos_disc / total_disc * 100) if total_disc > 0 else 0
        
        # Buscar TODAS as matérias reais desta disciplina (dos PDFs que geraram questões)
        pdfs_da_disciplina = PDFDocument.objects.filter(disciplina=disciplina, materia__isnull=False).exclude(materia='')
        materias_reais = pdfs_da_disciplina.values_list('materia', flat=True).distinct()
        
        # Estatísticas por matéria real - TODAS as matérias, mesmo sem tentativas
        materias_com_estatisticas = []
        for materia_nome in materias_reais:
            # Buscar questões desta disciplina que vieram de PDFs com esta matéria
            questoes_da_materia = Questao.objects.filter(
                disciplina=disciplina,
                pdf_origem__materia=materia_nome
            )
            
            # Buscar tentativas do usuário para essas questões específicas
            tentativas_materia = tentativas_usuario.filter(questao__in=questoes_da_materia)
            acertos_materia = tentativas_materia.filter(acertou=True).count()
            total_materia = tentativas_materia.count()
            taxa_materia = (acertos_materia / total_materia * 100) if total_materia > 0 else 0
            
            # Incluir TODAS as matérias, mesmo sem tentativas (para mostrar que existem)
            materias_com_estatisticas.append({
                'materia_nome': materia_nome,
                'tentativas': total_materia,
                'acertos': acertos_materia,
                'taxa_acerto': round(taxa_materia, 1),
                'tem_tentativas': total_materia > 0  # Flag para destacar matérias com tentativas
            })
        
        # Ordenar matérias: primeiro as com tentativas (por taxa de acerto), depois as sem tentativas
        materias_com_estatisticas.sort(key=lambda x: (x['tem_tentativas'], x['taxa_acerto']), reverse=True)
        
        estatisticas_hierarquicas.append({
            'disciplina_nome': disciplina.nome,
            'peso': 1,  # Peso padrão
            'tentativas': total_disc,
            'acertos': acertos_disc,
            'taxa_acerto': round(taxa_disc, 1),
            'pontos': acertos_disc * 10,
            'materias': materias_com_estatisticas  # TODAS as matérias da disciplina
        })
    
    # Ordenar por pontos
    estatisticas_hierarquicas.sort(key=lambda x: x['pontos'], reverse=True)
    
    # Dados para gráficos de evolução temporal (últimos 30 dias)
    from datetime import datetime, timedelta
    
    data_fim_evolucao = datetime.now().date()
    data_inicio_evolucao = data_fim_evolucao - timedelta(days=30)
    
    evolucao_data = []
    evolucao_acertos = []
    evolucao_tentativas = []
    
    for i in range(30):
        data_atual = data_inicio_evolucao + timedelta(days=i)
        tentativas_dia = tentativas_usuario.filter(data_tentativa__date=data_atual)
        acertos_dia = tentativas_dia.filter(acertou=True).count()
        total_dia = tentativas_dia.count()
        
        evolucao_data.append(data_atual.strftime('%d/%m'))
        evolucao_acertos.append(acertos_dia)
        evolucao_tentativas.append(total_dia)
    
    # Top 10 matérias mais estudadas (simplificado - sem matérias por enquanto)
    materias_performance = []
    
    context = {
        'total_questoes': total_questoes,
        'total_tentativas': total_tentativas,
        'total_acertos': total_acertos,
        'taxa_acerto': round(taxa_acerto, 1),
        'estatisticas_disciplinas': estatisticas_disciplinas,
        'estatisticas_hierarquicas': estatisticas_hierarquicas,
        'evolucao_data': evolucao_data,
        'evolucao_acertos': evolucao_acertos,
        'evolucao_tentativas': evolucao_tentativas,
        'materias_performance': materias_performance,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
    }
    
    return render(request, 'core/dashboard.html', context)


@login_required
def estatisticas_disciplina(request, disciplina_id):
    """Estatísticas detalhadas de uma disciplina específica - versão simplificada"""
    disciplina = get_object_or_404(Disciplina, id=disciplina_id)
    
    # Questões desta disciplina
    questoes_disciplina = Questao.objects.filter(disciplina=disciplina)
    
    context = {
        'disciplina': disciplina,
        'questoes_disciplina': questoes_disciplina,
        'total_questoes': questoes_disciplina.count(),
    }
    
    return render(request, 'core/estatisticas_disciplina.html', context)


@login_required
def criar_backup(request):
    """Cria backup do banco de dados - versão simplificada"""
    messages.info(request, 'Sistema de backup temporariamente desabilitado.')
    return redirect('core:dashboard')


def api_status(request):
    """Página de status da API"""
    return render(request, 'core/api_status.html')


@login_required
def pdfs_duplicados(request):
    """Lista PDFs duplicados no sistema"""
    # Busca PDFs com mesmo hash
    from django.db.models import Count
    pdfs_duplicados = PDFDocument.objects.filter(
        hash_arquivo__isnull=False
    ).values('hash_arquivo').annotate(
        total=Count('id')
    ).filter(total__gt=1)
    
    # Para cada hash duplicado, busca os PDFs
    grupos_duplicados = []
    for grupo in pdfs_duplicados:
        pdfs = PDFDocument.objects.filter(hash_arquivo=grupo['hash_arquivo']).order_by('data_upload')
        grupos_duplicados.append({
            'hash': grupo['hash_arquivo'],
            'total': grupo['total'],
            'pdfs': pdfs
        })
    
    context = {
        'grupos_duplicados': grupos_duplicados,
        'total_duplicados': len(grupos_duplicados)
    }
    
    return render(request, 'core/pdfs_duplicados.html', context)


def ajax_buscar_topicos(request):
    """AJAX para buscar tópicos de uma disciplina"""
    disciplina_id = request.GET.get('disciplina_id')
    topicos = Topico.objects.filter(disciplina_id=disciplina_id).values('id', 'nome')
    return JsonResponse(list(topicos), safe=False)


def ajax_buscar_materias(request):
    """AJAX para buscar matérias únicas de uma disciplina"""
    disciplina_id = request.GET.get('disciplina_id')
    if disciplina_id:
        # Busca matérias únicas dos PDFs desta disciplina
        materias_unicas = PDFDocument.objects.filter(
            disciplina_id=disciplina_id,
            materia__isnull=False
        ).values_list('materia', flat=True).distinct().order_by('materia')
        
        materias = [{'id': m, 'nome': m} for m in materias_unicas if m]
    else:
        materias = []
    return JsonResponse(materias, safe=False)


@login_required
def listar_provas_antigas(request):
    """Lista todas as provas antigas"""
    provas = ProvaAntiga.objects.all().order_by('-ano', '-data_upload')
    
    # Filtros
    banca = request.GET.get('banca')
    tipo = request.GET.get('tipo')
    ano = request.GET.get('ano')
    
    if banca:
        provas = provas.filter(banca=banca)
    if tipo:
        provas = provas.filter(tipo=tipo)
    if ano:
        provas = provas.filter(ano=ano)
    
    # Paginação
    paginator = Paginator(provas, 10)
    page_number = request.GET.get('page')
    provas = paginator.get_page(page_number)
    
    context = {
        'provas': provas,
        'bancas': ProvaAntiga.BANCA_CHOICES,
        'tipos': ProvaAntiga.TIPO_CHOICES,
        'anos': range(2020, 2026),  # Últimos 5 anos
    }
    
    return render(request, 'core/listar_provas_antigas.html', context)


@login_required
def upload_prova_antiga(request):
    """Upload de prova antiga"""
    if request.method == 'POST':
        form = ProvaAntigaUploadForm(request.POST, request.FILES)
        if form.is_valid():
            prova = form.save()
            
            # Processa o PDF automaticamente
            try:
                with open(prova.arquivo_pdf.path, 'rb') as arquivo:
                    conteudo = PDFProcessor.extrair_texto_pdf(arquivo)
                    prova.conteudo_texto = conteudo
                    prova.save()
                
                messages.success(request, f'Prova "{prova.titulo}" enviada com sucesso!')
                return redirect('core:listar_provas_antigas')
            except Exception as e:
                messages.error(request, f'Erro ao processar PDF: {str(e)}')
                return redirect('core:upload_prova_antiga')
    else:
        form = ProvaAntigaUploadForm()
    
    context = {
        'form': form,
        'title': 'Upload de Prova Antiga'
    }
    
    return render(request, 'core/upload_prova_antiga.html', context)


@login_required
def detalhar_prova_antiga(request, prova_id):
    """Detalhes de uma prova antiga"""
    prova = get_object_or_404(ProvaAntiga, id=prova_id)
    
    context = {
        'prova': prova,
    }
    
    return render(request, 'core/detalhar_prova_antiga.html', context)


@login_required
def processar_prova_antiga(request, prova_id):
    """Processa uma prova antiga para análise de padrões"""
    prova = get_object_or_404(ProvaAntiga, id=prova_id)
    
    if request.method == 'POST':
        try:
            # Analisa a prova usando o analisador inteligente
            sucesso = ProvaAntigaAnalyzer.analisar_prova(prova)
            
            if sucesso:
                # Analisa padrões de recorrência
                ProvaAntigaAnalyzer.analisar_padroes_recorrencia(prova)
                
                messages.success(request, f'Prova "{prova.titulo}" processada com sucesso!')
                messages.info(request, f'Identificadas {prova.get_disciplinas_count()} disciplinas com {prova.total_questoes} questões.')
            else:
                messages.error(request, 'Erro ao processar a prova. Verifique se o conteúdo foi extraído corretamente.')
                
        except Exception as e:
            messages.error(request, f'Erro ao processar prova: {str(e)}')
    
    return redirect('core:detalhar_prova_antiga', prova_id=prova_id)


@login_required
def testar_contabilidade(request, prova_id):
    """Testa a contabilidade de questões de uma prova"""
    try:
        prova_antiga = ProvaAntiga.objects.get(id=prova_id)
        
        # Executa análise detalhada
        resultado = ProvaAntigaAnalyzer.analisar_contabilidade_detalhada(prova_antiga)
        
        return JsonResponse({
            'success': True,
            'resultado': resultado
        })
        
    except ProvaAntiga.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Prova não encontrada'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def detectar_quantidade_questoes(request, prova_id):
    """Detecta a quantidade real de questões de uma prova"""
    try:
        prova_antiga = ProvaAntiga.objects.get(id=prova_id)
        
        # Executa detecção inteligente
        resultado = ProvaAntigaAnalyzer.detectar_quantidade_real_questoes(prova_antiga)
        
        return JsonResponse({
            'success': True,
            'resultado': resultado
        })
        
    except ProvaAntiga.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Prova não encontrada'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })