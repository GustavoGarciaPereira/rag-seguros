// ------------------------------------------------------------------ //
// XSS: nunca inserir conteúdo externo via innerHTML sem escape        //
// ------------------------------------------------------------------ //
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

// Evita "Unexpected end of JSON input" quando o servidor retorna
// resposta vazia (502/504/OOM no Render). Sempre retorna um objeto.
async function safeParseJson(response) {
    const text = await response.text();
    if (!text) return { detail: `Erro HTTP ${response.status} (resposta vazia)` };
    try { return JSON.parse(text); }
    catch { return { detail: `Resposta invalida do servidor (HTTP ${response.status})` }; }
}

// ------------------------------------------------------------------ //
// Drawer                                                               //
// ------------------------------------------------------------------ //
const drawer = document.getElementById('sidebar-drawer');
const overlay = document.getElementById('drawer-overlay');

function openDrawer() {
    drawer.classList.add('open');
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeDrawer() {
    drawer.classList.remove('open');
    overlay.classList.remove('open');
    document.body.style.overflow = '';
}

document.getElementById('menu-btn').addEventListener('click', openDrawer);
document.getElementById('close-drawer-btn').addEventListener('click', closeDrawer);
overlay.addEventListener('click', closeDrawer);

// ------------------------------------------------------------------ //
// Elementos do DOM                                                     //
// ------------------------------------------------------------------ //
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const uploadBtn = document.getElementById('upload-btn');
const uploadModal = document.getElementById('upload-modal');
const closeModal = document.getElementById('close-modal');
const pdfFileInput = document.getElementById('pdf-file');
const confirmUploadBtn = document.getElementById('confirm-upload');
const cancelUploadBtn = document.getElementById('cancel-upload');
const removeFileBtn = document.getElementById('remove-file');
const selectedFileDiv = document.getElementById('selected-file');
const uploadProgress = document.getElementById('upload-progress');
const progressBar = document.getElementById('progress-bar');
const progressPercent = document.getElementById('progress-percent');
const uploadStatus = document.getElementById('upload-status');
const refreshStatsBtn = document.getElementById('refresh-stats');
const connectionStatus = document.getElementById('connection-status');

// ------------------------------------------------------------------ //
// Estado                                                               //
// ------------------------------------------------------------------ //
let selectedFile = null;
let isProcessing = false;
let messageCounter = 0;
let selectedDocumentType = null;
let wizardSinistroType = null;

// ------------------------------------------------------------------ //
// Sugestões por categoria                                              //
// ------------------------------------------------------------------ //
const SUGGESTIONS = {
    apolice:   ['O que está coberto?', 'Qual o período de vigência?', 'Quem são os beneficiários?'],
    sinistro:  ['Como acionar o sinistro?', 'Quais documentos preciso?', 'Qual o prazo de resposta?'],
    cobertura: ['O que não está coberto?', 'Há carência?', 'Qual o limite de cobertura?'],
    franquia:  ['Qual o valor da franquia?', 'Quando ela é cobrada?', 'Há franquia reduzida?'],
    endosso:   ['O que mudou na apólice?', 'Quando entra em vigor?', 'Como solicitar um endosso?'],
};

// ------------------------------------------------------------------ //
// Botões de categoria                                                  //
// ------------------------------------------------------------------ //
document.querySelectorAll('.category-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const type = btn.dataset.type;
        if (selectedDocumentType === type) {
            selectedDocumentType = null;
            btn.classList.remove('active');
            hideSuggestions();
        } else {
            document.querySelectorAll('.category-btn').forEach(b => b.classList.remove('active'));
            selectedDocumentType = type;
            btn.classList.add('active');
            showSuggestions(type);
        }
    });
});

function showSuggestions(type) {
    const bar = document.getElementById('suggestion-bar');
    bar.innerHTML = (SUGGESTIONS[type] || []).map(s =>
        `<button class="suggestion-chip" data-question="${escapeHtml(s)}">${escapeHtml(s)}</button>`
    ).join('');
    bar.classList.remove('hidden');
    bar.querySelectorAll('.suggestion-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const q = chip.dataset.question;
            if (type === 'sinistro' && q === 'Como acionar o sinistro?') {
                openWizard();
                return;
            }
            chatInput.value = q;
            chatInput.focus();
        });
    });
}

function hideSuggestions() {
    const bar = document.getElementById('suggestion-bar');
    bar.classList.add('hidden');
    bar.innerHTML = '';
}

// ------------------------------------------------------------------ //
// Wizard — Sinistro                                                   //
// ------------------------------------------------------------------ //
const wizardModal = document.getElementById('wizard-modal');

function openWizard() {
    wizardSinistroType = null;
    document.getElementById('wizard-step-1').classList.remove('hidden');
    document.getElementById('wizard-step-2').classList.add('hidden');
    document.getElementById('wizard-back').classList.add('hidden');
    document.getElementById('wizard-next').classList.remove('hidden');
    document.getElementById('wizard-finish').classList.add('hidden');
    document.getElementById('wizard-next').disabled = true;
    document.getElementById('wizard-date').value = '';
    document.querySelectorAll('.sinistro-type-btn').forEach(b => b.classList.remove('selected'));
    wizardModal.classList.remove('hidden');
}

document.getElementById('close-wizard').addEventListener('click', () => {
    wizardModal.classList.add('hidden');
});
wizardModal.addEventListener('click', e => {
    if (e.target === wizardModal) wizardModal.classList.add('hidden');
});

document.querySelectorAll('.sinistro-type-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.sinistro-type-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        wizardSinistroType = btn.dataset.val;
        document.getElementById('wizard-next').disabled = false;
    });
});

document.getElementById('wizard-next').addEventListener('click', () => {
    document.getElementById('wizard-step-1').classList.add('hidden');
    document.getElementById('wizard-step-2').classList.remove('hidden');
    document.getElementById('wizard-back').classList.remove('hidden');
    document.getElementById('wizard-next').classList.add('hidden');
    document.getElementById('wizard-finish').classList.remove('hidden');
    document.getElementById('wizard-date').focus();
});

document.getElementById('wizard-back').addEventListener('click', () => {
    document.getElementById('wizard-step-2').classList.add('hidden');
    document.getElementById('wizard-step-1').classList.remove('hidden');
    document.getElementById('wizard-back').classList.add('hidden');
    document.getElementById('wizard-next').classList.remove('hidden');
    document.getElementById('wizard-finish').classList.add('hidden');
});

document.getElementById('wizard-finish').addEventListener('click', () => {
    const date = document.getElementById('wizard-date').value.trim();
    const datePart = date ? ` ocorrido em ${date}` : '';
    chatInput.value = `Como acionar sinistro de ${wizardSinistroType}${datePart}?`;
    wizardModal.classList.add('hidden');
    chatInput.focus();
});

// ------------------------------------------------------------------ //
// Inicialização                                                        //
// ------------------------------------------------------------------ //
document.addEventListener('DOMContentLoaded', function () {
    checkConnection();
    loadStats();
    checkInitialStatus();
    renderHistory();
});

async function checkInitialStatus() {
    try {
        const response = await fetch('/status');
        const data = await response.json();
        if (data.ready) enableChat();
    } catch (error) {
        console.error('Erro ao verificar status inicial', error);
    }
}

async function checkConnection() {
    try {
        const response = await fetch('/health');
        updateConnectionStatus(response.ok);
    } catch (error) {
        updateConnectionStatus(false);
    }
}

function updateConnectionStatus(connected) {
    const dot  = connectionStatus.querySelector('div');
    const text = connectionStatus.querySelector('span');
    if (connected) {
        dot.className = 'w-2.5 h-2.5 rounded-full bg-green-500';
        text.textContent = 'Conectado';
        text.className = 'text-sm text-green-600 hidden sm:inline';
    } else {
        dot.className = 'w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse';
        text.textContent = 'Desconectado';
        text.className = 'text-sm text-red-600 hidden sm:inline';
    }
}

async function loadStats() {
    try {
        const response = await fetch('/stats');
        const data = await response.json();

        document.getElementById('chunk-count').textContent = data.vector_store.total_chunks || 0;
        document.getElementById('doc-count').textContent = data.vector_store.total_chunks > 0 ? '1+' : '0';

        const aiStatus = document.getElementById('ai-status');
        if (data.llm_service.status === 'connected') {
            aiStatus.textContent = 'Conectado';
            aiStatus.className = 'font-bold text-sm text-green-500';
        } else {
            aiStatus.textContent = 'Desconectado';
            aiStatus.className = 'font-bold text-sm text-red-500';
        }
    } catch (error) {
        console.error('Erro ao carregar estatísticas:', error);
    }
}

function enableChat() {
    if (!chatInput.disabled) return;
    chatInput.disabled = false;
    sendBtn.disabled = false;
    document.getElementById('input-hint').innerHTML =
        '<i class="fas fa-check-circle mr-1 text-green-500"></i> Chat habilitado! Faca sua pergunta.';
    chatInput.placeholder = 'Ex: Qual e o valor da franquia?';
    addSystemMessage('Chat habilitado! Voce pode fazer perguntas sobre o documento carregado.');
}

// ------------------------------------------------------------------ //
// Mensagens                                                            //
// ------------------------------------------------------------------ //
function addMessage(content, sender, isSystem = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `mb-3 max-w-[80%] p-4 fade-in ${isSystem
        ? 'chat-message-system'
        : (sender === 'user' ? 'chat-message-user' : 'chat-message-assistant')}`;

    if (sender === 'assistant') {
        const renderedHtml = marked.parse(content);
        messageDiv.innerHTML = `
            <div class="flex items-start space-x-3">
                <div class="bg-blue-100 text-blue-600 p-2 rounded-full flex-shrink-0">
                    <i class="fas fa-robot"></i>
                </div>
                <div class="flex-grow min-w-0">
                    <div class="font-medium text-gray-700 mb-1 text-sm">Assistente</div>
                    <div class="response-text prose text-gray-800 text-sm" data-markdown="${escapeHtml(content)}">${renderedHtml}</div>
                    <button class="copy-btn mt-2 text-xs text-gray-400 hover:text-blue-500 transition duration-200 flex items-center space-x-1">
                        <i class="fas fa-copy"></i>
                        <span>Copiar resposta</span>
                    </button>
                </div>
            </div>
        `;
        messageDiv.querySelector('.copy-btn').addEventListener('click', async () => {
            const text = messageDiv.querySelector('.response-text').dataset.markdown;
            try {
                await navigator.clipboard.writeText(text);
                const span = messageDiv.querySelector('.copy-btn span');
                span.textContent = 'Copiado!';
                setTimeout(() => { span.textContent = 'Copiar resposta'; }, 2000);
            } catch (e) {
                console.error('Clipboard error:', e);
            }
        });
    } else if (sender === 'user') {
        messageDiv.innerHTML = `
            <div class="flex items-start space-x-3 flex-row-reverse">
                <div class="bg-blue-600 text-white p-2 rounded-full flex-shrink-0">
                    <i class="fas fa-user"></i>
                </div>
                <div class="flex-grow text-right min-w-0">
                    <div class="font-medium text-white mb-1 text-sm">Voce</div>
                    <div class="text-white whitespace-pre-wrap text-sm">${escapeHtml(content)}</div>
                </div>
            </div>
        `;
    } else {
        messageDiv.innerHTML = `
            <div class="flex items-center space-x-2">
                <i class="fas fa-info-circle text-yellow-500"></i>
                <div class="text-sm">${escapeHtml(content)}</div>
            </div>
        `;
    }

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addSystemMessage(content) {
    addMessage(content, 'system', true);
}

// ------------------------------------------------------------------ //
// Histórico (localStorage)                                            //
// ------------------------------------------------------------------ //
const HISTORY_KEY = 'rag_question_history';

function addToHistory(question) {
    let history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    history = history.filter(q => q !== question);
    history.unshift(question);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 10)));
    renderHistory();
}

function renderHistory() {
    const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    const list = document.getElementById('history-list');
    if (history.length === 0) {
        list.innerHTML = '<p class="text-gray-400 text-sm italic">Nenhuma pergunta ainda.</p>';
        return;
    }
    list.innerHTML = history.map((q, idx) =>
        `<div class="history-item cursor-pointer hover:bg-blue-50 p-2 rounded-lg text-sm text-gray-700 truncate border border-transparent hover:border-blue-100 transition duration-150" data-idx="${idx}" title="${escapeHtml(q)}">${escapeHtml(q)}</div>`
    ).join('');
    list.querySelectorAll('.history-item').forEach(item => {
        item.addEventListener('click', () => {
            const h = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
            chatInput.value = h[parseInt(item.dataset.idx)] || '';
            chatInput.focus();
            closeDrawer();
        });
    });
}

document.getElementById('clear-history').addEventListener('click', () => {
    localStorage.removeItem(HISTORY_KEY);
    renderHistory();
});

// ------------------------------------------------------------------ //
// Streaming helpers                                                    //
// ------------------------------------------------------------------ //
function buildTypingIndicator() {
    const el = document.createElement('div');
    el.id = 'typing-indicator';
    el.className = 'chat-message-assistant mb-3 max-w-[80%] p-4';
    el.innerHTML = `
        <div class="flex items-center space-x-3">
            <div class="bg-blue-100 text-blue-600 p-2 rounded-full flex-shrink-0">
                <i class="fas fa-robot"></i>
            </div>
            <div class="flex-grow">
                <div class="font-medium text-gray-700 mb-1 text-sm">Assistente</div>
                <div class="text-gray-600 flex items-center space-x-2 text-sm">
                    <div class="flex space-x-1">
                        <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                        <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay:0.1s"></div>
                        <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay:0.2s"></div>
                    </div>
                    <span>Buscando nos documentos...</span>
                </div>
            </div>
        </div>
    `;
    return el;
}

// Creates the assistant message bubble used during streaming.
// Returns { msgDiv, textDiv } for live updates.
function buildStreamingBubble(msgId, contextData) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-message-assistant mb-3 max-w-[80%] p-4 fade-in';

    const contextCount = contextData.length;
    const contextItemsHtml = contextData.map((ctx, i) => `
        <div class="mb-2 pb-2 border-b border-gray-200 last:border-0">
            <div class="font-medium text-gray-700">Trecho ${i + 1}
                <span class="font-normal text-gray-500">— ${escapeHtml(ctx.seguradora || '?')} | Pág. ${escapeHtml(String(ctx.page))} | Score: ${escapeHtml(String(ctx.relevance_score))}</span>
            </div>
            <div class="text-gray-600 text-sm mt-0.5">${escapeHtml(ctx.text)}</div>
        </div>
    `).join('');

    msgDiv.innerHTML = `
        <div class="flex items-start space-x-3">
            <div class="bg-blue-100 text-blue-600 p-2 rounded-full flex-shrink-0">
                <i class="fas fa-robot"></i>
            </div>
            <div class="flex-grow min-w-0">
                <div class="font-medium text-gray-700 mb-1 text-sm">Assistente</div>
                <div class="stream-text prose text-gray-800 text-sm"></div>
                <button class="copy-btn mt-2 text-xs text-gray-400 hover:text-blue-500 transition duration-200 flex items-center space-x-1">
                    <i class="fas fa-copy"></i><span>Copiar resposta</span>
                </button>
                ${contextCount > 0 ? `
                <div class="text-xs text-gray-500 mt-2">
                    <i class="fas fa-search mr-1"></i>
                    Baseado em <strong>${contextCount}</strong> trecho(s) do documento
                    <button class="show-context-btn ml-2 text-blue-500 hover:text-blue-700 underline">Ver fontes</button>
                    <div id="context-details-${msgId}" class="hidden mt-2 p-3 bg-gray-50 rounded-lg text-left">
                        ${contextItemsHtml}
                    </div>
                </div>` : ''}
            </div>
        </div>
    `;

    const textDiv = msgDiv.querySelector('.stream-text');

    // Copy button — reads the data-markdown attribute set during streaming
    msgDiv.querySelector('.copy-btn').addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(textDiv.dataset.markdown || '');
            const span = msgDiv.querySelector('.copy-btn span');
            span.textContent = 'Copiado!';
            setTimeout(() => { span.textContent = 'Copiar resposta'; }, 2000);
        } catch (_) {}
    });

    // Toggle context details
    if (contextCount > 0) {
        const toggleBtn = msgDiv.querySelector('.show-context-btn');
        const detailsDiv = document.getElementById(`context-details-${msgId}`);
        toggleBtn.addEventListener('click', () => {
            detailsDiv.classList.toggle('hidden');
            toggleBtn.textContent = detailsDiv.classList.contains('hidden')
                ? 'Ver fontes' : 'Ocultar fontes';
        });
    }

    return { msgDiv, textDiv };
}

// ------------------------------------------------------------------ //
// Enviar pergunta                                                      //
// ------------------------------------------------------------------ //
async function sendQuestion() {
    const question = chatInput.value.trim();
    if (!question || isProcessing) return;

    addToHistory(question);
    addMessage(question, 'user');
    chatInput.value = '';

    const typingIndicator = buildTypingIndicator();
    chatMessages.appendChild(typingIndicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    isProcessing = true;
    sendBtn.disabled = true;

    try {
        const seguradoraFilter = document.getElementById('seguradora-filter').value;
        const ramoFilter = document.getElementById('ramo-filter').value;
        const requestBody = { question, top_k: 15 };
        const filter = {};
        if (seguradoraFilter) filter.seguradora = seguradoraFilter;
        if (ramoFilter) filter.ramo = ramoFilter;
        if (Object.keys(filter).length > 0) requestBody.filter = filter;
        if (selectedDocumentType) requestBody.document_type = selectedDocumentType;

        const response = await fetch('/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        // Non-streaming HTTP errors (e.g. 400 validation, 500 before stream starts)
        if (!response.ok || !response.body) {
            typingIndicator.remove();
            const data = await safeParseJson(response);
            addMessage(`Erro: ${data.detail || `HTTP ${response.status}`}`, 'assistant');
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullText = '';
        let msgDiv = null;
        let textDiv = null;
        const msgId = ++messageCounter;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // SSE events are delimited by a blank line (\n\n or \r\n\r\n).
            // We split on either variant so CRLF responses from proxies work too.
            const eventBlocks = buffer.split(/\r?\n\r?\n/);
            buffer = eventBlocks.pop() ?? ''; // keep the incomplete trailing fragment

            for (const block of eventBlocks) {
                if (!block.trim()) continue;

                // Find the first "data:" line inside the block.
                // SSE blocks can also carry "event:", "id:", comment lines, etc.
                let jsonStr = null;
                for (const line of block.split(/\r?\n/)) {
                    if (/^data:/.test(line)) {
                        // Strip "data:" and any single leading space (per SSE spec)
                        jsonStr = line.replace(/^data:\s?/, '');
                        break;
                    }
                }
                if (jsonStr === null || jsonStr === '') continue;

                let event;
                try {
                    event = JSON.parse(jsonStr);
                } catch (parseErr) {
                    console.error('[SSE] JSON.parse falhou:', parseErr, '| raw:', jsonStr);
                    continue;
                }

                try {
                    if (event.type === 'context') {
                        typingIndicator.remove();
                        ({ msgDiv, textDiv } = buildStreamingBubble(msgId, event.data));
                        chatMessages.appendChild(msgDiv);
                        chatMessages.scrollTop = chatMessages.scrollHeight;

                    } else if (event.type === 'text') {
                        // Guard: text before context on very fast responses
                        if (!msgDiv) {
                            typingIndicator.remove();
                            ({ msgDiv, textDiv } = buildStreamingBubble(msgId, []));
                            chatMessages.appendChild(msgDiv);
                        }
                        fullText += event.data;
                        textDiv.dataset.markdown = fullText;
                        textDiv.innerHTML = marked.parse(fullText);
                        chatMessages.scrollTop = chatMessages.scrollHeight;

                    } else if (event.type === 'no_context') {
                        typingIndicator.remove();
                        addMessage(
                            'Nao encontrei informacoes relevantes nos documentos filtrados para responder sua pergunta.',
                            'assistant'
                        );

                    } else if (event.type === 'error') {
                        if (typingIndicator.parentNode) typingIndicator.remove();
                        console.error('[SSE] Evento de erro recebido do servidor:', event.data);
                        addMessage(`Erro ao processar: ${escapeHtml(String(event.data))}`, 'assistant');
                    }
                } catch (handlerErr) {
                    console.error('[SSE] Erro ao processar evento:', handlerErr, '| event:', event);
                }
            }
        }

        // If the stream ended without any event (empty body / aborted connection),
        // remove the spinner that would otherwise be stuck on screen.
        if (typingIndicator.parentNode) {
            typingIndicator.remove();
            addMessage('A resposta chegou vazia. Tente novamente.', 'assistant');
        }

        // Re-render final markdown to ensure no partial Markdown tokens remain
        if (textDiv && fullText) {
            textDiv.innerHTML = marked.parse(fullText);
        }

    } catch (error) {
        console.error('[sendQuestion] Erro inesperado:', error);
        console.error('[sendQuestion] Stack:', error?.stack);
        document.getElementById('typing-indicator')?.remove();
        addMessage('Erro de conexao com o servidor. Verifique se o servidor esta rodando.', 'assistant');
    } finally {
        isProcessing = false;
        sendBtn.disabled = false;
        chatInput.focus();
    }
}

// ------------------------------------------------------------------ //
// Upload de PDF                                                        //
// ------------------------------------------------------------------ //
const MAX_UPLOAD_SIZE = 50 * 1024 * 1024;

pdfFileInput.addEventListener('change', function (e) {
    const file = e.target.files[0];
    if (!file) return;

    if (file.type !== 'application/pdf') {
        alert('Por favor, selecione um arquivo PDF valido.');
        pdfFileInput.value = '';
        return;
    }

    if (file.size > MAX_UPLOAD_SIZE) {
        alert(`Arquivo muito grande: ${formatFileSize(file.size)}. O limite maximo e ${formatFileSize(MAX_UPLOAD_SIZE)}.`);
        pdfFileInput.value = '';
        return;
    }

    selectedFile = file;
    document.getElementById('file-name').textContent = file.name;
    document.getElementById('file-size').textContent = formatFileSize(file.size);
    selectedFileDiv.classList.remove('hidden');
    confirmUploadBtn.disabled = false;
});

removeFileBtn.addEventListener('click', function () {
    selectedFile = null;
    pdfFileInput.value = '';
    selectedFileDiv.classList.add('hidden');
    confirmUploadBtn.disabled = true;
});

confirmUploadBtn.addEventListener('click', async function () {
    if (!selectedFile) return;

    const formData = new FormData();
    formData.append('file', selectedFile);

    uploadProgress.classList.remove('hidden');
    confirmUploadBtn.disabled = true;
    cancelUploadBtn.disabled = true;

    let progress = 0;
    const progressInterval = setInterval(() => {
        progress += 5;
        if (progress > 90) clearInterval(progressInterval);
        updateProgress(progress, 'Processando documento...');
    }, 200);

    try {
        const response = await fetch('/upload', { method: 'POST', body: formData });
        clearInterval(progressInterval);

        const data = await safeParseJson(response);
        if (response.ok) {
            updateProgress(100, 'Documento processado com sucesso!');
            setTimeout(() => {
                loadStats();
                enableChat();
                setTimeout(() => {
                    closeUploadModal();
                    addSystemMessage(`Documento "${escapeHtml(data.filename)}" carregado com sucesso! ${Number(data.chunks_added)} trechos indexados.`);
                }, 2000);
            }, 1000);
        } else {
            updateProgress(0, `Erro: ${data.detail || `HTTP ${response.status}`}`);
            confirmUploadBtn.disabled = false;
            cancelUploadBtn.disabled = false;
        }
    } catch (error) {
        clearInterval(progressInterval);
        updateProgress(0, `Erro de conexao: ${error.message}`);
        confirmUploadBtn.disabled = false;
        cancelUploadBtn.disabled = false;
    }
});

function updateProgress(percent, message) {
    progressBar.style.width = `${percent}%`;
    progressPercent.textContent = `${percent}%`;
    uploadStatus.textContent = message;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

uploadBtn.addEventListener('click', function () {
    uploadModal.classList.remove('hidden');
});

function closeUploadModal() {
    uploadModal.classList.add('hidden');
    selectedFile = null;
    pdfFileInput.value = '';
    selectedFileDiv.classList.add('hidden');
    uploadProgress.classList.add('hidden');
    confirmUploadBtn.disabled = true;
    cancelUploadBtn.disabled = false;
    updateProgress(0, '');
}

closeModal.addEventListener('click', closeUploadModal);
cancelUploadBtn.addEventListener('click', closeUploadModal);
uploadModal.addEventListener('click', function (e) {
    if (e.target === uploadModal) closeUploadModal();
});

refreshStatsBtn.addEventListener('click', loadStats);

chatInput.addEventListener('keypress', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
    }
});

sendBtn.addEventListener('click', sendQuestion);

// ------------------------------------------------------------------ //
// Drag & Drop                                                          //
// ------------------------------------------------------------------ //
const dropZone = uploadModal.querySelector('.border-dashed');

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(ev => {
    dropZone.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); });
});

['dragenter', 'dragover'].forEach(ev => {
    dropZone.addEventListener(ev, () => dropZone.classList.add('border-blue-500', 'bg-blue-50'));
});

['dragleave', 'drop'].forEach(ev => {
    dropZone.addEventListener(ev, () => dropZone.classList.remove('border-blue-500', 'bg-blue-50'));
});

dropZone.addEventListener('drop', function (e) {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        const file = files[0];
        if (file.type === 'application/pdf') {
            const dt = new DataTransfer();
            dt.items.add(file);
            pdfFileInput.files = dt.files;
            pdfFileInput.dispatchEvent(new Event('change'));
        } else {
            alert('Por favor, solte apenas arquivos PDF.');
        }
    }
});
