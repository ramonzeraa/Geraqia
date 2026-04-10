from django import template

register = template.Library()

@register.filter
def questao_respondida(questao_id, questoes_respondidas_ids):
    """Verifica se uma questão foi respondida pelo usuário"""
    if not questoes_respondidas_ids:
        return False
    return questao_id in questoes_respondidas_ids

