// app.js
document.addEventListener('DOMContentLoaded', () => {
    const forgeBtn = document.getElementById('forge-btn');
    const rawSeedInput = document.getElementById('raw-seed');
    const humanStyleInput = document.getElementById('human-style');
    const consoleDiv = document.getElementById('console');
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');

    function getTimestamp() {
        const now = new Date();
        return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}.${now.getMilliseconds().toString().padStart(3, '0')}`;
    }

    function appendLog(module, message, type = 'info') {
        let modClass = '';
        if (type === 'phase') modClass = 'mod-phase';
        else if (type === 'platform') modClass = 'mod-platform';
        else if (type === 'fatal') modClass = 'mod-fatal';
        else if (type === 'success') modClass = 'mod-success';

        const logEntry = document.createElement('div');
        logEntry.className = 'log-line';
        logEntry.innerHTML = `
            <span class="log-timestamp">${getTimestamp()}</span>
            <span class="log-module ${modClass}">[${module.toUpperCase()}]</span>
            <span class="log-message">${message}</span>
        `;

        consoleDiv.appendChild(logEntry);
        consoleDiv.scrollTo({ top: consoleDiv.scrollHeight, behavior: 'smooth' });
    }

    function setSystemState(state, active) {
        statusText.innerText = state;
        statusDot.classList.toggle('active', active);
    }

    forgeBtn.addEventListener('click', async () => {
        const raw_seed = rawSeedInput.value.trim();
        const human_style = humanStyleInput.value;

        if (!raw_seed) {
            appendLog('VALIDATION', 'Execution halted: Raw seed payload is empty.', 'fatal');
            return;
        }

        forgeBtn.disabled = true;
        forgeBtn.classList.add('loading');
        forgeBtn.querySelector('span').innerText = 'Executing Pipeline...';
        setSystemState('EXECUTING_PIPELINE', true);
        consoleDiv.innerHTML = '';

        appendLog('NETWORK', 'Establishing SSE connection to localhost:8000/api/forge...');

        try {
            const response = await fetch('http://127.0.0.1:8000/api/forge', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream'
                },
                body: JSON.stringify({ raw_seed, human_style })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

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
                        try {
                            const parsed = JSON.parse(line.substring(6));

                            if (parsed.event === 'phase_update') {
                                appendLog('ORCHESTRATOR', parsed.message, 'phase');
                            } else if (parsed.event === 'platform_update') {
                                const err = parsed.error ? ` | ERR: ${parsed.error}` : '';
                                appendLog(`SPOKE_${parsed.platform}`, `Status: ${parsed.status.toUpperCase()}${err}`, parsed.status === 'failed' ? 'fatal' : 'platform');
                            } else if (parsed.event === 'fatal_error') {
                                appendLog('EXCEPTION', parsed.message, 'fatal');
                            } else if (parsed.event === 'system_complete') {
                                appendLog('SYS_EXIT', parsed.message, 'success');
                            } else {
                                appendLog('STDOUT', parsed.message || JSON.stringify(parsed));
                            }
                        } catch (e) {
                            appendLog('SYS_WARN', `Malformed buffer chunk: ${line.substring(0, 50)}...`);
                        }
                    }
                }
            }
        } catch (error) {
            appendLog('SOCKET_ERR', error.message, 'fatal');
        } finally {
            forgeBtn.disabled = false;
            forgeBtn.classList.remove('loading');
            forgeBtn.querySelector('span').innerText = 'Ignite Engine Pipeline';
            setSystemState('PROCESS_IDLE', false);
            appendLog('NETWORK', 'Socket connection closed.');
        }
    });
});
// Add these enhancements to your script.js

function appendLog(module, message, type = 'info') {
    const logEntry = document.createElement('div');
    logEntry.className = 'log-line';

    // Add a specialized class for the current action
    if (type === 'phase') logEntry.classList.add('active-node');

    logEntry.innerHTML = `
        <span class="log-timestamp">${getTimestamp()}</span>
        <span class="log-module">[${module.toUpperCase()}]</span>
        <span class="log-message">${message}</span>
    `;

    // Remove the "active" highlight from previous logs
    document.querySelectorAll('.active-node').forEach(el => el.classList.remove('active-node'));

    consoleDiv.appendChild(logEntry);

    // Use a smoother scroll behavior
    logEntry.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Add these variables at the top of script.js
const scrollBtn = document.getElementById('scroll-btn');
let isAutoScrollEnabled = true;

// Detection logic: Is the user looking at history?
consoleDiv.addEventListener('scroll', () => {
    const distanceFromBottom = consoleDiv.scrollHeight - consoleDiv.scrollTop - consoleDiv.clientHeight;

    // If user is more than 100px from bottom, disable auto-scroll and show button
    if (distanceFromBottom > 100) {
        isAutoScrollEnabled = false;
        scrollBtn.classList.add('visible');
    } else {
        isAutoScrollEnabled = true;
        scrollBtn.classList.remove('visible', 'pulse');
    }
});

// Click to Jump to Bottom
scrollBtn.addEventListener('click', () => {
    consoleDiv.scrollTo({ top: consoleDiv.scrollHeight, behavior: 'smooth' });
});

function appendLog(module, message, type = 'info') {
    // ... existing entry creation code ...

    consoleDiv.appendChild(logEntry);

    if (isAutoScrollEnabled) {
        consoleDiv.scrollTop = consoleDiv.scrollHeight;
    } else {
        // Pulse the button to signal new data is arriving below
        scrollBtn.classList.add('pulse');
    }
}