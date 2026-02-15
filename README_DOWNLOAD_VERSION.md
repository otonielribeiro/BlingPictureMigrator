# Bling Picture Downloader - Versão Simplificada

## 📥 Sobre esta Versão

Esta é uma versão simplificada da aplicação que **apenas baixa e organiza** as imagens de produtos do Bling, sem fazer upload para a conta destino.

### Por que esta mudança?

Descobrimos que a API do Bling v3 **não suporta upload direto de imagens** via campo `midia.imagens.internas[]`. Este campo é **somente leitura** (read-only).

A API aceita apenas URLs externas via `midia.imagens.imagensURL[]`, mas essas URLs do S3 da Amazon expiram em ~7 dias, tornando a solução inadequada para migração permanente.

## 🎯 Funcionalidades

✅ **Download completo de imagens**
- Extrai imagens do produto pai
- Extrai imagens de todas as variações
- Remove duplicatas automaticamente

✅ **Organização automática**
- Cria uma pasta para cada SKU
- Estrutura: `[diretório_download]/[SKU]/imagem.jpg`

✅ **Interface intuitiva**
- Autenticação apenas da conta ORIGEM
- Configuração de diretório de download
- Processamento em lote de múltiplos SKUs

✅ **Logs detalhados**
- Registro de todas as operações
- Facilita debugging e auditoria

## 🚀 Como Usar

### 1. Autenticação

1. Acesse a aplicação
2. Clique em "Clique aqui para autenticar LOJAHI"
3. Autorize o acesso à sua conta Bling

### 2. Configurar Diretório

1. Defina o caminho onde as imagens serão salvas
2. Padrão: `./app/data/storage`
3. As imagens serão organizadas em: `[caminho]/[SKU]/`

### 3. Download

1. Digite os SKUs (um por linha) na caixa de texto
2. Clique em "📥 Baixar Imagens"
3. Aguarde o processamento
4. Verifique as imagens no diretório configurado

## 📂 Estrutura de Arquivos

```
diretório_download/
├── CP-ZFD-17/
│   ├── e3d264113369b8054f64e0906272cdeb
│   ├── c8cb536eca60ae94c17822f2f7eb46ef
│   ├── acba5c5368c79640c71187595c900d2c
│   └── ... (mais imagens)
├── HUB-USB-C-5-1/
│   ├── 0610ec6033060fba61d33c82a3174fdf
│   ├── 38397fca7b0f603c3581bf60b3650584
│   └── ... (mais imagens)
└── migration.log
```

## 🔄 Upload Manual para Conta Destino

Após baixar as imagens, você pode fazer o upload manual:

### Opção 1: Interface do Bling (Recomendado)

1. Acesse sua conta Bling DESTINO
2. Vá em **Produtos** > Editar produto
3. Aba **Imagens**
4. Clique em "anexar arquivos"
5. Selecione todas as imagens da pasta do SKU
6. Salve o produto

### Opção 2: Importação em Lote (Se disponível)

1. Consulte o suporte do Bling sobre importação em lote
2. Pode haver ferramentas ou APIs não documentadas

## 📊 Logs

Todos os logs são salvos em `[diretório_download]/migration.log`

Você pode visualizar os logs diretamente na interface expandindo a seção "📋 Ver Log de Operações".

## 🔧 Variáveis de Ambiente

```env
BLING_LOJAHI_CLIENT_ID=seu_client_id
BLING_LOJAHI_CLIENT_SECRET=seu_client_secret
APP_URL=https://sua-app.railway.app
STORAGE_PATH=./app/data/storage
```

## 📝 Notas Importantes

- **Rate Limiting**: A aplicação aguarda 0.5s entre requisições de variações para evitar bloqueio
- **Cache**: Imagens já baixadas não são baixadas novamente
- **Duplicatas**: Imagens duplicadas entre produto pai e variações são automaticamente removidas
- **Timeout**: Cada download tem timeout de 30s

## 🆘 Solução de Problemas

### "Nenhuma imagem encontrada para SKU"

- Verifique se o SKU existe na conta ORIGEM
- Verifique se o produto tem imagens cadastradas

### "Erro HTTP 429"

- Rate limit atingido
- A aplicação tenta novamente automaticamente
- Se persistir, aguarde alguns minutos

### "Erro de autenticação"

- Token expirado
- Clique em "🔄 Reautenticar LOJAHI"

## 📦 Versão Completa (Backup)

A versão completa com tentativa de upload está salva em:
`app/app_backup_full_migration.py`

Para restaurá-la:
```bash
cp app/app_backup_full_migration.py app/app.py
```

## 🎓 Aprendizados

### API do Bling v3 - Imagens

**Campos de Leitura (GET):**
- `midia.imagens.internas[]` - Imagens armazenadas no Bling
- `midia.imagens.externas[]` - URLs externas

**Campos de Escrita (PUT/PATCH):**
- `midia.imagens.imagensURL[]` - Apenas URLs externas
- ❌ **NÃO suporta** upload de arquivos via base64
- ❌ **NÃO suporta** campo `internas[]` para escrita

## 📞 Suporte

Para dúvidas sobre a API do Bling:
- Documentação: https://developer.bling.com.br
- Suporte: https://ajuda.bling.com.br

---

**Desenvolvido para migração de imagens entre contas Bling**
