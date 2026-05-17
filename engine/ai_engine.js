/**
 * GemmaForge AI Engine (Frontend Implementation)
 * Replaces the Python backend for Hackathon deployments (Ease Wins).
 */

const getApiKey = () => {
    const key = localStorage.getItem('GEMINI_API_KEY');
    if (!key) {
        throw new Error("GEMINI_API_KEY is not set. Please open Settings and enter your key.");
    }
    return key;
};

/**
 * Base generic wrapper for calling the Gemini API.
 */
async function callGemini(modelName, prompt, generationConfig, systemInstruction = null, prefilledModelResponse = null) {
    const apiKey = getApiKey();
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${modelName}:generateContent?key=${apiKey}`;

    const payload = {
        contents: [
            { role: "user", parts: [{ text: prompt }] }
        ],
        generationConfig: generationConfig
    };

    if (systemInstruction) {
        payload.systemInstruction = { parts: [{ text: systemInstruction }] };
    }

    if (prefilledModelResponse) {
        payload.contents.push({ role: "model", parts: [{ text: prefilledModelResponse }] });
    }

    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });

    if (!response.ok) {
        const errText = await response.text();
        throw new Error(`API Error (${response.status}): ${errText}`);
    }

    const data = await response.json();
    return data.candidates[0].content.parts[0].text;
}

window.aiEngine = (function() {
    const getApiKey = () => {
        const key = localStorage.getItem('GEMINI_API_KEY');
        if (!key) {
            throw new Error("GEMINI_API_KEY is not set. Please open Settings (⚙️) and enter your key.");
        }
        return key;
    };

    // HARDCODED MODEL LIST: Verified Gemma 4 family lineup.
    const HARDCODED_MODELS = [
        "gemma-4-e2b-it",
        "gemma-4-26b-a4b-it",
        "gemma-4-31b-it"
    ];

    /**
     * Dynamically finds the best available Gemma 4 model based on size keywords.
     */
    async function getTargetModel(sizeKeyword) {
        if (sizeKeyword === '2b') return "gemma-4-e2b-it";
        if (sizeKeyword === '4b') return "gemma-4-26b-a4b-it";
        if (sizeKeyword === '26b') return "gemma-4-26b-a4b-it";
        if (sizeKeyword === '31b' || sizeKeyword === '32b') return "gemma-4-31b-it";
        return "gemma-4-e2b-it"; 
    }

    async function callGemini(modelName, prompt, generationConfig, systemInstruction = null, prefilledModelResponse = null, timeoutMs = 60000) {
        const apiKey = getApiKey();
        const url = `https://generativelanguage.googleapis.com/v1beta/models/${modelName}:generateContent?key=${apiKey}`;

        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);

        const payload = {
            contents: [
                { role: "user", parts: [{ text: prompt }] }
            ],
            generationConfig: generationConfig
        };

        if (systemInstruction) {
            payload.systemInstruction = { parts: [{ text: systemInstruction }] };
        }

        if (prefilledModelResponse) {
            payload.contents.push({ role: "model", parts: [{ text: prefilledModelResponse }] });
        }

        try {
            const response = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
                signal: controller.signal
            });

            clearTimeout(timer);

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`API Error (${response.status}): ${errText}`);
            }

            const data = await response.json();
            return data.candidates[0].content.parts[0].text;
        } catch (err) {
            clearTimeout(timer);
            if (err.name === 'AbortError') {
                throw new Error(`TIMEOUT: ${modelName} took longer than ${timeoutMs/1000}s.`);
            }
            throw err;
        }
    }

    // Fallback helper
    const logFallback = (msg) => {
        if (window.showToast) window.showToast(msg, 'warning');
        console.warn(msg);
    };

    return {
        compressCompetitorFluff: async function(rawText) {
            try {
                const model = await getTargetModel('2b');
                const prompt = `Perform aggressive signal extraction on the provided text.\nDiscard all marketing copy, introductions, self-promotional filler, and 'thought' transitions.\nRetain only hard technical data: version numbers, library names, code logic, and architectural constraints.\n\nINPUT TEXT:\n${rawText.substring(0, 12000)}\n\nOUTPUT: A high-density technical summary.`;
                return await callGemini(model, prompt, { temperature: 0.2, maxOutputTokens: 2048 }, null, null, 30000);
            } catch (e) {
                throw e; // Smallest model, nowhere to fall back.
            }
        },

        analyseTrends: async function(rawTrendsJson) {
            try {
                const model = await getTargetModel('4b');
                const prompt = `You are an Expert Analyst. Analyze the following trending data.\nIdentify exactly 5 distinct, highly actionable patterns or shifts.\n\nFor each of the 5 signals, provide:\n1. Signal Name\n2. Context\n3. Strategic Implication\n\nRaw Trend Data:\n${rawTrendsJson}\n\nOutput format: Raw Markdown only. Use bolding for names. NO INTRO. NO OUTRO.`;
                return await callGemini(model, prompt, { temperature: 0.6, maxOutputTokens: 4096 }, null, null, 45000);
            } catch (e) {
                logFallback(`4B failed/timed out. Falling back to 2B.`);
                const model = await getTargetModel('2b');
                return await this.compressCompetitorFluff(rawTrendsJson); // Re-use logic for 2b
            }
        },

        generateSeoGapReport: async function(myText, competitorContext) {
            const tiers = ['26b', '4b', '2b'];
            for (const tier of tiers) {
                try {
                    const model = await getTargetModel(tier);
                    const prompt = `You are a Content Architect.\nExecute a differential analysis (Semantic Gap Analysis).\n\n[MY CURRENT CONTENT DRAFT]:\n${myText}\n\n[COMPETITOR CONTEXT]:\n${competitorContext}\n\nTASK:\nIdentify the "Semantic Delta" — the precise sub-topics, details, and context present in the Competitor Context that are MISSING from My Current Content.\n\nOUTPUT:\nA prioritized list of 3-5 deficits. Be specific.\nFormat: Raw Markdown only.`;
                    return await callGemini(model, prompt, { temperature: 0.5, maxOutputTokens: 4096 }, null, null, tier === '26b' ? 60000 : 30000);
                } catch (e) {
                    if (tier === '2b') throw e;
                    logFallback(`${tier} failed. Trying ${tiers[tiers.indexOf(tier)+1]}...`);
                }
            }
        },

        planTheContent: async function(gapReport, trendsSummary, humanStyle) {
            const tiers = ['26b', '4b', '2b'];
            for (const tier of tiers) {
                try {
                    const model = await getTargetModel(tier);
                    const prompt = `You are an Expert Content Architect synthesizing research into a rigid content blueprint.\n\n[INPUT 1: SEO Gap Report]\n${gapReport}\n\n[INPUT 2: Forward-Looking Trends]\n${trendsSummary}\n\n[INPUT 3: Target Style / Tone]\n${humanStyle}\n\nTASK: Synthesize these inputs into a comprehensive, section-by-section Content Blueprint.\n\nREQUIREMENTS:\n- Integrate the missing components from the Gap Report.\n- Weave the advanced signals from the Trends Summary.\n- Follow the Target Style implicitly.\n\nOUTPUT MUST BE A BULLETED PLAN ONLY. Do not write the article itself.`;
                    return await callGemini(model, prompt, { temperature: 0.7, maxOutputTokens: 4096 }, null, null, tier === '26b' ? 60000 : 30000);
                } catch (e) {
                    if (tier === '2b') throw e;
                    logFallback(`${tier} failed. Trying ${tiers[tiers.indexOf(tier)+1]}...`);
                }
            }
        },

        writeTheContent: async function(contentPlan, outputFormat = "html") {
            const tiers = ['31b', '26b', '4b'];
            for (const tier of tiers) {
                try {
                    const model = await getTargetModel(tier);
                    const isMd = outputFormat.toLowerCase() === "md" || outputFormat.toLowerCase() === "markdown";
                    
                    // Dynamic Anchoring based on context
                    const strongAnchor = isMd ? "# " : "<h1>";

                    const systemInstruction = "You are a professional Content Creator and Writer. Your only output is final, published article prose. You never reproduce plans, outlines, instructions, role definitions, or meta-commentary. You never use headers like 'PART 1', 'META-PROMPT', 'BLUEPRINT', or 'ROLE:'.";
                    
                    const dataPrompt = `The following block is your source data. Study it, then write the article.

[SOURCE DATA — DO NOT REPRODUCE]
${contentPlan}
[END SOURCE DATA]

Using only the facts above, write a complete, high-quality article.

Rules:
- Write engaging prose tailored to the audience.
- Use ## / ### headers and bullet lists for requirements.
- Do NOT copy, paraphrase, or reference these instructions.
- Start the article immediately.`;

                    let continuation = await callGemini(model, dataPrompt, { temperature: 0.85, maxOutputTokens: 8192, topP: 0.95 }, systemInstruction, strongAnchor, tier === '31b' ? 120000 : 60000);
                    let result = strongAnchor + continuation;
                    
                    if (result.includes("OBJECTIVE:") || result.includes("META-PROMPT")) {
                        throw new Error("Echo detected in output.");
                    }

                    return result;
                } catch (e) {
                    if (tier === '4b') throw e;
                    logFallback(`${tier} failed (timeout or echo). Falling back to ${tiers[tiers.indexOf(tier)+1]}...`);
                }
            }
        }
    };
})();
