import streamlit as st
import requests
import os
import json
import time
from datetime import datetime
from urllib.parse import urlencode

# --- Configurações ---
BLING_API_BASE_URL = "https://www.bling.com.br/Api/v3"
APP_URL_BASE = os.getenv("APP_URL", "http://localhost:8501")

# Configurações OAuth para conta ORIGEM (LOJAHI)
BLING_LOJAHI_CLIENT_ID = os.getenv("BLING_LOJAHI_CLIENT_ID")
BLING_LOJAHI_CLIENT_SECRET = os.getenv("BLING_LOJAHI_CLIENT_SECRET")
BLING_LOJAHI_REDIRECT_URI = f"{APP_URL_BASE}/lojahi"
STATE_LOJAHI_FIXED = "lojahi_state_fixed_12345"

# Diretório de armazenamento
DEFAULT_STORAGE_PATH = "./app/data/storage"
STORAGE_PATH = os.getenv("STORAGE_PATH", DEFAULT_STORAGE_PATH)
os.makedirs(STORAGE_PATH, exist_ok=True)

# Arquivo de log
LOG_FILE = os.path.join(STORAGE_PATH, "migration.log")


# --- Funções Auxiliares ---
def log_message(message):
    """Registra mensagens no arquivo de log com timestamp."""
    timestamp = datetime.now().isoformat()
    log_entry = f"[{timestamp}] {message}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)
    print(log_entry.strip())


def save_tokens(account_name, tokens):
    """Salva tokens OAuth em arquivo JSON."""
    token_file = os.path.join(STORAGE_PATH, f"token_{account_name}.json")
    with open(token_file, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)
    log_message(f"Tokens de {account_name} salvos em {token_file}")


def load_tokens(account_name):
    """Carrega tokens OAuth de arquivo JSON."""
    token_file = os.path.join(STORAGE_PATH, f"token_{account_name}.json")
    if os.path.exists(token_file):
        with open(token_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def get_authorization_url(client_id, redirect_uri, state):
    """Gera URL de autorização OAuth."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state
    }
    return f"https://www.bling.com.br/Api/v3/oauth/authorize?{urlencode(params)}"


def get_access_token(client_id, client_secret, code, redirect_uri, state):
    """Troca código de autorização por tokens de acesso."""
    import base64
    
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "1.0"
    }
    
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri
    }
    
    response = requests.post(f"{BLING_API_BASE_URL}/oauth/token", headers=headers, data=data)
    response.raise_for_status()
    return response.json()


def download_image(url, local_path):
    """Baixa uma imagem de uma URL e salva localmente."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    with open(local_path, 'wb') as f:
        f.write(response.content)


def get_product_images(access_token, sku):
    """Extrai todas as imagens de um produto (pai + variações) pelo SKU."""
    log_message(f"🔍 [EXTRAÇÃO] Iniciando busca de imagens para SKU: {sku}")
    
    headers = {"Authorization": f"Bearer {access_token}"}
    all_images = []
    
    # 1. Buscar produto pelo SKU
    log_message(f"📡 [API] GET {BLING_API_BASE_URL}/produtos?codigo={sku}")
    response = requests.get(f"{BLING_API_BASE_URL}/produtos?codigo={sku}", headers=headers)
    response.raise_for_status()
    
    products = response.json().get('data', [])
    if not products:
        log_message(f"❌ [BUSCA] Nenhum produto encontrado com SKU: {sku}")
        return []
    
    product_id = products[0]['id']
    log_message(f"✅ [BUSCA] Produto encontrado - ID: {product_id}")
    
    # 2. Obter ficha completa do produto
    log_message(f"📡 [API] GET {BLING_API_BASE_URL}/produtos/{product_id}")
    response = requests.get(f"{BLING_API_BASE_URL}/produtos/{product_id}", headers=headers)
    response.raise_for_status()
    
    product_data = response.json().get('data', {})
    log_message(f"✅ [FICHA] Ficha completa obtida para produto ID {product_id}")
    
    # 3. Extrair imagens do produto pai
    midia = product_data.get('midia', {})
    log_message(f"🔍 [ANÁLISE] Tipo do campo 'midia': {type(midia).__name__}")
    
    if isinstance(midia, dict):
        imagens = midia.get('imagens', {})
        
        # Imagens internas
        internas = imagens.get('internas', [])
        log_message(f"📸 [PAI] Imagens internas encontradas: {len(internas)}")
        for img in internas:
            if img.get('link'):
                all_images.append(img)
                log_message(f"   ✓ Imagem interna adicionada: {img.get('link')[:100]}...")
        
        # Imagens externas
        externas = imagens.get('externas', [])
        log_message(f"📸 [PAI] Imagens externas encontradas: {len(externas)}")
        for img in externas:
            if img.get('link'):
                all_images.append(img)
                log_message(f"   ✓ Imagem externa adicionada: {img.get('link')[:100]}...")
    
    log_message(f"📊 [PAI] Total de imagens do produto pai: {len(all_images)}")
    
    # 4. Extrair imagens das variações
    variacoes = product_data.get('variacoes', [])
    if variacoes:
        log_message(f"🔄 [VARIAÇÕES] Produto tem {len(variacoes)} variações. Buscando imagens...")
        
        for idx, variacao in enumerate(variacoes, 1):
            variacao_id = variacao.get('id')
            variacao_nome = variacao.get('nome', 'Sem nome')[:50]
            
            log_message(f"📡 [VARIAÇÃO {idx}/{len(variacoes)}] ID: {variacao_id} | Nome: {variacao_nome}...")
            
            try:
                # Rate limiting
                time.sleep(0.5)
                
                response = requests.get(f"{BLING_API_BASE_URL}/produtos/{variacao_id}", headers=headers)
                response.raise_for_status()
                
                variacao_data = response.json().get('data', {})
                variacao_midia = variacao_data.get('midia', {})
                
                if isinstance(variacao_midia, dict):
                    variacao_imagens = variacao_midia.get('imagens', {})
                    
                    # Imagens internas da variação
                    variacao_internas = variacao_imagens.get('internas', [])
                    log_message(f"   📸 Imagens internas: {len(variacao_internas)}")
                    for img in variacao_internas:
                        if img.get('link') and img not in all_images:
                            all_images.append(img)
                    
                    # Imagens externas da variação
                    variacao_externas = variacao_imagens.get('externas', [])
                    log_message(f"   📸 Imagens externas: {len(variacao_externas)}")
                    for img in variacao_externas:
                        if img.get('link') and img not in all_images:
                            all_images.append(img)
                
                log_message(f"   ✅ Variação {idx} processada com sucesso")
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    log_message(f"   ⚠️ Rate limit atingido na variação {idx}. Aguardando...")
                    time.sleep(2)
                else:
                    log_message(f"   ❌ Erro ao buscar variação {idx}: {e.response.status_code}")
    else:
        log_message(f"ℹ️ [INFO] Produto não possui variações")
    
    # 5. Remover duplicatas (comparando por link)
    unique_images = []
    seen_links = set()
    for img in all_images:
        link = img.get('link')
        if link and link not in seen_links:
            unique_images.append(img)
            seen_links.add(link)
    
    log_message(f"🎯 [RESULTADO] Total de imagens únicas encontradas: {len(unique_images)}")
    log_message(f"📦 [EXTRAÇÃO] Finalizando busca para SKU {sku}")
    
    return unique_images


def download_sku_images(sku, access_token_origin, download_base_path):
    """Baixa todas as imagens de um SKU para um diretório local."""
    log_message(f"Iniciando download de imagens para SKU: {sku}")
    
    # Criar diretório para o SKU
    sku_path = os.path.join(download_base_path, sku)
    os.makedirs(sku_path, exist_ok=True)
    
    try:
        # 1. Obter imagens da conta de origem
        st.info(f"Obtendo imagens do SKU {sku} na conta de origem...")
        images_data_origin = get_product_images(access_token_origin, sku)
        
        if not images_data_origin:
            log_message(f"Nenhuma imagem encontrada para SKU {sku} na origem.")
            st.warning(f"Nenhuma imagem encontrada para SKU {sku}.")
            return False, 0
        
        # 2. Baixar todas as imagens
        downloaded_count = 0
        for img_data in images_data_origin:
            image_url = img_data.get('link')
            if image_url:
                file_name = os.path.basename(image_url).split('?')[0]
                local_image_path = os.path.join(sku_path, file_name)
                
                # Verificar se já foi baixada
                if os.path.exists(local_image_path):
                    log_message(f"✅ [CACHE] Imagem {file_name} já existe. Pulando download.")
                else:
                    st.info(f"Baixando imagem {file_name} do SKU {sku}...")
                    download_image(image_url, local_image_path)
                    downloaded_count += 1
                    log_message(f"📥 [DOWNLOAD] Imagem {file_name} baixada para {local_image_path}")
        
        total_images = len(images_data_origin)
        st.success(f"✅ SKU {sku}: {total_images} imagens salvas em {sku_path}")
        log_message(f"Download concluído para SKU {sku}: {total_images} imagens em {sku_path}")
        return True, total_images
        
    except requests.exceptions.HTTPError as e:
        error_message = f"Erro HTTP no download do SKU {sku}: {e.response.status_code} - {e.response.text}"
        st.error(error_message)
        log_message(error_message)
    except Exception as e:
        error_message = f"Erro inesperado no download do SKU {sku}: {e}"
        st.error(error_message)
        log_message(error_message)
    
    return False, 0


# --- Interface Streamlit ---
st.set_page_config(page_title="Bling Picture Downloader", layout="wide")
st.title("📥 Bling Picture Downloader")
st.markdown("Ferramenta para baixar imagens de produtos do Bling e organizar por SKU.")
st.markdown("---")

# --- Lógica de redirecionamento OAuth ---
query_params = st.query_params
auth_code = query_params.get("code")
state_received = query_params.get("state")

if auth_code and state_received == STATE_LOJAHI_FIXED:
    try:
        tokens = get_access_token(BLING_LOJAHI_CLIENT_ID, BLING_LOJAHI_CLIENT_SECRET, 
                                 auth_code, BLING_LOJAHI_REDIRECT_URI, state_received)
        save_tokens("lojahi", tokens)
        st.success("✅ Conta LOJAHI autenticada com sucesso! Redirecionando...")
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Erro ao autenticar: {e}")
        log_message(f"Erro ao autenticar LOJAHI: {e}")
        st.query_params.clear()

# --- Interface Principal ---
st.header("1️⃣ Autenticação")

# Verificar se já está autenticado
tokens_lojahi = load_tokens("lojahi")

col1, col2 = st.columns(2)

with col1:
    if tokens_lojahi:
        st.success("✅ Conta LOJAHI autenticada")
        if st.button("🔄 Reautenticar LOJAHI"):
            auth_url = get_authorization_url(BLING_LOJAHI_CLIENT_ID, BLING_LOJAHI_REDIRECT_URI, STATE_LOJAHI_FIXED)
            st.markdown(f"[Clique aqui para autenticar LOJAHI]({auth_url})")
    else:
        st.warning("⚠️ Conta LOJAHI não autenticada")
        auth_url = get_authorization_url(BLING_LOJAHI_CLIENT_ID, BLING_LOJAHI_REDIRECT_URI, STATE_LOJAHI_FIXED)
        st.markdown(f"[Clique aqui para autenticar LOJAHI]({auth_url})")

st.markdown("---")

# --- Configuração de Download ---
st.header("2️⃣ Configuração de Download")

download_path = st.text_input(
    "📁 Diretório de Download", 
    value=STORAGE_PATH,
    help="Caminho onde as imagens serão salvas. Cada SKU terá sua própria pasta."
)

st.info(f"💡 As imagens serão organizadas em: `{download_path}/[SKU]/imagem.jpg`")

st.markdown("---")

# --- Download de Imagens ---
st.header("3️⃣ Download de Imagens")

skus_input = st.text_area(
    "SKUs para Download (um por linha)",
    height=150,
    placeholder="CP-ZFD-17\nHUB-USB-C-5-1\nOUTRO-SKU"
)

if st.button("📥 Baixar Imagens", type="primary"):
    if not tokens_lojahi:
        st.error("❌ Você precisa autenticar a conta LOJAHI primeiro!")
    elif not skus_input.strip():
        st.error("❌ Digite pelo menos um SKU!")
    else:
        access_token_origin = tokens_lojahi.get("access_token")
        skus = [sku.strip() for sku in skus_input.split('\n') if sku.strip()]
        
        st.info(f"Iniciando download de {len(skus)} SKU(s)...")
        
        success_count = 0
        total_images = 0
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, sku in enumerate(skus, 1):
            status_text.text(f"Processando {idx}/{len(skus)}: {sku}")
            success, img_count = download_sku_images(sku, access_token_origin, download_path)
            
            if success:
                success_count += 1
                total_images += img_count
            
            progress_bar.progress(idx / len(skus))
        
        progress_bar.empty()
        status_text.empty()
        
        st.markdown("---")
        st.success(f"✅ Download concluído!")
        st.metric("SKUs processados", f"{success_count}/{len(skus)}")
        st.metric("Total de imagens", total_images)
        st.info(f"📁 Imagens salvas em: `{download_path}`")
        
        log_message(f"Download finalizado. {success_count}/{len(skus)} SKUs processados, {total_images} imagens baixadas.")

st.markdown("---")

# --- Visualizar Log ---
with st.expander("📋 Ver Log de Operações"):
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            log_content = f.read()
        st.text_area("Log", value=log_content, height=300)
    else:
        st.info("Nenhum log disponível ainda.")
