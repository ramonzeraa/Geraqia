from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import Questao, TentativaQuestao




@login_required
def resolver_questao_afirmacoes(request, questao_id):
    """Interface para resolver uma questão de afirmações"""
    questao = get_object_or_404(Questao, id=questao_id, tipo__in=['afirmacoes', 'afirmacoes_variadas', 'verdadeiro_falso'])
    
    if request.method == 'POST':
        try:
            resposta_escolhida = request.POST.get('resposta')
            
            if not resposta_escolhida:
                messages.error(request, 'Selecione uma resposta!')
                return redirect('core:resolver_questao_afirmacoes', questao_id=questao_id)
            
            # Verifica se a resposta está correta
            resposta_correta = questao.resposta_correta
            acertou = resposta_escolhida == resposta_correta
            
            # Redireciona para página de resultado
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
        'afirmacoes_display': questao.get_afirmacoes_display(),
        'instrucao_display': questao.get_instrucao_display(),
        'alternativas_display': questao.get_alternativas_display(),
    }
    
    return render(request, 'core/resolver_questao_afirmacoes.html', context)
