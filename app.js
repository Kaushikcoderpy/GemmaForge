// app.js
document.addEventListener('DOMContentLoaded', () => {
    const forgeBtn = document.getElementById('forge-btn');
    const modularExecBtn = document.getElementById('modular-exec-btn');
    const rawSeedInput = document.getElementById('raw-seed');
    const humanStyleInput = document.getElementById('human-style');
    const sandboxCheckbox = document.getElementById('sandbox-mode');
    const consoleDiv = document.getElementById('console');
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const scrollBtn = document.getElementById('scroll-btn');
    const tabs = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    const currentTaskText = document.getElementById('current-task');

    let isAutoScrollEnabled = true;

    // --- UTILS ---
    function getTimestamp() {
        const now = new Date();
        return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}.${now.getMilliseconds().toString().padStart(3, '0')}`;
    }

    function appendLog(module, message, type = 'info', data = null) {
        const logEntry = document.createElement('div');
        logEntry.className = 'log-line';
        if (type === 'phase') logEntry.classList.add('active-phase');

        let messageHtml = message;
        if (data && (data.html || data.markdown)) {
            const content = data.html || data.markdown;
            messageHtml += ` <button class="copy-pill" data-content="${encodeURIComponent(content)}">COPY</button>`;
        }

        logEntry.innerHTML = `
            <span class="ts">${getTimestamp()}</span>
            <span class="mod">[${module.toUpperCase()}]</span>
            <span class="msg">${messageHtml}</span>
        `;

        document.querySelectorAll('.active-phase').forEach(el => el.classList.remove('active-phase'));
        consoleDiv.appendChild(logEntry);

        if (isAutoScrollEnabled) {
            consoleDiv.scrollTo({ top: consoleDiv.scrollHeight, behavior: 'smooth' });
        } else {
            scrollBtn.classList.add('visible');
        }
    }

    function setSystemState(state, active) {
        statusText.innerText = state;
        statusDot.classList.toggle('active', active);
    }

    // --- TABS ---
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.tab;
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`${target}-tab`).classList.add('active');
            currentTaskText.innerText = tab.innerText;
        });
    });

    // --- COPY FUNCTIONALITY ---
    consoleDiv.addEventListener('click', (e) => {
        if (e.target.classList.contains('copy-pill')) {
            const content = decodeURIComponent(e.target.dataset.content);
            navigator.clipboard.writeText(content).then(() => {
                const originalText = e.target.innerText;
                e.target.innerText = 'COPIED';
                setTimeout(() => e.target.innerText = originalText, 2000);
            });
        }
    });

    // --- SCROLLING ---
    consoleDiv.addEventListener('scroll', () => {
        const distanceFromBottom = consoleDiv.scrollHeight - consoleDiv.scrollTop - consoleDiv.clientHeight;
        if (distanceFromBottom > 100) {
            isAutoScrollEnabled = false;
            scrollBtn.classList.add('visible');
        } else {
            isAutoScrollEnabled = true;
            scrollBtn.classList.remove('visible');
        }
    });

    scrollBtn.addEventListener('click', () => {
        consoleDiv.scrollTo({ top: consoleDiv.scrollHeight, behavior: 'smooth' });
    });

    // --- PIPELINE EXECUTION ---
    forgeBtn.addEventListener('click', async () => {
        const raw_seed = rawSeedInput.value.trim();
        const human_style = humanStyleInput.value;
        const is_draft_mesh = sandboxCheckbox.checked;

        if (!raw_seed) {
            appendLog('ERROR', 'Seed input required for execution.', 'fatal');
            return;
        }

        forgeBtn.disabled = true;
        setSystemState('PROCESSING', true);
        consoleDiv.innerHTML = '';
        appendLog('NETWORK', `Handshaking with ${is_draft_mesh ? 'Aletheia Mode' : 'Full Pipeline'}...`);

        try {
            const response = await fetch('http://127.0.0.1:8000/api/forge', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ raw_seed, human_style, is_draft_mesh })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const parsed = JSON.parse(line.substring(6));
                        if (parsed.event === 'phase_update') {
                            appendLog('ORCH', parsed.message, 'phase');
                        } else if (parsed.event === 'fatal_error') {
                            appendLog('FATAL', parsed.message, 'fatal');
                        } else if (parsed.event === 'system_complete') {
                            appendLog('FINAL', parsed.message, 'success', parsed);
                        } else if (parsed.event === 'broadcast_update') {
                            appendLog(parsed.platform, parsed.message, parsed.status === 'failed' ? 'fatal' : 'platform');
                        } else if (parsed.event === 'broadcast_complete') {
                            appendLog('FINISH', parsed.message, 'success');
                        }
                    }
                }
            }
        } catch (error) {
            appendLog('NET_ERR', error.message, 'fatal');
        } finally {
            forgeBtn.disabled = false;
            setSystemState('IDLE', false);
        }
    });

    // --- MODULAR TOOL EXECUTION (Now SSE for Transparency) ---
    modularExecBtn.addEventListener('click', async () => {
        const tool = document.getElementById('modular-tool').value;
        const input = document.getElementById('modular-input').value.trim();

        if (!input) {
            appendLog('ERROR', 'Payload input required.', 'fatal');
            return;
        }

        modularExecBtn.disabled = true;
        setSystemState('TOOL_RUN', true);
        appendLog('MODULAR', `Executing ${tool} atomic function...`);

        try {
            const response = await fetch(`http://127.0.0.1:8000/api/modular/${tool}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ input_data: input })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const parsed = JSON.parse(line.substring(6));
                        if (parsed.event === 'phase_update') {
                            appendLog('RETRY', parsed.message, 'warn');
                        } else if (parsed.event === 'fatal_error') {
                            appendLog('ERROR', parsed.message, 'fatal');
                        } else if (parsed.event === 'system_complete') {
                            appendLog('RESULT', `Operation successful. Output attached.`, 'success', {markdown: parsed.result});
                        }
                    }
                }
            }
        } catch (error) {
            appendLog('NET_ERR', error.message, 'fatal');
        } finally {
            modularExecBtn.disabled = false;
            setSystemState('IDLE', false);
        }
    });
});