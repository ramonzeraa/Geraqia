from django.core.management.base import BaseCommand
from core.models import PDFDocument
from core.services import PDFProcessor
import os

class Command(BaseCommand):
    help = "Testa a funcionalidade de detecção de duplicatas"

    def handle(self, *args, **options):
        # Lista PDFs existentes
        pdfs = PDFDocument.objects.filter(hash_arquivo__isnull=False)
        
        self.stdout.write(f'PDFs com hash no sistema: {pdfs.count()}')
        
        for pdf in pdfs:
            self.stdout.write(f'\n--- {pdf.titulo} ---')
            self.stdout.write(f'Hash: {pdf.hash_arquivo[:16]}...')
            self.stdout.write(f'Disciplina: {pdf.disciplina}')
            self.stdout.write(f'Matéria: {pdf.materia}')
            self.stdout.write(f'Usuário: {pdf.usuario.username}')
            self.stdout.write(f'Processado: {pdf.processado}')
            
            # Testa verificação de duplicata
            pdf_duplicata = PDFProcessor.verificar_duplicata(pdf.hash_arquivo)
            if pdf_duplicata:
                self.stdout.write(f'✓ Duplicata detectada: {pdf_duplicata.titulo}')
            else:
                self.stdout.write('✗ Nenhuma duplicata encontrada')
        
        # Busca grupos de duplicatas
        from django.db.models import Count
        grupos = PDFDocument.objects.filter(
            hash_arquivo__isnull=False
        ).values('hash_arquivo').annotate(
            total=Count('id')
        ).filter(total__gt=1)
        
        self.stdout.write(f'\nGrupos de duplicatas encontrados: {len(grupos)}')
        
        for grupo in grupos:
            pdfs_grupo = PDFDocument.objects.filter(hash_arquivo=grupo['hash_arquivo'])
            self.stdout.write(f'\nGrupo com {grupo["total"]} PDFs:')
            for pdf in pdfs_grupo:
                self.stdout.write(f'  - {pdf.titulo} ({pdf.usuario.username})')

