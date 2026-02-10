import streamlit as st
import requests
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import json

# Carregar variáveis de ambiente
load_dotenv()

# --- Configurações Bling e OAuth 2.0 ---
BLING_AUTH_URL = "https://www.bling.com.br/Api/v3/oauth/authorize"
BLING_TOKEN_URL = "https://www.bling.com.br/Api/v3/oauth/token"
BLING_API_BASE_URL = "https://www.bling.com.br/Api/v3"

# Credenciais Bling Origem (LOJAHI)
BLING_LOJAHI_CLIENT_ID = os.getenv("BLING_LOJAHI_CLIENT_ID")
BLING_LOJAHI_CLIENT_SECRET = os.getenv("BLING_LOJAHI_CLIENT_SECRET")

# Credenciais Bling Destino (SELECT)
BLING_SELECT_CLIENT_ID = os.getenv("BLING_SELECT_CLIENT_ID")
BLING_SELECT_CLIENT_SECRET = os.getenv("BLING_SELECT_CLIENT_SECRET")

# Caminho para armazenamento local
# A APP_URL será definida pelo Railway em produção, ou será localhost em dev
APP_URL_BASE = os.getenv("APP_URL", "http://localhost:8501") # Padrão para desenvolvimento local

# Redirect URIs
BLING_LOJAHI_REDIRECT_URI = f"{APP_URL_BASE}/oauth_callback"
BLING_SELECT_REDIRECT_URI = f"{APP_URL_BASE}/oauth_callback"

STORAGE_PATH = os.getenv("STORAGE_PATH", "app/data/storage") # Caminho como /app/data/storage no Railway
LOG_FILE_PATH = os.path.join(STORAGE_PATH, "migration_log.txt")
TOKEN_LOJAHI_PATH = os.path.join(STORAGE_PATH, "token_lojahi.json")
TOKEN_SELECT_PATH = os.path.join(STORAGE_PATH, "token_select.json")

# Garantir que o diretório de armazenamento e log exista
os.makedirs(STORAGE_PATH, exist_ok=True)


def log_message(message):
    '''Adiciona uma mensagem ao arquivo de log da migração.'''
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {message}\n")


def save_tokens(account_name, tokens):
    '''Salva os tokens OAuth em um arquivo JSON no volume persistente.'''
    token_path = TOKEN_LOJAHI_PATH if account_name == "lojahih" else TOKEN_SELECT_PATH
    tokens["expires_at"] = (datetime.now() + timedelta(seconds=tokens["expires_in"])).isoformat()
    with open(token_path, "w", encoding="utf-8") as f:
        json.dump(tokens, f)
    log_message(f"Tokens de {account_name} salvos em {token_path}")


def load_tokens(account_name):
    '''Carrega os tokens OAuth de um arquivo JSON e verifica a expiração.'''
    token_path = TOKEN_LOJAHI_PATH if account_name == "lojahih" else TOKEN_SELECT_PATH
    if not os.path.exists(token_path):
        return None
    try:
        with open(token_path, "r", encoding="utf-8") as f:
            tokens = json.load(f)
        if "expires_at" in tokens:
            expires_at = datetime.fromisoformat(tokens["expires_at"])
            if expires_at < datetime.now():
                log_message(f"Tokens de {account_name} expirados. Tentando refresh...")
                # TODO: Implementar refresh token. Por enquanto, retorna None para forçar reautenticação
                st.warning(f"Tokens de {account_name} expirados. Por favor, reautentique.")
                return None
        return tokens
    except json.JSONDecodeError:
        log_message(f"Erro ao decodificar tokens de {account_name} de {token_path}")
        return None


# --- Funções OAuth 2.0 ---
def get_authorization_url(client_id, redirect_uri, state):
    '''Gera a URL de autorização Bling OAuth 2.0.'''
    params = {
        "response_type": "code",
        "client_id": client_id,
        "state": state,
        "redirect_uri": redirect_uri
    }
    return f"{BLING_AUTH_URL}?" + "&".join([f"{k}={v}" for k, v in params.items()])


def get_access_token(client_id, client_secret, code, redirect_uri):
    '''Troca o código de autorização por um token de acesso Bling.'''
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "authorization_code", "code": code, "client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri}
    response = requests.post(BLING_TOKEN_URL, headers=headers, data=data)
    response.raise_for_status()
    return response.json()


def refresh_access_token(client_id, client_secret, refresh_token):
    '''Usa o refresh token para obter um novo token de acesso Bling.'''
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id, "client_secret": client_secret}
    response = requests.post(BLING_TOKEN_URL, headers=headers, data=data)
    response.raise_for_status()
    return response.json()


# --- Funções API Bling ---
def get_product_images(access_token, sku):
    '''Obtém as imagens de um produto Bling pelo SKU.'''
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    # Bling API v3: Primeiro busca o produto pelo SKU, depois suas imagens
    response_product = requests.get(f"{BLING_API_BASE_URL}/produtos?filters=sku['{sku}']", headers=headers)
    response_product.raise_for_status()
    products_data = response_product.json().get('data')

    if not products_data:
        log_message(f"SKU {sku} não encontrado na conta de origem.")
        return []

    product_id = products_data[0]['id']
    response_images = requests.get(f"{BLING_API_BASE_URL}/produtos/{product_id}/imagens", headers=headers)
    response_images.raise_for_status()
    return response_images.json().get('data', [])


def download_image(url, save_path):
    '''Baixa uma imagem de uma URL para um caminho local.'''
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(save_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def upload_image_to_bling(access_token, product_id, image_path):
    '''Faz upload de uma imagem para um produto específico no Bling Destino.'''
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    files = {
        "file": (os.path.basename(image_path), open(image_path, 'rb'), 'image/jpeg')
    }
    # Endpoint da API Bling v3 para anexar imagem (sujeito a ajustes)
    response = requests.post(f"{BLING_API_BASE_URL}/produtos/{product_id}/anexar-imagem", headers=headers, files=files)
    response.raise_for_status()
    return response.json()


# --- Lógica de Migração ---
def migrate_sku_images(sku, access_token_origin, access_token_dest):
    '''Orquestra o download de imagens de origem e upload para o destino para um SKU.'''
    log_message(f"Iniciando migração para SKU: {sku}")
    sku_storage_path = os.path.join(STORAGE_PATH, sku)
    os.makedirs(sku_storage_path, exist_ok=True)

    try:
        # 1. Obter imagens da conta de origem
        st.info(f"Obtendo imagens do SKU {sku} na conta de origem...")
        images_data_origin = get_product_images(access_token_origin, sku)

        if not images_data_origin:
            log_message(f"Nenhuma imagem encontrada para SKU {sku} na origem. Ignorando.")
            # st.warning(f"Nenhuma imagem encontrada para SKU {sku} na origem.") # Evitar mensagens excessivas
            return False

        downloaded_images = []
        for img_data in images_data_origin:
            image_url = img_data.get('link')
            if image_url:
                file_name = os.path.basename(image_url).split('?')[0] # Remove query params da URL
                local_image_path = os.path.join(sku_storage_path, file_name)
                st.info(f"Baixando imagem {file_name} do SKU {sku}...")
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
            log_message(f"SKU {sku} não encontrado na conta de destino. Imagens baixadas para {sku_storage_path}, mas não enviadas.")
            st.error(f"SKU {sku} não encontrado na conta de destino. Imagens baixadas para {sku_storage_path}, mas não enviadas.")
            return False

        product_id_dest = products_data_dest[0]['id']

        # 3. Fazer upload das imagens para a conta de destino
        st.info(f"Fazendo upload de imagens para SKU {sku} no Bling Destino (Produto ID: {product_id_dest})...")
        for image_path in downloaded_images:
            st.info(f"Subindo imagem {os.path.basename(image_path)} do SKU {sku}...")
            upload_image_to_bling(access_token_dest, product_id_dest, image_path)
            log_message(f"Imagem {os.path.basename(image_path)} do SKU {sku} enviada com sucesso para o destino.")

        st.success(f"Migração do SKU {sku} concluída com sucesso!")
        log_message(f"Migração do SKU {sku} concluída com sucesso!")
        return True

    except requests.exceptions.HTTPError as e:
        error_message = f"Erro HTTP na migração do SKU {sku}: {e.response.status_code} - {e.response.text} (URL: {e.request.url})"
        st.error(error_message)
        log_message(error_message)
    except Exception as e:
        error_message = f"Erro inesperado na migração do SKU {sku}: {e}"
        st.error(error_message)
        log_message(error_message)
    finally:
        # Manter arquivos localmente por enquanto para debug. Em produção, considerar limpeza.
        pass
    
    return False


# --- Interface Streamlit ---
st.set_page_config(page_title="Bling Picture Migrator", layout="wide")
st.title("Bling Picture Migrator")
st.markdown("Ferramenta para migrar fotos de produtos entre contas Bling (Origem -> Destino).")
st.markdown(f"URL Base da Aplicação: __`{APP_URL_BASE}`__. Certifique-se de que a `APP_URL` configurada no Railway corresponda à URL pública da sua aplicação Bling para Redirecionamentos OAuth.")

# --- Fluxo de Autenticação Sequencial ---
st.sidebar.header("Status da Autenticação Bling")

tokens_lojahih_loaded = load_tokens("lojahih")
tokens_select_loaded = load_tokens("select")

# Definir estados atuais
is_lojahih_authenticated = tokens_lojahih_loaded is not None
is_select_authenticated = tokens_select_loaded is not None

tokens_lojahih = tokens_lojahih_loaded
tokens_select = tokens_select_loaded


if not is_lojahih_authenticated:
    st.header("Passo 1: Conectar Conta de Origem (LOJAHI)")
    st.info("Para iniciar, autorize o acesso à sua conta Bling de origem (LOJAHI).")
    lojahih_auth_url = get_authorization_url(BLING_LOJAHI_CLIENT_ID, BLING_LOJAHI_REDIRECT_URI, "lojahih_state")
    st.markdown(f"**Clique aqui para autorizar a LOJAHI:** [Autorizar LOJAHI]({lojahih_auth_url})")

    auth_code_lojahih = st.text_input("Cole o Código de Autorização da LOJAHI aqui:", key="code_lojahih_input")
    if auth_code_lojahih:
        try:
            tokens = get_access_token(BLING_LOJAHI_CLIENT_ID, BLING_LOJAHI_CLIENT_SECRET, auth_code_lojahih, BLING_LOJAHI_REDIRECT_URI)
            save_tokens("lojahih", tokens)
            tokens_lojahih = tokens # Atualizar o token na sessão atual
            st.success("LOJAHI autenticada com sucesso! Recarregue a página para continuar.")
            log_message("LOJAHI autenticada com sucesso!")
            st.experimental_rerun() # Recarregar a página para mostrar o próximo passo
        except Exception as e:
            st.error(f"Erro ao autenticar LOJAHI: {e}")
            log_message(f"Erro ao autenticar LOJAHI: {e}")
            
elif is_lojahih_authenticated and not is_select_authenticated:
    st.header("Passo 2: Conectar Conta de Destino (SELECT)")
    st.success("✅ Origem (LOJAHI) Conectada com Sucesso!")
    st.info("Agora, vamos conectar sua conta Bling de destino (SELECT).")
    
    st.warning("⚠️ **IMPORTANTE:** Antes de clicar abaixo, certifique-se de ter feito LOGOUT TOTAL do Bling nesta aba ou abra o link abaixo em uma **JANELA ANÔNIMA** para evitar conflito de contas Bling.")
    
    select_auth_url = get_authorization_url(BLING_SELECT_CLIENT_ID, BLING_SELECT_REDIRECT_URI, "select_state")
    st.markdown(f"**Clique aqui para autorizar a SELECT:** [Autorizar SELECT]({select_auth_url})")

    auth_code_select = st.text_input("Cole o Código de Autorização da SELECT aqui:", key="code_select_input")
    if auth_code_select:
        try:
            tokens = get_access_token(BLING_SELECT_CLIENT_ID, BLING_SELECT_CLIENT_SECRET, auth_code_select, BLING_SELECT_REDIRECT_URI)
            save_tokens("select", tokens)
            tokens_select = tokens # Atualizar o token na sessão atual
            st.success("SELECT autenticada com sucesso! Recarregue a página para continuar.")
            log_message("SELECT autenticada com sucesso!")
            st.experimental_rerun() # Recarregar a página para mostrar o próximo passo
        except Exception as e:
            st.error(f"Erro ao autenticar SELECT: {e}")
            log_message(f"Erro ao autenticar SELECT: {e}")

elif is_lojahih_authenticated and is_select_authenticated:
    st.header("Passo 3: Iniciar Migração de Imagens")
    st.success("✅ Origem (LOJAHI) Conectada com Sucesso!")
    st.success("✅ Destino (SELECT) Conectado com Sucesso!")
    st.markdown("Ambas as contas Bling estão autenticadas. Agora você pode migrar as imagens.")

    skus_input = st.text_area("Insira os SKUs dos produtos (um por linha):", height=200)
    if st.button("Iniciar Migração"):
        if skus_input:
            skus_to_migrate = [sku.strip() for sku in skus_input.split('\n') if sku.strip()]
            progress_bar = st.progress(0)
            status_text = st.empty()
            total_skus = len(skus_to_migrate)
            migrated_count = 0

            with st.spinner("Iniciando migração..."):
                for i, sku in enumerate(skus_to_migrate):
                    status_text.text(f"Processando SKU: {sku}... ({i+1}/{total_skus})")
                    if migrate_sku_images(sku, tokens_lojahih['access_token'], tokens_select['access_token']):
                        migrated_count += 1
                    progress_bar.progress((i + 1) / total_skus)
                
                if migrated_count == total_skus:
                    st.success(f"🎉 Migração concluída! Todos os {migrated_count} SKUs foram migrados com sucesso.")
                else:
                    st.warning(f"Migração concluída com {migrated_count} de {total_skus} SKUs migrados. Verifique o log para detalhes de SKUs pendentes ou com erros.")
                log_message(f"Migração finalizada. {migrated_count}/{total_skus} SKUs migrados com sucesso.")
        else:
            st.warning("Por favor, insira pelo menos um SKU para iniciar a migração.")

# --- Exibir log de migração (opcional na sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader("Logs da Migração")
if os.path.exists(LOG_FILE_PATH):
    with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
        log_content = f.read()
        st.sidebar.download_button("Download Log", log_content, file_name="migration_log.txt", mime="text/plain")
        if st.sidebar.checkbox("Exibir Log Completo"):
            st.sidebar.text_area("Log de Migração", log_content, height=300)
else:
    st.sidebar.info("Nenhum log de migração disponível ainda.")

# --- Estado atual da autenticação (sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader("Estado dos Tokens (Debug)")
if tokens_lojahih:
    st.sidebar.write("LOJAHI: ✅ Conectada")
    if st.sidebar.button("Limpar Token LOJAHI", key="clear_lojahi_token"):
        os.remove(TOKEN_LOJAHI_PATH)
        st.experimental_rerun()
else:
    st.sidebar.write("LOJAHI: ❌ Desconectada")

if tokens_select:
    st.sidebar.write("SELECT: ✅ Conectada")
    if st.sidebar.button("Limpar Token SELECT", key="clear_select_token"):
        os.remove(TOKEN_SELECT_PATH)
        st.experimental_rerun()
else:
    st.sidebar.write("SELECT: ❌ Desconectada")
