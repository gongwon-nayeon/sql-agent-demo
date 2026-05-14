// WebSocket 연결
let ws = null;
let isConnected = false;

// 스트리밍 상태
let currentStreamingMessage = null;

// DOM 요소
const messagesDiv = document.getElementById('messages');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const statusDiv = document.getElementById('status');
const statusText = statusDiv.querySelector('.status-text');

// WebSocket 연결
function connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/chat`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('✅ WebSocket 연결됨');
        isConnected = true;
        updateStatus('connected', '연결됨');
        sendBtn.disabled = false;
    };

    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleMessage(message);
    };

    ws.onerror = (error) => {
        console.error('❌ WebSocket 오류:', error);
        updateStatus('error', '연결 오류');
    };

    ws.onclose = () => {
        console.log('🔌 WebSocket 연결 종료');
        isConnected = false;
        updateStatus('disconnected', '연결 끊김');
        sendBtn.disabled = true;

        // 재연결 시도
        setTimeout(() => {
            console.log('🔄 재연결 시도...');
            connect();
        }, 3000);
    };
}

// 상태 업데이트
function updateStatus(status, text) {
    statusDiv.className = 'status ' + status;
    statusText.textContent = text;
}

// 메시지 처리
function handleMessage(message) {
    const { type, content, tool_name, args } = message;

    switch (type) {
        case 'system':
            addMessage('system', content);
            break;
        case 'user':
            // 사용자 메시지는 이미 UI에 추가됨
            break;
        case 'thinking':
            addThinkingMessage();
            break;
        case 'tool_call':
            // 도구 호출 시작
            addToolCallMessage(content, tool_name, args);
            break;
        case 'tool_result':
            // 도구 실행 결과
            addToolResultMessage(content, tool_name);
            break;
        case 'tool_start':
            addToolMessage(content, false);
            break;
        case 'tool_end':
            removeThinkingMessage();
            addToolMessage(content, true);
            break;
        case 'assistant_start':
            removeThinkingMessage();
            startStreamingMessage();
            break;
        case 'assistant_token':
            appendToStreamingMessage(content);
            break;
        case 'assistant_end':
            finishStreamingMessage();
            break;
        case 'assistant':
            removeThinkingMessage();
            addMessage('assistant', content);
            break;
        case 'suggested_questions':
            addSuggestedQuestions(message.questions);
            break;
        case 'error':
            removeThinkingMessage();
            addMessage('error', content);
            break;
    }

    scrollToBottom();
}

// 마크다운을 HTML로 변환
function parseMarkdown(text) {
    let html = text;

    // 한 줄로 된 테이블을 여러 줄로 분리 (전처리)
    // 예: | a | b | |---|---| | 1 | 2 | => 줄바꿈 추가
    html = html.replace(/(\|[^|\n]+\|)\s*(\|[\-:|\s]+\|)/g, '$1\n$2');
    html = html.replace(/(\|[\-:|\s]+\|)\s*(\|[^|\n]+\|)/g, '$1\n$2');

    // 임시로 코드 블록 저장 (다른 변환으로부터 보호)
    const codeBlocks = [];
    html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        const placeholder = `___CODEBLOCK_${codeBlocks.length}___`;
        codeBlocks.push(`<pre><code class="language-${lang || 'text'}">${escapeHtml(code.trim())}</code></pre>`);
        return placeholder;
    });

    // 테이블 변환 (마크다운 테이블) - 개선된 버전
    const tables = [];
    const lines = html.split(/\r?\n/);
    let i = 0;
    let newLines = [];

    while (i < lines.length) {
        const line = lines[i];

        // 테이블 시작 감지 (| 로 시작하고 끝나는 줄)
        if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
            const tableLines = [line];
            let j = i + 1;

            // 연속된 테이블 줄 수집
            while (j < lines.length && lines[j].trim().startsWith('|') && lines[j].trim().endsWith('|')) {
                tableLines.push(lines[j]);
                j++;
            }

            // 최소 2줄 이상이어야 테이블 (헤더 + 구분선 이상)
            if (tableLines.length >= 2) {
                const headerLine = tableLines[0];
                const separatorLine = tableLines[1];

                // 구분선 검증 (-, :, | 와 공백만 포함)
                if (separatorLine.match(/^\|[\s\-:|]+\|$/)) {
                    // 헤더 파싱
                    const headers = headerLine.split('|')
                        .map(h => h.trim())
                        .filter(h => h);

                    // 데이터 행 파싱
                    const rows = tableLines.slice(2).map(line =>
                        line.split('|')
                            .map(cell => cell.trim())
                            .filter(cell => cell)
                    );

                    // HTML 테이블 생성
                    let tableHtml = '<table class="markdown-table">';
                    tableHtml += '<thead><tr>';
                    headers.forEach(h => tableHtml += `<th>${parseInlineMarkdown(h)}</th>`);
                    tableHtml += '</tr></thead>';
                    tableHtml += '<tbody>';
                    rows.forEach(row => {
                        if (row.length > 0) {
                            tableHtml += '<tr>';
                            row.forEach(cell => tableHtml += `<td>${parseInlineMarkdown(cell)}</td>`);
                            tableHtml += '</tr>';
                        }
                    });
                    tableHtml += '</tbody></table>';

                    const placeholder = `___TABLE_${tables.length}___`;
                    tables.push(tableHtml);
                    newLines.push(placeholder);

                    i = j;
                    continue;
                }
            }
        }

        newLines.push(line);
        i++;
    }

    html = newLines.join('\n');

    // 인라인 코드 (`)
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // 볼드 (**)
    html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');

    // 이탤릭 (*)
    html = html.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

    // 링크 [text](url)
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    // 제목 (###, ##, #)
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // 리스트 (- 또는 *)
    html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');

    // 연속된 li를 ul로 묶기
    html = html.replace(/(<li>.*?<\/li>\n?)+/g, (match) => {
        return '<ul>' + match + '</ul>';
    });

    // 단락 구분 (빈 줄로 구분)
    const paragraphs = html.split(/\n\n+/);
    html = paragraphs.map(para => {
        para = para.trim();
        // 이미 HTML 태그로 시작하는 경우는 그대로
        if (para.startsWith('<') || para === '') {
            return para;
        }
        // 일반 텍스트는 p 태그로 감싸고 줄바꿈은 br로
        return '<p>' + para.replace(/\n/g, '<br>') + '</p>';
    }).join('\n');

    // 코드 블록 복원
    codeBlocks.forEach((block, index) => {
        html = html.replace(`___CODEBLOCK_${index}___`, block);
    });

    // 테이블 복원
    tables.forEach((table, index) => {
        html = html.replace(`___TABLE_${index}___`, table);
    });

    return html;
}

// HTML 이스케이프
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 인라인 마크다운 파싱 (테이블 셀용 - 볼드, 이탤릭, 코드 등)
function parseInlineMarkdown(text) {
    let html = escapeHtml(text);

    // 인라인 코드 (`)
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // 볼드 (**)
    html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');

    // 이탤릭 (*) - 볼드 이후에 처리
    html = html.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

    // 링크 [text](url)
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    return html;
}

// 메시지 추가
function addMessage(type, content) {
    const messageGroup = document.createElement('div');
    messageGroup.className = `message-group ${type}`;

    const message = document.createElement('div');
    message.className = `message ${type}-message`;

    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';

    // assistant 메시지는 마크다운 렌더링
    if (type === 'assistant') {
        messageContent.innerHTML = parseMarkdown(content);
    } else {
        messageContent.textContent = content;
    }

    message.appendChild(messageContent);
    messageGroup.appendChild(message);
    messagesDiv.appendChild(messageGroup);

    // Syntax highlighting 적용 (assistant 메시지의 코드 블록에)
    if (type === 'assistant' && typeof hljs !== 'undefined') {
        messageGroup.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
    }
}

// 스트리밍 메시지 관리
function startStreamingMessage() {
    const messageGroup = document.createElement('div');
    messageGroup.className = 'message-group assistant';
    messageGroup.id = 'streaming-message';

    const message = document.createElement('div');
    message.className = 'message assistant-message';

    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';
    messageContent.textContent = ''; // 빈 내용으로 시작

    message.appendChild(messageContent);
    messageGroup.appendChild(message);
    messagesDiv.appendChild(messageGroup);

    currentStreamingMessage = {
        element: messageGroup,
        content: messageContent,
        text: ''
    };

    scrollToBottom();
}

function appendToStreamingMessage(token) {
    if (currentStreamingMessage) {
        currentStreamingMessage.text += token;
        currentStreamingMessage.content.textContent = currentStreamingMessage.text;
        scrollToBottom();
    }
}

function finishStreamingMessage() {
    if (currentStreamingMessage) {
        const fullText = currentStreamingMessage.text;

        // 마크다운 파싱 적용
        currentStreamingMessage.content.innerHTML = parseMarkdown(fullText);

        // Syntax highlighting 적용
        if (typeof hljs !== 'undefined') {
            currentStreamingMessage.element.querySelectorAll('pre code').forEach((block) => {
                hljs.highlightElement(block);
            });
        }

        // ID 제거 (더 이상 스트리밍 중이 아님)
        currentStreamingMessage.element.removeAttribute('id');
        currentStreamingMessage = null;

        scrollToBottom();
    }
}

// 생각 중 메시지
let thinkingElement = null;

function addThinkingMessage() {
    removeThinkingMessage(); // 기존 것 제거

    const messageGroup = document.createElement('div');
    messageGroup.className = 'message-group assistant';
    messageGroup.id = 'thinking-message';

    const message = document.createElement('div');
    message.className = 'thinking-message';
    message.innerHTML = `
        🤔 생각 중
        <div class="thinking-dots">
            <span></span>
            <span></span>
            <span></span>
        </div>
    `;

    messageGroup.appendChild(message);
    messagesDiv.appendChild(messageGroup);
    thinkingElement = messageGroup;

    scrollToBottom();
}

function removeThinkingMessage() {
    if (thinkingElement) {
        thinkingElement.remove();
        thinkingElement = null;
    }
}

// 도구 메시지
function addToolMessage(content, isSuccess) {
    const messageGroup = document.createElement('div');
    messageGroup.className = 'message-group system';

    const message = document.createElement('div');
    message.className = `tool-message ${isSuccess ? 'success' : ''}`;
    message.textContent = content;

    messageGroup.appendChild(message);
    messagesDiv.appendChild(messageGroup);

    scrollToBottom();
}

// 도구 호출 메시지
function addToolCallMessage(content, toolName, args) {
    removeThinkingMessage(); // 생각 중 메시지 제거

    const messageGroup = document.createElement('div');
    messageGroup.className = 'message-group tool';

    const message = document.createElement('div');
    message.className = 'tool-call-message';

    let argsText = '';
    if (args && Object.keys(args).length > 0) {
        // SQL 쿼리는 코드 블록으로 포맷
        if (toolName === 'sql_db_query' || toolName === 'sql_db_query_checker') {
            if (args.query) {
                const sqlMarkdown = '```sql\n' + args.query + '\n```';
                argsText = `<div class="tool-args">${parseMarkdown(sqlMarkdown)}</div>`;
            }
        } else {
            // 다른 도구들은 기존 방식대로
            const argsList = Object.entries(args)
                .map(([key, value]) => `${key}: ${value}`)
                .join(', ');
            argsText = `<div class="tool-args">${argsList}</div>`;
        }
    }

    message.innerHTML = `
        <div class="tool-icon">🔧</div>
        <div class="tool-details">
            <div class="tool-name">${content}</div>
            ${argsText}
        </div>
    `;

    messageGroup.appendChild(message);
    messagesDiv.appendChild(messageGroup);

    // Syntax highlighting 적용
    if (typeof hljs !== 'undefined') {
        messageGroup.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
    }

    scrollToBottom();
}

// 도구 결과 메시지
function addToolResultMessage(content, toolName) {
    const messageGroup = document.createElement('div');
    messageGroup.className = 'message-group tool-result';

    const message = document.createElement('div');
    message.className = 'tool-result-message';

    const escaped = content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    message.innerHTML = `
        <div class="tool-result-icon">✓</div>
        <div class="tool-result-content">${escaped}</div>
    `;

    messageGroup.appendChild(message);
    messagesDiv.appendChild(messageGroup);

    scrollToBottom();
}

// 관련 질문 제안 버튼 추가
function addSuggestedQuestions(questions) {
    // 이전 관련 질문들 제거
    const existingSuggestions = document.querySelectorAll('.suggested-questions');
    existingSuggestions.forEach(el => el.remove());

    if (!questions || questions.length === 0) {
        return;
    }

    const messageGroup = document.createElement('div');
    messageGroup.className = 'message-group suggested-questions';

    const container = document.createElement('div');
    container.className = 'suggested-questions-container';

    questions.forEach(question => {
        const btn = document.createElement('button');
        btn.className = 'suggested-question-btn';
        btn.textContent = question;
        btn.onclick = () => {
            userInput.value = question;
            userInput.dispatchEvent(new Event('input'));
            sendMessage();
        };
        container.appendChild(btn);
    });

    messageGroup.appendChild(container);
    messagesDiv.appendChild(messageGroup);

    scrollToBottom();
}

// 메시지 전송
function sendMessage() {
    const query = userInput.value.trim();

    if (!query || !isConnected) {
        return;
    }

    // 이전 관련 질문들 제거 (새 질문 시작 시)
    const existingSuggestions = document.querySelectorAll('.suggested-questions');
    existingSuggestions.forEach(el => el.remove());

    // 초기 중앙정렬 해제 (첫 메시지 전송 시)
    messagesDiv.classList.remove('initial-state');

    // 사용자 메시지 표시
    addMessage('user', query);

    // WebSocket으로 전송
    ws.send(JSON.stringify({ query }));

    // 입력창 초기화
    userInput.value = '';
    userInput.style.height = 'auto';
    sendBtn.disabled = true;
}

// 스크롤 하단으로
function scrollToBottom() {
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// 이벤트 리스너
sendBtn.addEventListener('click', sendMessage);

userInput.addEventListener('input', () => {
    // 자동 높이 조절
    userInput.style.height = 'auto';
    userInput.style.height = userInput.scrollHeight + 'px';

    // 전송 버튼 활성화/비활성화
    sendBtn.disabled = !userInput.value.trim() || !isConnected;
});

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// 예시 질문 버튼
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('example-btn')) {
        const query = e.target.dataset.query;
        userInput.value = query;
        userInput.dispatchEvent(new Event('input'));
        userInput.focus();
    }
});

// 초기 연결
connect();
