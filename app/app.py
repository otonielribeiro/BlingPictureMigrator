# Temporary comment to force a new commit for testing.
import streamlit as st
import requests
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import json
import uuid # Mantido para referência, mas não usado diretamente para state
import base64 # Importado para codificação Base64

# Carregar variáveis de ambiente
load_dotenv()

# --- Constantes de State Fixo para OAuth ---
STATE_LOJAHI_FIXED = "state_lojahi_fixed_v1"
STATE_SELECT_FIXED = "state_select_fixed_v1"

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
APP_URL_BASE = os.getenv("APP_URL", "http://localhost:8080") # Padrão para desenvolvimento local, Railway usa $PORT=8080

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
    token_path = TOKEN_LOJAHI_PATH if account_name == "lojahi" else TOKEN_SELECT_PATH
    tokens["expires_at"] = (datetime.now() + timedelta(seconds=tokens["expires_in"])).isoformat()
    with open(token_path, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=4)
    log_message(f"Tokens de {account_name} salvos em {token_path}")


def load_tokens(account_name):
    '''Carrega os tokens OAuth de um arquivo JSON e verifica a expiração.'''
    token_path = TOKEN_LOJAHI_PATH if account_name == "lojahi" else TOKEN_SELECT_PATH
    if not os.path.exists(token_path):
        return None
    try:
        with open(token_path, "r", encoding="utf-8") as f:
            tokens = json.load(f)
        if "expires_at" in tokens:
            expires_at = datetime.fromisoformat(tokens["expires_at"])
            if expires_at < datetime.now():
                log_message(f"Tokens de {account_name} expirados. Forçando reautenticação.")
                st.warning(f"Tokens de {account_name} expirados. Por favor, reautentique.")
                os.remove(token_path) # Limpa o token expirado
                st.rerun()
                return None
        return tokens
    except json.JSONDecodeError:
        log_message(f"Erro ao decodificar tokens de {account_name} de {token_path}. Arquivo corrompido ou inválido.")
        os.remove(token_path) # Limpa o arquivo corrompido
        st.rerun()
        return None
    except FileNotFoundError:
        return None


def clear_all_tokens():
    '''Remove todos os arquivos de token para resetar as conexões.'''
    if os.path.exists(TOKEN_LOJAHI_PATH):
        os.remove(TOKEN_LOJAHI_PATH)
        log_message("Token LOJAHI removido.")
    if os.path.exists(TOKEN_SELECT_PATH):
        os.remove(TOKEN_SELECT_PATH)
        log_message("Token SELECT removido.")
    st.rerun()


# --- Funções OAuth 2.0 ---
def get_authorization_url(client_id, redirect_uri):
    '''Gera a URL de autorização Bling OAuth 2.0.'''
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri
    }
    # Usando state fixo
    if client_id == BLING_LOJAHI_CLIENT_ID:
        params["state"] = STATE_LOJAHI_FIXED
    elif client_id == BLING_SELECT_CLIENT_ID:
        params["state"] = STATE_SELECT_FIXED
    else: # Fallback para client_id inesperado
        params["state"] = "generic_state"

    return f"{BLING_AUTH_URL}?" + "&".join([f"{k}={v}" for k, v in params.items()])


def get_access_token(client_id, client_secret, code, redirect_uri, received_state):
    '''Troca o código de autorização por um token de acesso Bling.'''
    # Verifica o estado para proteção CSRF
    expected_state = None
    if client_id == BLING_LOJAHI_CLIENT_ID:
        expected_state = STATE_LOJAHI_FIXED
    elif client_id == BLING_SELECT_CLIENT_ID:
        expected_state = STATE_SELECT_FIXED

    if expected_state and expected_state != received_state:
        raise ValueError("OAuth state mismatch! Possible CSRF attack or invalid redirect.")
    
    # Prepara as credenciais para Basic Auth
    client_auth_string = f"{client_id}:{client_secret}"
    encoded_client_auth = base64.b64encode(client_auth_string.encode("utf-8")).decode("utf-8")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_client_auth}" # Adiciona o cabeçalho Basic Auth
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri
        # client_id e client_secret removidos do corpo, pois estão no cabeçalho Authorization
    }
    response = requests.post(BLING_TOKEN_URL, headers=headers, data=data)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        log_message(f"DEBUG: Erro HTTP detalhado do Bling: {e.response.status_code} - {e.text}")
        raise # Re-lança o erro para Streamlit exibir
    return response.json()


def refresh_access_token(client_id, client_secret, refresh_token):
    '''Usa o refresh token para obter um novo token de acesso Bling.'''
    # Prepara as credenciais para Basic Auth
    client_auth_string = f"{client_id}:{client_secret}"
    encoded_client_auth = base64.b64encode(client_auth_string.encode("utf-8")).decode("utf-8")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_client_auth}" # Adiciona o cabeçalho Basic Auth
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
        # client_id e client_secret removidos do corpo, pois estão no cabeçalho Authorization
    }
    response = requests.post(BLING_TOKEN_URL, headers=headers, data=data)
    response.raise_for_status()
    return response.json()


# --- Funções API Bling (Mantidas as mesmas) ---
def get_product_images(access_token, sku):
    """
    Busca TODAS as imagens de um produto (pai + variações) na API do Bling v3.
    
    Estrutura da API:
    - midia é um OBJETO (não array)
    - midia.imagens.internas[] contém as imagens principais
    - midia.imagens.externas[] contém imagens externas
    - Variações têm suas próprias imagens e precisam de chamadas separadas
    
    Args:
        access_token: Token OAuth da conta Bling
        sku: Código SKU do produto
    
    Returns:
        Lista de dicts com campo 'link' contendo URLs únicas de imagens
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    
    log_message(f"🔍 [EXTRAÇÃO] Iniciando busca de imagens para SKU: {sku}")
    
    # PASSO 1: Buscar produto por SKU
    url_search = f"{BLING_API_BASE_URL}/produtos?codigo={sku}"
    log_message(f"📡 [API] GET {url_search}")
    
    try:
        resp_search = requests.get(url_search, headers=headers)
        resp_search.raise_for_status()
        search_data = resp_search.json()
        
        if not search_data.get('data'):
            log_message(f"❌ [ERRO] Nenhum produto encontrado com SKU {sku}")
            return []
        
        product_id = search_data['data'][0]['id']
        log_message(f"✅ [BUSCA] Produto encontrado - ID: {product_id}")
        
    except requests.exceptions.RequestException as e:
        log_message(f"❌ [ERRO] Falha ao buscar SKU {sku}: {str(e)}")
        return []
    
    # PASSO 2: Obter ficha completa do produto
    url_detail = f"{BLING_API_BASE_URL}/produtos/{product_id}"
    log_message(f"📡 [API] GET {url_detail}")
    
    try:
        resp_detail = requests.get(url_detail, headers=headers)
        resp_detail.raise_for_status()
        product_data = resp_detail.json().get('data', {})
        
        log_message(f"✅ [FICHA] Ficha completa obtida para produto ID {product_id}")
        
    except requests.exceptions.RequestException as e:
        log_message(f"❌ [ERRO] Falha ao obter ficha do produto {product_id}: {str(e)}")
        return []
    
    # PASSO 3: Extrair imagens do produto PAI
    found_images = []
    
    midia = product_data.get('midia', {})
    log_message(f"🔍 [ANÁLISE] Tipo do campo 'midia': {type(midia).__name__}")
    
    if isinstance(midia, dict):
        imagens_obj = midia.get('imagens', {})
        
        # Imagens internas
        internas = imagens_obj.get('internas', [])
        log_message(f"📸 [PAI] Imagens internas encontradas: {len(internas)}")
        for img in internas:
            if isinstance(img, dict) and 'link' in img:
                found_images.append(img['link'])
                log_message(f"   ✓ Imagem interna adicionada: {img['link'][:80]}...")
        
        # Imagens externas
        externas = imagens_obj.get('externas', [])
        log_message(f"📸 [PAI] Imagens externas encontradas: {len(externas)}")
        for img in externas:
            if isinstance(img, dict) and 'link' in img:
                found_images.append(img['link'])
                log_message(f"   ✓ Imagem externa adicionada: {img['link'][:80]}...")
    else:
        log_message(f"⚠️ [AVISO] Campo 'midia' não é um objeto dict. Tipo: {type(midia)}")
    
    log_message(f"📊 [PAI] Total de imagens do produto pai: {len(found_images)}")
    
    # PASSO 4: Extrair imagens de TODAS as variações
    variacoes = product_data.get('variacoes', [])
    total_variacoes = len(variacoes)
    
    if total_variacoes > 0:
        log_message(f"🔄 [VARIAÇÕES] Produto tem {total_variacoes} variações. Buscando imagens...")
        
        for idx, variacao in enumerate(variacoes, 1):
            variacao_id = variacao.get('id')
            variacao_nome = variacao.get('nome', 'N/A')
            
            log_message(f"📡 [VARIAÇÃO {idx}/{total_variacoes}] ID: {variacao_id} | Nome: {variacao_nome[:50]}...")
            
            try:
                url_variacao = f"{BLING_API_BASE_URL}/produtos/{variacao_id}"
                resp_var = requests.get(url_variacao, headers=headers)
                resp_var.raise_for_status()
                
                var_data = resp_var.json().get('data', {})
                var_midia = var_data.get('midia', {})
                
                if isinstance(var_midia, dict):
                    var_imagens = var_midia.get('imagens', {})
                    
                    # Imagens internas da variação
                    var_internas = var_imagens.get('internas', [])
                    log_message(f"   📸 Imagens internas: {len(var_internas)}")
                    for img in var_internas:
                        if isinstance(img, dict) and 'link' in img:
                            found_images.append(img['link'])
                    
                    # Imagens externas da variação
                    var_externas = var_imagens.get('externas', [])
                    log_message(f"   📸 Imagens externas: {len(var_externas)}")
                    for img in var_externas:
                        if isinstance(img, dict) and 'link' in img:
                            found_images.append(img['link'])
                
                log_message(f"   ✅ Variação {idx} processada com sucesso")
                
            except requests.exceptions.RequestException as e:
                log_message(f"   ⚠️ [AVISO] Falha ao buscar variação {variacao_id}: {str(e)}")
                continue
    else:
        log_message(f"ℹ️ [INFO] Produto não possui variações")
    
    # PASSO 5: Remover duplicatas e retornar
    unique_urls = sorted(list(set(found_images)))
    total_unique = len(unique_urls)
    
    log_message(f"🎯 [RESULTADO] Total de imagens únicas encontradas: {total_unique}")
    log_message(f"📦 [EXTRAÇÃO] Finalizando busca para SKU {sku}")
    
    if total_unique == 0:
        log_message(f"⚠️ [AVISO] Nenhuma imagem encontrada para SKU {sku}")
        return []
    
    return [{'link': url} for url in unique_urls]


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
    response = requests.post(f"{BLING_API_BASE_URL}/produtos/{product_id}/anexar-imagem", headers=headers, files=files)
    response.raise_for_status()
    return response.json()


# --- Lógica de Migração (Mantida a mesma) ---
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
            return False

        downloaded_images = []
        for img_data in images_data_origin:
            image_url = img_data.get('link')
            if image_url:
                file_name = os.path.basename(image_url).split('?')[0]
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
        pass
    return False


# --- Interface Streamlit ---
st.set_page_config(page_title="Bling Picture Migrator", layout="wide")
st.title("Bling Picture Migrator")
st.markdown("Ferramenta para migrar fotos de produtos entre contas Bling (Origem -> Destino).")
st.markdown(f"URL Base da Aplicação: __`{APP_URL_BASE}`__. Certifique-se de que a `APP_URL` configurada no Railway corresponda à URL pública da sua aplicação Bling para Redirecionamentos OAuth.")
st.markdown("---")

# --- Lógica de redirecionamento para o Streamlit ---
query_params = st.query_params
auth_code = query_params.get("code")
state_received = query_params.get("state")
client_id_for_state = None  # To identify which client_id the state belongs to


if auth_code:
    if state_received == STATE_LOJAHI_FIXED:
        client_id_for_state = BLING_LOJAHI_CLIENT_ID
        redirect_uri = BLING_LOJAHI_REDIRECT_URI
        account_name = "lojahi"
        client_secret = BLING_LOJAHI_CLIENT_SECRET
    elif state_received == STATE_SELECT_FIXED:
        client_id_for_state = BLING_SELECT_CLIENT_ID
        redirect_uri = BLING_SELECT_REDIRECT_URI
        account_name = "select"
        client_secret = BLING_SELECT_CLIENT_SECRET
    
    if client_id_for_state:
        try:
            tokens = get_access_token(client_id_for_state, client_secret, auth_code, redirect_uri, state_received)
            save_tokens(account_name, tokens)
            st.success(f"{account_name.upper()} autenticada com sucesso! Redirecionando...")
            st.query_params.clear() 
            st.rerun()
        except ValueError as e:
            st.error(f"Erro de autenticação {account_name.upper()}: {e}")
            log_message(f"Erro de autenticação {account_name.upper()}: {e}")
            st.query_params.clear()
        except requests.exceptions.HTTPError as e: # Captura HTTPError especificamente para log detalhado
            error_details = e.response.text if e.response is not None else "N/A"
            st.error(f"Erro ao autenticar {account_name.upper()}: {e.response.status_code} - {error_details}")
            log_message(f"Erro ao autenticar {account_name.upper()}: {e.response.status_code} - {error_details}")
            st.query_params.clear()
        except Exception as e:
            st.error(f"Erro ao autenticar {account_name.upper()}: {e}")
            log_message(f"Erro ao autenticar {account_name.upper()}: {e}")
            st.query_params.clear()
    else:
        st.error("Erro: Estado OAuth recebido não corresponde a nenhuma conta Bling esperada. Possível CSRF ou token inválido.")
        log_message("Erro: Estado OAuth recebido não corresponde a nenhuma conta Bling esperada.")
        st.query_params.clear()

# --- Fluxo de Autenticação Sequencial Principal ---
current_lojahi_tokens = load_tokens("lojahi")
current_select_tokens = load_tokens("select")

is_lojahi_connected = current_lojahi_tokens is not None
is_select_connected = current_select_tokens is not None

tokens_to_use_lojahi = current_lojahi_tokens['access_token'] if is_lojahi_connected else None
tokens_to_use_select = current_select_tokens['access_token'] if is_select_connected else None


if not is_lojahi_connected:
    # --- FASE 1: Conexão da Origem (LOJAHI) ---
    st.header("Passo 1: Conectar Conta de Origem (LOJAHI)")
    st.warning("⚠️ **ATENÇÃO:** Para iniciar a autenticação da conta de origem (LOJAHI) e evitar conflitos, **certifique-se de estar deslogado do Bling** ou logado na conta correta (LOJAHI) no seu navegador.")
    st.markdown(f"**[🔴 CLIQUE AQUI PARA LIMPAR SESSÃO ANTERIOR](https://www.bling.com.br/login?logout=true)** (Sugestão: Abra em uma **nova aba** com Ctrl/Cmd + clique ou botão direito)")
    st.info("Após deslogar, ou se já estiver na conta LOJAHI, marque a caixa abaixo para prosseguir com a autorização.")

    logout_confirmed_lojahi = st.checkbox("Confirmo que estou deslogado ou na conta correta (LOJAHI).", key="logout_confirm_checkbox_lojahi")

    if logout_confirmed_lojahi:
        lojahi_auth_url = get_authorization_url(BLING_LOJAHI_CLIENT_ID, BLING_LOJAHI_REDIRECT_URI)
        st.markdown(f"**1. Clique aqui para autorizar a LOJAHI:** [Autorizar LOJAHI]({lojahi_auth_url})")

        # Para testes locais, o usuário ainda pode precisar colar o código (em caso de falha de redirecionamento)
        if APP_URL_BASE == "http://localhost:8080" and not auth_code:
            temp_code_input = st.text_input("Cole o código de autorização da LOJAHI (somente para depuração local):", key="temp_lojahi_code_input")
            if temp_code_input:
                st.warning("Por favor, cole o código, ou use a URL de redirecionamento para o seu ambiente Railway. Recarregue após colar.")
    else:
        st.info("Marque a caixa acima para prosseguir com a conexão da conta de origem.")

elif is_lojahi_connected and not is_select_connected:
    # --- FASE 2: Conexão do Destino (SELECT) ---
    st.header("Passo 2: Conectar Conta de Destino (SELECT)")
    st.success("✅ Origem (LOJAHI) Conectada com Sucesso!")
    
    st.warning("⚠️ **ATENÇÃO:** Para conectar a conta de destino (SELECT) e evitar o erro 'client_id mismatch', **É OBRIGATÓRIO** fazer o logout da conta Bling ativa, **OU** logar na conta SELECT no seu navegador. Recomenda-se usar uma **JANELA ANÔNIMA**.")
    st.markdown(f"**[🔴 CLIQUE AQUI PARA LIMPAR SESSÃO ANTERIOR](https://www.bling.com.br/login?logout=true)** (Sugestão: Abra em uma **nova aba** com Ctrl/Cmd + clique ou botão direito)")
    st.info("Após deslogar, ou se já estiver na conta SELECT, retorne a esta página e marque a caixa abaixo para prosseguir com a autorização.")

    logout_confirmed_select = st.checkbox("Confirmo que já fiz logout e estou pronto para logar na conta de Destino (SELECT).", key="logout_confirm_checkbox_select")
    
    if logout_confirmed_select:
        select_auth_url = get_authorization_url(BLING_SELECT_CLIENT_ID, BLING_SELECT_REDIRECT_URI)
        st.markdown(f"**2. Clique aqui para autorizar a SELECT:** [Autorizar SELECT]({select_auth_url})")

        # Para testes locais, o usuário ainda pode precisar colar o código (em caso de falha de redirecionamento)
        if APP_URL_BASE == "http://localhost:8080" and not auth_code:
            temp_code_input = st.text_input("Cole o código de autorização da SELECT (somente para depuração local):", key="temp_select_code_input")
            if temp_code_input:
                st.warning("Por favor, cole o código, ou use a URL de redirecionamento para o seu ambiente Railway. Recarregue após colar.")
    else:
        st.info("Marque a caixa acima para prosseguir com a conexão da conta de destino.")


elif is_lojahi_connected and is_select_connected:
    # --- FASE 3: Migração ---
    st.header("Passo 3: Iniciar Migração de Imagens")
    st.success("✅ Origem (LOJAHI) Conectada com Sucesso!")
    st.success("✅ Destino (SELECT) Conectado com Sucesso!")
    st.markdown("Ambas as contas Bling estão autenticadas. Agora você pode migrar as imagens.")
    
    skus_input = st.text_area("Insira os SKUs dos produtos (um por linha, sem espaços extras):", height=200)
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
                    if migrate_sku_images(sku, tokens_to_use_lojahi, tokens_to_use_select):
                        migrated_count += 1
                    progress_bar.progress((i + 1) / total_skus)
                
                if migrated_count == total_skus:
                    st.success(f"🎉 Migração concluída! Todos os {migrated_count} SKUs foram migrados com sucesso.")
                else:
                    st.warning(f"Migração concluída com {migrated_count} de {total_skus} SKUs migrados. Verifique o log para detalhes de SKUs pendentes ou com erros.")
                log_message(f"Migração finalizada. {migrated_count}/{total_skus} SKUs migrados com sucesso.")
        else:
            st.warning("Por favor, insira pelo menos um SKU para iniciar a migração.")

    st.markdown("---")
    if st.button("Resetar Conexões (Apagar Tokens)", help="Isso removerá os tokens de acesso e forçará uma nova autenticação para ambas as contas Bling."):
        clear_all_tokens()
        st.success("Conexões resetadas! Reiniciando...")
        st.rerun()


# --- Exibir log de migração (sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader("Logs da Migração")
if os.path.exists(LOG_FILE_PATH):
    with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
        log_content = f.read()
        st.sidebar.download_button("Download Log", log_content, file_name="migration_log.txt", mime="text/plain")
        if st.sidebar.checkbox("Exibir Log Completo", key="show_full_log"):
            st.sidebar.text_area("Log de Migração", log_content, height=300)
else:
    st.sidebar.info("Nenhum log de migração disponível ainda.")
