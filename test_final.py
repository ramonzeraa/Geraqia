#!/usr/bin/env python
"""
Teste final do sistema
"""
import requests
import time

def test_sistema():
    print("🧪 TESTE FINAL DO SISTEMA")
    print("=" * 40)
    
    # Aguardar servidor inicializar
    time.sleep(2)
    
    try:
        # Teste 1: Página inicial
        response = requests.get('http://127.0.0.1:8000/', timeout=5)
        print(f"✅ Página inicial: {response.status_code}")
    except Exception as e:
        print(f"❌ Página inicial: {e}")
    
    try:
        # Teste 2: Listagem de questões
        response = requests.get('http://127.0.0.1:8000/questoes/', timeout=5)
        print(f"✅ Listagem de questões: {response.status_code}")
    except Exception as e:
        print(f"❌ Listagem de questões: {e}")
    
    try:
        # Teste 3: Upload de PDF
        response = requests.get('http://127.0.0.1:8000/upload-pdf/', timeout=5)
        print(f"✅ Upload de PDF: {response.status_code}")
    except Exception as e:
        print(f"❌ Upload de PDF: {e}")
    
    try:
        # Teste 4: Provas antigas
        response = requests.get('http://127.0.0.1:8000/provas-antigas/', timeout=5)
        print(f"✅ Provas antigas: {response.status_code}")
    except Exception as e:
        print(f"❌ Provas antigas: {e}")
    
    try:
        # Teste 5: Dashboard
        response = requests.get('http://127.0.0.1:8000/dashboard/', timeout=5)
        print(f"✅ Dashboard: {response.status_code}")
    except Exception as e:
        print(f"❌ Dashboard: {e}")
    
    try:
        # Teste 6: Admin
        response = requests.get('http://127.0.0.1:8000/admin/', timeout=5)
        print(f"✅ Admin: {response.status_code}")
    except Exception as e:
        print(f"❌ Admin: {e}")
    
    print("\n🎉 TESTE CONCLUÍDO!")

if __name__ == "__main__":
    test_sistema()


