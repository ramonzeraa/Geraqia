from django.core.management.base import BaseCommand
from core.models import PDFDocument
from core.services import PDFProcessor
import os

class Command(BaseCommand):
    help = "Popula hashes dos PDFs existentes"

    def handle(self, *args, **options):
        pdfs_sem_hash = PDFDocument.objects.filter(hash_arquivo__isnull=True)
        total = pdfs_sem_hash.count()
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS('Todos os PDFs já possuem hash.'))
            return
        
        self.stdout.write(f'Processando {total} PDFs...')
        
        processados = 0
        erros = 0
        
        for pdf in pdfs_sem_hash:
            try:
                if pdf.arquivo and os.path.exists(pdf.arquivo.path):
                    # Lê o arquivo e calcula hash
                    with open(pdf.arquivo.path, 'rb') as f:
                        hash_arquivo = PDFProcessor.calcular_hash_arquivo(f)
                        tamanho = os.path.getsize(pdf.arquivo.path)
                        
                        # Verifica se já existe um PDF com este hash
                        pdf_existente = PDFProcessor.verificar_duplicata(hash_arquivo)
                        if pdf_existente and pdf_existente.id != pdf.id:
                            # PDF duplicado - marca como duplicado mas não salva o hash
                            self.stdout.write(self.style.WARNING(f'⚠ Duplicata detectada: {pdf.titulo} (igual a {pdf_existente.titulo})'))
                            erros += 1
                        else:
                            pdf.hash_arquivo = hash_arquivo
                            pdf.tamanho_arquivo = tamanho
                            pdf.save()
                            
                            processados += 1
                            self.stdout.write(f'✓ {pdf.titulo}')
                else:
                    self.stdout.write(self.style.WARNING(f'⚠ Arquivo não encontrado: {pdf.titulo}'))
                    erros += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Erro em {pdf.titulo}: {str(e)}'))
                erros += 1
        
        self.stdout.write(self.style.SUCCESS(
            f'Processamento concluído: {processados} sucessos, {erros} erros'
        ))
