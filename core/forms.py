from django import forms
from .models import PDFDocument, Disciplina, Questao, ProvaAntiga


class PDFUploadForm(forms.ModelForm):
    """Formulário para upload de PDFs"""
    
    class Meta:
        model = PDFDocument
        fields = ['titulo', 'disciplina', 'materia', 'arquivo']
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Digite um título para o PDF...'
            }),
            'disciplina': forms.Select(attrs={
                'class': 'form-select'
            }),
            'materia': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex.: Funções, Citologia, Leis de Newton...',
                'id': 'id_materia'
            }),
            'arquivo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf'
            })
        }
    
    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        if arquivo:
            if not arquivo.name.lower().endswith('.pdf'):
                raise forms.ValidationError('Apenas arquivos PDF são permitidos.')
            if arquivo.size > 10 * 1024 * 1024:  # 10MB
                raise forms.ValidationError('O arquivo deve ter no máximo 10MB.')
        return arquivo


class QuestaoFilterForm(forms.Form):
    """Formulário para filtrar questões"""
    
    NIVEL_CHOICES = [('', 'Todos os níveis')] + [
        (k, v) for k, v in {
            'fixacao': 'Fixação - Conteúdo do PDF',
            'medio': 'Médio - Aplicação Lógica',
            'dificil': 'Difícil - Lógica + Raciocínio Aplicado',
            'nivel_banca': 'Nível da Banca - Questão Real',
        }.items()
    ]
    
    TIPO_CHOICES = [
        ('', 'Todos os tipos'),
        ('multipla_escolha', 'Múltipla Escolha'),
        ('certo_errado', 'Certo/Errado'),
        ('afirmacoes', 'Afirmações'),
        ('afirmacoes_variadas', 'Afirmações com Alternativas Variadas'),
        ('verdadeiro_falso', 'Verdadeiro ou Falso com Sequência'),
    ]
    
    disciplina = forms.ChoiceField(
        choices=[('', 'Todas as disciplinas')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_disciplina_filtro'})
    )
    
    materia = forms.ChoiceField(
        choices=[('', 'Todas as matérias')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_materia_filtro'}) 
    )
    
    nivel_dificuldade = forms.ChoiceField(
        choices=NIVEL_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    tipo = forms.ChoiceField(
        choices=TIPO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    busca = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por enunciado ou disciplina...'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Carrega disciplinas dinamicamente para evitar consulta em import
        disciplina_choices = [('', 'Todas as disciplinas')]
        try:
            disciplina_choices += [(d.id, d.nome) for d in Disciplina.objects.all()]
        except Exception:
            # Em fase de migração, a tabela pode não existir
            pass
        self.fields['disciplina'].choices = disciplina_choices
        
        # Carrega matérias únicas baseado na disciplina selecionada
        materia_choices = [('', 'Todas as matérias')]
        try:
            if 'disciplina' in self.data and self.data['disciplina']:
                disciplina_id = self.data['disciplina']
                # Busca matérias únicas dos PDFs desta disciplina
                materias_unicas = PDFDocument.objects.filter(
                    disciplina_id=disciplina_id,
                    materia__isnull=False
                ).values_list('materia', flat=True).distinct().order_by('materia')
                materia_choices += [(m, m) for m in materias_unicas if m]
        except Exception:
            pass
        self.fields['materia'].choices = materia_choices


class GerarQuestoesForm(forms.Form):
    """Formulário para geração de questões"""
    
    disciplina = forms.ModelChoiceField(
        queryset=Disciplina.objects.none(),
        empty_label="Selecione uma disciplina",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_disciplina'})
    )
    
    nivel_dificuldade = forms.ChoiceField(
        choices=[
            ('fixacao', 'Fixação - Conteúdo do PDF'),
            ('medio', 'Médio - Aplicação Lógica'),
            ('dificil', 'Difícil - Lógica + Raciocínio Aplicado'),
            ('nivel_banca', 'Nível da Banca - Questão Real'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    quantidade = forms.IntegerField(
        min_value=1,
        max_value=20,
        initial=5,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1',
            'max': '20'
        })
    )
    
    tipos_questoes = forms.MultipleChoiceField(
        choices=[
            ('multipla_escolha', 'Múltipla Escolha'),
            ('certo_errado', 'Certo/Errado'),
            ('afirmacoes', 'Afirmações'),
            ('afirmacoes_variadas', 'Afirmações com Alternativas Variadas'),
            ('verdadeiro_falso', 'Verdadeiro ou Falso com Sequência'),
        ],
        initial=['multipla_escolha', 'afirmacoes_variadas', 'verdadeiro_falso'],
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ajusta queryset dinamicamente (evita consulta na importação do módulo)
        try:
            self.fields['disciplina'].queryset = Disciplina.objects.all()
        except Exception:
            self.fields['disciplina'].queryset = Disciplina.objects.none()
        
        if 'disciplina' in self.data:
            try:
                disciplina_id = int(self.data.get('disciplina'))
                self.fields['topico'].queryset = Topico.objects.filter(disciplina_id=disciplina_id)
            except (ValueError, TypeError):
                self.fields['topico'].queryset = Topico.objects.none()
        else:
            self.fields['topico'].queryset = Topico.objects.none()


class ProvaAntigaUploadForm(forms.ModelForm):
    """Formulário para upload de provas antigas"""
    class Meta:
        model = ProvaAntiga
        fields = ['titulo', 'ano', 'banca', 'tipo', 'arquivo_pdf', 'quantidade_total_questoes', 'observacoes']
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Prova IDECAN 2024 - Concurso Bombeiros'
            }),
            'ano': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '2000',
                'max': '2030'
            }),
            'banca': forms.Select(attrs={'class': 'form-select'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'arquivo_pdf': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf'
            }),
            'quantidade_total_questoes': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '80',
                'placeholder': 'Ex: 80'
            }),
            'observacoes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observações sobre a prova (opcional)'
            })
        }
    
    def clean_arquivo_pdf(self):
        arquivo = self.cleaned_data.get('arquivo_pdf')
        if arquivo:
            if not arquivo.name.lower().endswith('.pdf'):
                raise forms.ValidationError('Apenas arquivos PDF são permitidos.')
            if arquivo.size > 50 * 1024 * 1024:  # 50MB
                raise forms.ValidationError('O arquivo deve ter no máximo 50MB.')
        return arquivo
    
    def clean_ano(self):
        ano = self.cleaned_data.get('ano')
        if ano and (ano < 2000 or ano > 2030):
            raise forms.ValidationError('O ano deve estar entre 2000 e 2030.')
        return ano


