import streamlit as st
import requests
from dotenv import load_dotenv
import os
from datetime import datetime

# Carregar variáveis de ambiente
load_dotenv()

# --- Configurações Bling e OAuth 2.0 ---
BLING_AUTH_URL = "https://www.bling.com.br/Api/v3/oauth/authorize"
BLING_TOKEN_URL = "https://www.bling.com.br/Api/v3/oauth/token"
BLING_API_BASE_URL = "https://www.bling.com.br/Api/v3"

# Credenciais Bling Origem (LOJAHI)
BLING_LOJAHI_CLIENT_ID = os.getenv("BLING_LOJAHI_CLIENT_ID")
BLING_LOJAHI_CLIENT_SECRET = os.getenv("BLING_LOJAHI_CLIENT_SECRET")
BLING_LOJAHI_REDIRECT_URI = os.getenv("BLING_LOJAHI_REDIRECT_URI", "http://localhost:8501/oauth_callback")

# Credenciais Bling Destino (SELECT)
BLING_SELECT_CLIENT_ID = os.getenv("BLING_SELECT_CLIENT_ID")
BLING_SELECT_CLIENT_SECRET = os.getenv("BLING_SELECT_CLIENT_SECRET")
BLING_SELECT_REDIRECT_URI = os.getenv("BLING_SELECT_REDIRECT_URI", "http://localhost:8501/oauth_callback")

# Caminho para armazenamento local
STORAGE_PATH = os.getenv("STORAGE_PATH", "app/data/storage")
LOG_FILE_PATH = os.path.join(STORAGE_PATH, "migration_log.txt")

# Garantir que o diretório de armazenamento e log exista
os.makedirs(STORAGE_PATH, exist_ok=True)

def log_message(message):
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {message}\n")

# --- Funções OAuth 2.0 ---
def get_authorization_url(client_id, redirect_uri, state):
    return f"{BLING_AUTH_URL}?response_type=code&client_id={client_id}&state={state}&redirect_uri={redirect_uri}"

def get_access_token(client_id, client_secret, code, redirect_uri):
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri
    }
    response = requests.post(BLING_TOKEN_URL, headers=headers, data=data)
    response.raise_for_status()
    return response.json()

def refresh_access_token(client_id, client_secret, refresh_token):
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret
    }
    response = requests.post(BLING_TOKEN_URL, headers=headers, data=data)
    response.raise_for_status()
    return response.json()

# --- Funções API Bling ---
def get_product_images(access_token, sku):
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    # A API v3 do Bling não tem um endpoint direto para obter imagens de um produto por SKU.
    # Primeiro, encontramos o produto pelo SKU, depois fazemos a requisição das imagens associadas.
    # Isso pode requerer 2 requisições: 1 para buscar o produto, 1 para buscar as imagens do produto encontrado.
    
    # Exemplo (adaptar conforme a documentação exata do Bling API v3):
    # Busca produto por SKU
    response_product = requests.get(f"{BLING_API_BASE_URL}/produtos?filters=sku['{sku}']", headers=headers)
    response_product.raise_for_status()
    products_data = response_product.json().get('data')

    if not products_data:
        st.warning(f"SKU {sku} não encontrado na conta de origem.")
        log_message(f"SKU {sku} não encontrado na conta de origem.")
        return []
    
    product_id = products_data[0]['id'] # Assumindo que o SKU é único e retorna 1 produto

    # Busca imagens do produto
    response_images = requests.get(f"{BLING_API_BASE_URL}/produtos/{product_id}/imagens", headers=headers)
    response_images.raise_for_status()
    return response_images.json().get('data', [])

def download_image(url, save_path):
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(save_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

def upload_image_to_bling(access_token, product_id, image_path):
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    files = {
        "file": (os.path.basename(image_path), open(image_path, 'rb'), 'image/jpeg') # Ou o tipo MIME correto
    }
    # Bling API v3 para upload de imagens pode exigir um endpoint específico para produtos
    # Exemplo (adaptar conforme a documentação exata do Bling API v3):
    response = requests.post(f"{BLING_API_BASE_URL}/produtos/{product_id}/anexar-imagem", headers=headers, files=files)
    response.raise_for_status()
    return response.json()

# --- Lógica de Migração ---
def migrate_sku_images(sku, access_token_origin, access_token_dest):
    log_message(f"Iniciando migração para SKU: {sku}")
    sku_storage_path = os.path.join(STORAGE_PATH, sku)
    os.makedirs(sku_storage_path, exist_ok=True)
    
    try:
        # 1. Obter imagens da conta de origem
        st.info(f"Obtendo imagens do SKU {sku} na conta de origem...")
        images_data_origin = get_product_images(access_token_origin, sku)
        
        if not images_data_origin:
            log_message(f"Nenhuma imagem encontrada para SKU {sku} na origem. Ignorando.")
            st.warning(f"Nenhuma imagem encontrada para SKU {sku} na origem.")
            return False

        downloaded_images = []
        for img in images_data_origin:
            image_url = img.get('link')
            if image_url:
                file_name = os.path.basename(image_url)
                local_image_path = os.path.join(sku_storage_path, file_name)
                st.info(f"Baixando imagem {file_name}...")
                download_image(image_url, local_image_path)
                downloaded_images.append(local_image_path)
                log_message(f"Imagem {file_name} do SKU {sku} baixada para {local_image_path}")

        # 2. Encontrar o ID do produto na conta de destino pelo SKU
        st.info(f"Buscando SKU {sku} na conta de destino...")
        response_product_dest = requests.get(f"{BLING_API_BASE_URL}/produtos?filters=sku['{sku}']", headers={
            "Authorization": f"Bearer {access_token_dest}"
        })
        response_product_dest.raise_for_status()
        products_data_dest = response_product_dest.json().get('data')

        if not products_data_dest:
            log_message(f"SKU {sku} não encontrado na conta de destino. Ignorando upload.")
            st.error(f"SKU {sku} não encontrado na conta de destino. Imagens baixadas para {sku_storage_path}")
            return False
        
        product_id_dest = products_data_dest[0]['id']

        # 3. Fazer upload das imagens para a conta de destino
        st.info(f"Fazendo upload de imagens para SKU {sku} na conta de destino...")
        for image_path in downloaded_images:
            st.info(f"Subindo imagem {os.path.basename(image_path)} do SKU {sku}...")
            upload_image_to_bling(access_token_dest, product_id_dest, image_path)
            log_message(f"Imagem {os.path.basename(image_path)} do SKU {sku} enviada com sucesso para o destino.")
        
        st.success(f"Migração do SKU {sku} concluída com sucesso!")
        log_message(f"Migração do SKU {sku} concluída com sucesso!")
        return True

    except requests.exceptions.HTTPError as e:
        error_message = f"Erro HTTP na migração do SKU {sku}: {e.response.status_code} - {e.response.text}"
        st.error(error_message)
        log_message(error_message)
    except Exception as e:
        error_message = f"Erro inesperado na migração do SKU {sku}: {e}"
        st.error(error_message)
        log_message(error_message)
    finally:
        # Limpar arquivos baixados após a tentativa de migração (opcional, dependendo da necessidade de debug)
        # shutil.rmtree(sku_storage_path)
        pass # Manter arquivos localmente por enquanto para debug
    
    return False

# --- Interface Streamlit ---
st.set_page_config(page_title="Bling Picture Migrator", layout="wide")
st.title("Bling Picture Migrator")
st.markdown("Migre fotos de produtos entre contas Bling (LOJAHI -> SELECT)")

# Carregar tokens de sessão ou iniciar fluxo OAuth
def get_oauth_tokens():
    if "tokens_lojahih" not in st.session_state:
        st.session_state.tokens_lojahih = None
    if "tokens_select" not in st.session_state:
        st.session_state.tokens_select = None
    
    st.sidebar.header("Autenticação Bling")

    # Autenticação LOJAHI
    with st.sidebar.expander("LOJAHI (Origem)"):
        if st.session_state.tokens_lojahih is None:
            # Gerar URL de autorização
            lojahih_auth_url = get_authorization_url(BLING_LOJAHI_CLIENT_ID, BLING_LOJAHI_REDIRECT_URI, "lojahih_state")
            st.write("1. Autorize a LOJAHI:")
            st.markdown(f"[Clique aqui para autorizar a LOJAHI]({lojahih_auth_url})")
            auth_code_lojahih = st.text_input("2. Código de Autorização LOJAHI:", key="code_lojahih")
            if auth_code_lojahih:
                try:
                    tokens = get_access_token(BLING_LOJAHI_CLIENT_ID, BLING_LOJAHI_CLIENT_SECRET, auth_code_lojahih, BLING_LOJAHI_REDIRECT_URI)
                    st.session_state.tokens_lojahih = tokens
                    st.success("LOJAHI autenticada com sucesso!")
                    log_message("LOJAHI autenticada com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao autenticar LOJAHI: {e}")
                    log_message(f"Erro ao autenticar LOJAHI: {e}")
        else:
            st.success("LOJAHI já autenticada.")
            if st.button("Reautenticar LOJAHI", key="reauth_lojahih"):
                st.session_state.tokens_lojahih = None
                st.experimental_rerun()

    # Autenticação SELECT
    with st.sidebar.expander("SELECT (Destino)"):
        if st.session_state.tokens_select is None:
            # Gerar URL de autorização
            select_auth_url = get_authorization_url(BLING_SELECT_CLIENT_ID, BLING_SELECT_REDIRECT_URI, "select_state")
            st.write("1. Autorize a SELECT:")
            st.markdown(f"[Clique aqui para autorizar a SELECT]({select_auth_url})")
            auth_code_select = st.text_input("2. Código de Autorização SELECT:", key="code_select")
            if auth_code_select:
                try:
                    tokens = get_access_token(BLING_SELECT_CLIENT_ID, BLING_SELECT_CLIENT_SECRET, auth_code_select, BLING_SELECT_REDIRECT_URI)
                    st.session_state.tokens_select = tokens
                    st.success("SELECT autenticada com sucesso!")
                    log_message("SELECT autenticada com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao autenticar SELECT: {e}")
                    log_message(f"Erro ao autenticar SELECT: {e}")
        else:
            st.success("SELECT já autenticada.")
            if st.button("Reautenticar SELECT", key="reauth_select"):
                st.session_state.tokens_select = None
                st.experimental_rerun()

    return st.session_state.tokens_lojahih, st.session_state.tokens_select


tokens_lojahih, tokens_select = get_oauth_tokens()

if tokens_lojahih and tokens_select:
    st.subheader("Migração de Imagens por SKU")
    skus_input = st.text_area("Insira os SKUs dos produtos (um por linha):", height=200)
    if st.button("Iniciar Migração"): 
        if skus_input:
            skus_to_migrate = [sku.strip() for sku in skus_input.split('\n') if sku.strip()]
            progress_bar = st.progress(0)
            total_skus = len(skus_to_migrate)
            migrated_count = 0
            
            for i, sku in enumerate(skus_to_migrate):
                st.write(f"Processando SKU: **{sku}**... ({i+1}/{total_skus})")
                if migrate_sku_images(sku, tokens_lojahih['access_token'], tokens_select['access_token']):
                    migrated_count += 1
                progress_bar.progress((i + 1) / total_skus)
            
            st.success(f"Migração concluída! {migrated_count} de {total_skus} SKUs migrados com sucesso.")
        else:
            st.warning("Por favor, insira pelo menos um SKU.")
else:
    st.warning("Por favor, autentique-se em ambas as contas Bling para iniciar a migração.")

# Exibir log de migração (opcional)
if os.path.exists(LOG_FILE_PATH):
    with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
        st.sidebar.download_button("Download Log", f.read(), file_name="migration_log.txt")

