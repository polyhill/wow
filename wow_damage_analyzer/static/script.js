// Wait for the DOM to be fully loaded before executing the script.
document.addEventListener('DOMContentLoaded', async () => {
    // Register the Chart.js datalabels plugin to display labels on charts.
    Chart.register(ChartDataLabels);

    // --- DOM Element Selection ---
    // Select all necessary DOM elements for manipulation.
    const langToggleBtn = document.getElementById('lang-toggle');
    const wclUrlInput = document.getElementById('wcl-url');
    const analyzeBtn = document.getElementById('analyze-btn');
    const fightSelect = document.getElementById('fight-select');
    const playerSelect = document.getElementById('player-select');
    const wclHistorySelect = document.getElementById('wcl-history-select');
    const damageTableBody = document.querySelector('#damage-table tbody');
    const modal = document.getElementById('details-modal');
    const closeBtn = document.querySelector('.close-btn');
    const apChartContainer = document.getElementById('ap-chart-container');
    const skillChartContainer = document.getElementById('skill-chart-container');
    const critHitChartContainer = document.getElementById('crit-hit-chart-container');
    const dpsStackChartContainer = document.getElementById('dps-stack-chart-container');
    const detailsTableHead = document.querySelector('#details-table thead');
    const detailsTableBody = document.querySelector('#details-table tbody');

    // --- State Variables ---
    // Initialize variables to hold chart instances, report data, and application state.
    let apDpsChart = null;
    let skillDpsChart = null;
    let critHitDpsChart = null;
    let dpsStackChart = null;
    let reportID = null;
    let currentLang = localStorage.getItem('lang') || 'en'; // Default to English if no language is saved.
    let lastAnalysisResult = null; // Store the last analysis result to re-render on language change.

    // --- Internationalization (i18n) ---
    // Object to hold translation strings for English and Chinese.
    const i18n = {
        'en': {},
        'zh': {}
    };

    /**
     * Translates an ability name using the loaded i18n data.
     * @param {string} abilityName - The ability name to translate.
     * @param {string} lang - The target language ('en' or 'zh').
     * @returns {string} The translated ability name or the original name if no translation is found.
     */
    function translateAbilityName(abilityName, lang) {
        const key = `ability_${abilityName.replace(/\s/g, '_').replace(/[()]/g, '')}`;
        return i18n[lang][key] || abilityName;
    }

    /**
     * Asynchronously loads translation files (en.json, zh.json) from the server.
     */
    async function loadTranslations() {
        try {
            const [en, zh] = await Promise.all([
                fetch('/static/locales/en.json').then(res => res.json()),
                fetch('/static/locales/zh.json').then(res => res.json())
            ]);
            i18n.en = en;
            i18n.zh = zh;
            setLanguage(currentLang); // Apply the current language once translations are loaded.
        } catch (error) {
            console.error("Could not load translation files:", error);
        }
    }

    /**
     * Sets the application language and updates all UI elements with the appropriate translations.
     * @param {string} lang - The language to set ('en' or 'zh').
     */
    function setLanguage(lang) {
        currentLang = lang;
        localStorage.setItem('lang', lang); // Save the selected language to local storage.
        const translations = i18n[lang];

        // Update all elements with a 'data-i18n' attribute.
        document.querySelectorAll('[data-i18n]').forEach(elem => {
            const key = elem.getAttribute('data-i18n');
            if (translations[key]) {
                elem.textContent = translations[key];
            }
        });

        // Update placeholders for input elements.
        document.querySelectorAll('[data-i18n-placeholder]').forEach(elem => {
            const key = elem.getAttribute('data-i18n-placeholder');
            if (translations[key]) {
                elem.placeholder = translations[key];
            }
        });

        // Update default options in select elements.
        document.querySelectorAll('select').forEach(select => {
            const firstOption = select.querySelector('option[value=""]');
            if (firstOption) {
                const key = firstOption.getAttribute('data-i18n');
                if (key && translations[key]) {
                    firstOption.textContent = translations[key];
                }
            }
        });

        // If an analysis has already been performed, re-render the data with the new language.
        if (lastAnalysisResult) {
            updateDamageTable(lastAnalysisResult.damage_breakdown);
            renderDpsChart(lastAnalysisResult.dps_curves);
            if (lastAnalysisResult.dps_stack_data) {
                renderDpsStackChart(lastAnalysisResult.dps_stack_data);
            }
        }
    }

    // --- Event Listeners ---

    // Toggles the language between English and Chinese.
    langToggleBtn.addEventListener('click', () => {
        const newLang = currentLang === 'en' ? 'zh' : 'en';
        setLanguage(newLang);
    });

    // --- Modal Event Listeners ---
    // Open the details modal when a chart is clicked.
    apChartContainer.addEventListener('click', () => {
        if (lastAnalysisResult && lastAnalysisResult.dps_gain_details) {
            updateDetailsTable(lastAnalysisResult.dps_gain_details, 'attack_power');
            modal.style.display = 'block';
        }
    });

    skillChartContainer.addEventListener('click', () => {
        if (lastAnalysisResult && lastAnalysisResult.dps_gain_details) {
            updateDetailsTable(lastAnalysisResult.dps_gain_details, 'weapon_skill');
            modal.style.display = 'block';
        }
    });

    critHitChartContainer.addEventListener('click', () => {
        if (lastAnalysisResult && lastAnalysisResult.dps_gain_details) {
            updateDetailsTable(lastAnalysisResult.dps_gain_details, 'crit_hit');
            modal.style.display = 'block';
        }
    });

    dpsStackChartContainer.addEventListener('click', () => {
        if (lastAnalysisResult && lastAnalysisResult.dps_stack_data) {
            updateDetailsTable(lastAnalysisResult.dps_stack_data, 'dps_stack');
            modal.style.display = 'block';
        }
    });

    // Close the modal when the close button is clicked.
    closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
    });

    // Close the modal when clicking outside of the modal content.
    window.addEventListener('click', (event) => {
        if (event.target == modal) {
            modal.style.display = 'none';
        }
    });

    // --- Initialization ---
    // Load all necessary data and restore state when the page loads.
    await loadTranslations();
    loadWclHistory();
    restoreCurrentStatus();
    restoreAttributeChanges();
    await restoreLastUrl();

    /**
     * Formats a duration in milliseconds to a M:SS.ms string.
     * @param {number} ms - The duration in milliseconds.
     * @returns {string} The formatted duration string.
     */
    function formatDuration(ms) {
        if (typeof ms !== 'number' || ms < 0) {
            return '0:00.000';
        }
        const totalSeconds = Math.floor(ms / 1000);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        const milliseconds = ms % 1000;

        const paddedSeconds = String(seconds).padStart(2, '0');
        const paddedMilliseconds = String(milliseconds).padStart(3, '0');

        if (minutes > 0) {
            return `${minutes}:${paddedSeconds}.${paddedMilliseconds}`;
        }
        return `${seconds}.${paddedMilliseconds}`;
    }

    /**
     * Restores the last used WCL URL from local storage and triggers data fetching.
     */
    async function restoreLastUrl() {
        const lastUrl = localStorage.getItem('lastWclUrl');
        if (lastUrl) {
            wclUrlInput.value = lastUrl;
            await handleWclUrlChange();
            
            // Sync the history dropdown with the restored URL.
            const historySelect = document.getElementById('wcl-history-select');
            const option = Array.from(historySelect.options).find(opt => opt.value === lastUrl);
            if (option) {
                historySelect.value = lastUrl;
            }
        }
    }

    // Handles changes to the WCL history dropdown.
    wclHistorySelect.addEventListener('change', () => {
        const selectedUrl = wclHistorySelect.value;
        if (selectedUrl) {
            wclUrlInput.value = selectedUrl;
            handleWclUrlChange();
            analyzeBtn.disabled = true;
            document.getElementById('last-analyzed-time').textContent = '';
        }
    });

    /**
     * Fetches fight and player data when the WCL URL input changes.
     */
    async function handleWclUrlChange() {
        const url = wclUrlInput.value.trim();
        if (!url) return;

        analyzeBtn.disabled = true;
        document.getElementById('last-analyzed-time').textContent = '';
        wclUrlInput.classList.add('highlight-animation');
        wclUrlInput.addEventListener('animationend', () => {
            wclUrlInput.classList.remove('highlight-animation');
        }, { once: true });

        // Extract the report ID from the URL.
        const match = url.match(/reports\/(.+)/);
        reportID = match ? match[1] : null;

        if (!reportID) {
            alert('Invalid WCL Report URL');
            return;
        }
        
        localStorage.setItem('lastWclUrl', url);
        await saveWclHistory(url);

        // Fetch fights and players for the given report ID.
        try {
            const [fights, players] = await Promise.all([
                fetch(`/api/fights/${reportID}`).then(res => res.json()),
                fetch(`/api/players/${reportID}`).then(res => res.json())
            ]);
            populateSelect(fightSelect, fights, 'select_fight_option', false);
            populateSelect(playerSelect, players, 'select_player_option', false);
            restoreLastSelection(reportID);
            updateFightListNames();
            analyzeBtn.disabled = false;
        } catch (error) {
            console.error('Error fetching report data:', error);
            alert('Failed to fetch data for the report.');
        }
    }

    wclUrlInput.addEventListener('change', handleWclUrlChange);

    /**
     * Performs the main analysis by sending data to the backend API.
     */
    async function performAnalysis() {
        analyzeBtn.disabled = true;
        analyzeBtn.classList.add('loading');
        document.getElementById('last-analyzed-time').textContent = '';

        const selectedFight = fightSelect.value;
        const selectedPlayer = playerSelect.value;

        saveLastSelection(reportID, selectedFight, selectedPlayer);
        saveCurrentStatus();
        saveAttributeChanges();

        // Construct the payload with all necessary data for analysis.
        const payload = {
            report_id: reportID,
            fight_id: selectedFight,
            player_id: selectedPlayer,
            attributes: getAttributeValues(),
            current_status: getCurrentStatus()
        };

        try {
            // Make parallel API calls for the main analysis and the DPS stack simulation.
            const [analyzeResponse, stackResponse] = await Promise.all([
                fetch('/api/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                }),
                fetch('/api/dps_simulation_stack', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                })
            ]);

            const result = await analyzeResponse.json();
            const stackData = await stackResponse.json();
            
            // Store the combined results.
            lastAnalysisResult = result;
            lastAnalysisResult.dps_stack_data = stackData;

            // Update the UI with the new data.
            updateDamageTable(result.damage_breakdown);
            renderDpsChart(result.dps_curves);
            renderDpsStackChart(stackData);
            updateDetailsTable(result.dps_gain_details);
            document.getElementById('last-analyzed-time').textContent = new Date().toLocaleString();
        } catch (error) {
            console.error('Error during analysis:', error);
            alert('An error occurred during analysis.');
        } finally {
            analyzeBtn.disabled = false;
            analyzeBtn.classList.remove('loading');
        }
    }

    // Triggers the analysis when the analyze button is clicked.
    analyzeBtn.addEventListener('click', () => {
        if (!reportID || !fightSelect.value || !playerSelect.value) {
            alert('Please select a report, fight, and player.');
            return;
        }
        performAnalysis();
    });

    // Updates the fight list and fetches weapon data when the player selection changes.
    playerSelect.addEventListener('change', () => {
        updateFightListNames();
        fetchWeapons();
    });

    /**
     * Fetches the selected player's weapon information from the backend.
     */
    async function fetchWeapons() {
        const selectedPlayer = playerSelect.value;
        if (!reportID || !selectedPlayer) return;

        try {
            const response = await fetch(`/api/weapons/${reportID}/${selectedPlayer}`);
            const weapons = await response.json();
            document.getElementById('mh-name').textContent = `${weapons.main_hand_name || 'Unknown'}`;
            document.getElementById('oh-name').textContent = `${weapons.off_hand_name || 'Unknown'}`;
        } catch (error) {
            console.error('Error fetching weapon data:', error);
        }
    }

    // --- Local Storage Management ---

    /**
     * Saves the last selected fight and player for a given report ID.
     */
    function saveLastSelection(reportId, fightId, playerId) {
        let selections = JSON.parse(localStorage.getItem('lastSelections')) || {};
        selections[reportId] = { fight: fightId, player: playerId };
        localStorage.setItem('lastSelections', JSON.stringify(selections));
    }

    /**
     * Restores the last selected fight and player for the current report ID.
     */
    function restoreLastSelection(reportId) {
        let selections = JSON.parse(localStorage.getItem('lastSelections')) || {};
        const lastSelection = selections[reportId];
        if (lastSelection) {
            if (fightSelect.querySelector(`option[value="${lastSelection.fight}"]`)) {
                fightSelect.value = lastSelection.fight;
            }
            if (playerSelect.querySelector(`option[value="${lastSelection.player}"]`)) {
                playerSelect.value = lastSelection.player;
            }
        }
    }

    /**
     * Saves the current player status (skills, speeds, stats) to local storage.
     */
    function saveCurrentStatus() {
        const status = {
            mh_skill: document.getElementById('mh-skill').value,
            oh_skill: document.getElementById('oh-skill').value,
            mh_speed: document.getElementById('mh-speed').value,
            oh_speed: document.getElementById('oh-speed').value,
            current_hit: document.getElementById('current-hit').value,
            current_crit: document.getElementById('current-crit').value
        };
        localStorage.setItem('currentStatus', JSON.stringify(status));
    }

    /**
     * Restores the player status from local storage.
     */
    function restoreCurrentStatus() {
        const status = JSON.parse(localStorage.getItem('currentStatus'));
        if (status) {
            document.getElementById('mh-skill').value = status.mh_skill;
            document.getElementById('oh-skill').value = status.oh_skill;
            document.getElementById('mh-speed').value = status.mh_speed;
            document.getElementById('oh-speed').value = status.oh_speed;
            document.getElementById('current-hit').value = status.current_hit;
            document.getElementById('current-crit').value = status.current_crit;
        }
    }

    /**
     * Saves the attribute change values from the input fields to local storage.
     */
    function saveAttributeChanges() {
        const attributes = getAttributeValues();
        localStorage.setItem('attributeChanges', JSON.stringify(attributes));
    }

    /**
     * Restores the attribute change values from local storage.
     */
    function restoreAttributeChanges() {
        const attributes = JSON.parse(localStorage.getItem('attributeChanges'));
        if (attributes) {
            document.getElementById('strength').value = attributes.strength;
            document.getElementById('agility').value = attributes.agility;
            document.getElementById('attack-power').value = attributes.attackPower;
            document.getElementById('crit').value = attributes.crit;
            document.getElementById('hit').value = attributes.hit;
            document.getElementById('haste').value = attributes.haste;
            document.getElementById('mh-skill-change').value = attributes.mainHandSkill;
            document.getElementById('oh-skill-change').value = attributes.offHandSkill;
        }
    }

    /**
     * Populates a select dropdown with a list of items.
     * @param {HTMLSelectElement} selectElement - The select element to populate.
     * @param {Array} items - An array of objects with 'id' and 'name' properties.
     * @param {string} defaultOptionKey - The i18n key for the default option text.
     * @param {boolean} selectLast - Whether to select the last item by default.
     */
    function populateSelect(selectElement, items, defaultOptionKey, selectLast = false) {
        const defaultOptionText = (i18n[currentLang] && i18n[currentLang][defaultOptionKey]) || defaultOptionKey.replace(/_/g, ' ');
        selectElement.innerHTML = `<option value="">${defaultOptionText}</option>`;
        items.forEach(item => {
            const option = document.createElement('option');
            option.value = item.id;
            
            if (selectElement.id === 'fight-select') {
                const durationText = formatDuration(item.duration);
                const newName = `${item.name} (${durationText})`;
                option.textContent = newName;
                option.dataset.originalName = newName;
            } else {
                option.textContent = item.name;
            }

            selectElement.appendChild(option);
        });

        if (selectLast && items.length > 0) {
            selectElement.value = items[items.length - 1].id;
        }
    }

    /**
     * Updates the fight list names to include the selected player's name for context.
     */
    function updateFightListNames() {
        const selectedPlayerOption = playerSelect.options[playerSelect.selectedIndex];
        const playerName = selectedPlayerOption.value ? selectedPlayerOption.textContent : null;

        const fightOptions = fightSelect.querySelectorAll('option');
        fightOptions.forEach(option => {
            if (option.value) {
                const originalName = option.dataset.originalName;
                if (playerName) {
                    option.textContent = `${playerName} - ${originalName}`;
                } else {
                    option.textContent = originalName;
                }
            }
        });
    }

    /**
     * Loads the WCL report history from local storage and populates the history dropdown.
     */
    function loadWclHistory() {
        let history = JSON.parse(localStorage.getItem('wclHistory')) || [];
        const historySelect = document.getElementById('wcl-history-select');
        historySelect.innerHTML = '';
        const defaultOption = document.createElement('option');
        defaultOption.value = "";
        defaultOption.textContent = "Select from history";
        defaultOption.setAttribute('data-i18n', 'select_history_option');
        historySelect.appendChild(defaultOption);

        // Filter out any potentially invalid or old history entries.
        history = history.filter(item => item.text && !item.text.includes('undefined') && !item.text.includes('None'));
        
        history.forEach(item => {
            const option = document.createElement('option');
            option.value = item.url;
            option.textContent = item.text;
            historySelect.appendChild(option);
        });
    }

    /**
     * Saves a new WCL report URL to the history in local storage.
     * @param {string} url - The WCL report URL to save.
     */
    async function saveWclHistory(url) {
        let history = JSON.parse(localStorage.getItem('wclHistory')) || [];
        // Only add the URL if it's not already in the history.
        if (!history.find(item => item.url === url)) {
            const reportID = url.match(/reports\/(.+)/)?.[1];
            if (reportID) {
                try {
                    // Fetch report metadata to create a descriptive history entry.
                    const response = await fetch(`/api/report/${reportID}`);
                    if (!response.ok) throw new Error('Failed to fetch report metadata');
                    const metadata = await response.json();
                    if (!metadata.error) {
                        const displayText = `${metadata.title} - ${metadata.startTime}`;
                        history.unshift({ url: url, text: displayText });
                        history = history.slice(0, 10); // Keep the history limited to 10 entries.
                        localStorage.setItem('wclHistory', JSON.stringify(history));
                        loadWclHistory();
                        // After reloading, set the dropdown to the newly added URL
                        const historySelect = document.getElementById('wcl-history-select');
                        historySelect.value = url;
                    }
                } catch (error) {
                    console.error('Failed to fetch report metadata:', error);
                    // Fallback to a simpler display text if metadata fetch fails.
                    const fallbackText = `Report ID: ${reportID}`;
                    history.unshift({ url: url, text: fallbackText });
                    history = history.slice(0, 10);
                    localStorage.setItem('wclHistory', JSON.stringify(history));
                    loadWclHistory();
                    // After reloading, set the dropdown to the newly added URL
                    const historySelect = document.getElementById('wcl-history-select');
                    historySelect.value = url;
                }
            }
        }
    }

    /**
     * Gathers all attribute change values from the input fields.
     * @returns {object} An object containing all attribute values.
     */
    function getAttributeValues() {
        return {
            strength: parseInt(document.getElementById('strength').value) || 0,
            agility: parseInt(document.getElementById('agility').value) || 0,
            attackPower: parseInt(document.getElementById('attack-power').value) || 0,
            crit: parseFloat(document.getElementById('crit').value) || 0,
            hit: parseFloat(document.getElementById('hit').value) || 0,
            haste: parseFloat(document.getElementById('haste').value) || 0,
            mainHandSkill: parseInt(document.getElementById('mh-skill-change').value) || 0,
            offHandSkill: parseInt(document.getElementById('oh-skill-change').value) || 0
        };
    }

    /**
     * Gathers the current player status values from the input fields.
     * @returns {object} An object containing the current player status.
     */
    function getCurrentStatus() {
        return {
            mh_skill: parseInt(document.getElementById('mh-skill').value) || 300,
            oh_skill: parseInt(document.getElementById('oh-skill').value) || 300,
            hit: parseFloat(document.getElementById('current-hit').value) || 0,
            crit: parseFloat(document.getElementById('current-crit').value) || 0,
            main_hand_speed: parseFloat(document.getElementById('mh-speed').value) || 0,
            off_hand_speed: parseFloat(document.getElementById('oh-speed').value) || 0
        };
    }

    /**
     * Formats a damage number into a more readable string (e.g., 1.2M, 5.3k).
     * @param {number|string} damage - The damage number to format.
     * @returns {string} The formatted damage string.
     */
    function formatDamage(damage) {
        const numDamage = parseFloat(damage) || 0;
        if (currentLang === 'zh') {
            if (numDamage >= 1000000) return `${(numDamage / 1000000).toFixed(1)}百万`;
            if (numDamage >= 1000) return `${(numDamage / 1000).toFixed(1)}千`;
            return numDamage.toFixed(0);
        }
        
        if (numDamage >= 1000000) return `${(numDamage / 1000000).toFixed(1)}M`;
        if (numDamage >= 1000) return `${(numDamage / 1000).toFixed(1)}k`;
        return numDamage.toFixed(0);
    }

    /**
     * Updates the main damage table with new data from an analysis.
     * @param {Array} data - The damage breakdown data.
     */
    function updateDamageTable(data) {
        damageTableBody.innerHTML = '';
        if (!data || data.length === 0) return;

        const maxDamage = Math.max(...data.slice(0, -1).map(row => row.total_damage));

        data.forEach(row => {
            const tr = document.createElement('tr');
            const isTotalRow = row.ability === 'Total';
            if (isTotalRow) {
                tr.classList.add('total-row');
            }

            const damageCellHtml = `
                <td class="col-damage damage-bar-cell">
                    <div class="damage-bar" style="width: ${isTotalRow ? 0 : (row.total_damage / maxDamage) * 100}%;"></div>
                    <div class="damage-text">${formatDamage(row.total_damage)}</div>
                </td>
            `;

            tr.innerHTML = `
                <td class="col-ability">${translateAbilityName(row.ability, currentLang)}</td>
                ${damageCellHtml}
                <td class="col-percent">${(parseFloat(row.damage_percent) || 0).toFixed(2)}%</td>
                <td class="col-casts">${row.casts || 0}</td>
                <td class="col-hits">${row.hits || 0}</td>
                <td class="col-crits">${row.crits || 0}</td>
                <td class="col-crit-rate">${(parseFloat(row.crit_rate) || 0).toFixed(2)}%</td>
                <td class="col-misses">${row.misses || 0}</td>
                <td class="col-dodge">${row.dodges || 0}</td>
                <td class="col-parry">${row.parries || 0}</td>
                <td class="col-miss-rate">${(parseFloat(row.miss_rate) || 0).toFixed(2)}%</td>
                <td class="col-dps">${(parseFloat(row.dps) || 0).toFixed(2)}</td>
            `;
            damageTableBody.appendChild(tr);
        });
    }

    /**
     * Renders the three main DPS gain charts (AP, Skill, Crit/Hit).
     * @param {object} data - The DPS curves data from the analysis.
     */
    function renderDpsChart(data) {
        const apCtx = document.getElementById('ap-dps-chart').getContext('2d');
        const skillCtx = document.getElementById('skill-dps-chart').getContext('2d');
        const critHitCtx = document.getElementById('crit-hit-dps-chart').getContext('2d');
        if (apDpsChart) apDpsChart.destroy();
        if (skillDpsChart) skillDpsChart.destroy();
        if (critHitDpsChart) critHitDpsChart.destroy();

        const apData = data.attack_power || [];
        const skillData = data.weapon_skill || {};
        const hitCritData = data.hit_crit || [];
        const critData = hitCritData.map(p => ({x: p.hit, y: p.crit_dps}));
        const hitData = hitCritData.map(p => ({x: p.hit, y: p.dps}));
        const translations = i18n[currentLang];

        // Calculate DPS gain per point for chart labels.
        let dpsGainPerAp = 0;
        if (apData.length > 1 && apData[1].x > 0) {
            dpsGainPerAp = (parseFloat(apData[1].y) || 0) / apData[1].x;
        }
        const apLabelTemplate = translations['chart_ap_dps_gain_label'] || "Attack Power (+{value} DPS)";
        const apLabel = apLabelTemplate.replace('{value}', dpsGainPerAp.toFixed(2));

        let dpsGainPerMhSkill = 0;
        if (skillData.mh && skillData.mh.length > 1 && skillData.mh[1].y) {
            dpsGainPerMhSkill = parseFloat(skillData.mh[1].y) || 0;
        }
        let dpsGainPerOhSkill = 0;
        if (skillData.oh && skillData.oh.length > 1 && skillData.oh[1].y) {
            dpsGainPerOhSkill = parseFloat(skillData.oh[1].y) || 0;
        }
        let dpsGainPerTotalSkill = 0;
        if (skillData.total && skillData.total.length > 1 && skillData.total[1].y) {
            dpsGainPerTotalSkill = parseFloat(skillData.total[1].y) || 0;
        }

        const mhSkillLabel = `${translations['chart_skill_dps_gain_label'] || "MH"} (+${dpsGainPerMhSkill.toFixed(2)} DPS)`;
        const ohSkillLabel = `${translations['chart_oh_skill_dps_gain_label'] || "OH"} (+${dpsGainPerOhSkill.toFixed(2)} DPS)`;
        const totalSkillLabel = `${translations['chart_total_skill_dps_gain_label'] || "Total"} (+${dpsGainPerTotalSkill.toFixed(2)} DPS)`;

        const critLabelTemplate = translations['chart_crit_dps_gain_label'] || "Crit";
        const hitLabelTemplate = translations['chart_hit_dps_gain_label'] || "Hit";

        let dpsGainPerCrit = 0;
        if (critData.length > 1 && critData[1].y) {
            dpsGainPerCrit = parseFloat(critData[1].y) || 0;
        }

        let dpsGainPerHit = 0;
        if (hitData.length > 1 && hitData[1].y) {
            dpsGainPerHit = parseFloat(hitData[1].y) || 0;
        }

        const critLabel = `${critLabelTemplate} (+${dpsGainPerCrit.toFixed(2)} DPS)`;
        const hitLabel = `${hitLabelTemplate} (+${dpsGainPerHit.toFixed(2)} DPS)`;

        // Common options for all three charts to maintain a consistent look.
        const commonOptions = {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    type: 'linear',
                    position: 'left',
                    title: {
                        display: false,
                        text: translations['chart_dps_gain_axis_label'] || 'DPS Gain',
                        color: '#f0f0f0'
                    },
                    ticks: { color: '#f0f0f0', stepSize: 10 },
                    grid: { color: '#444' },
                    min: 0,
                    max: 100
                }
            },
            plugins: {
                legend: {
                    display: true,
                    labels: { 
                        color: '#f0f0f0',
                        filter: (legendItem, chartData) => {
                            return legendItem.text !== '';
                        }
                    },
                    onClick: (e) => e.stopPropagation() // Prevent hiding datasets on legend click.
                },
                datalabels: { display: false }
            }
        };

        // --- Chart Creation ---

        // Attack Power DPS Gain Chart
        apDpsChart = new Chart(apCtx, {
            type: 'line',
            data: {
                datasets: [{
                    label: apLabel,
                    data: apData,
                    borderColor: '#ff8c00',
                    backgroundColor: 'rgba(255, 140, 0, 0.2)',
                    fill: true,
                    tension: 0.1
                }, {
                    type: 'line',
                    data: [{x: 0, y: 30}, {x: 200, y: 30}],
                    borderColor: 'rgba(255, 255, 255, 0.5)',
                    borderWidth: 2,
                    fill: false,
                    pointRadius: 0,
                    borderDash: [5, 5],
                    pointHoverRadius: 0,
                    pointHitRadius: 0,
                    label: ''
                }]
            },
            options: {
                ...commonOptions,
                scales: {
                    ...commonOptions.scales,
                    x: {
                        type: 'linear',
                        position: 'bottom',
                        title: {
                            display: true,
                            text: translations['chart_added_ap_axis_label'] || 'Added Attack Power',
                            color: '#f0f0f0'
                        },
                        min: 0,
                        ticks: { color: '#f0f0f0', stepSize: 20, max: 200 },
                        grid: { color: '#444' }
                    }
                },
                plugins: {
                    ...commonOptions.plugins,
                    tooltip: {
                        callbacks: {
                            title: (context) => `+${context[0].raw.x} AP`,
                            label: (context) => `DPS Gain: ${(parseFloat(context.raw.y) || 0).toFixed(2)}`
                        }
                    }
                }
            }
        });

        // Weapon Skill DPS Gain Chart
        skillDpsChart = new Chart(skillCtx, {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: mhSkillLabel,
                        data: skillData.mh || [],
                        borderColor: '#36a2eb',
                        backgroundColor: 'rgba(54, 162, 235, 0.2)',
                        fill: true,
                        tension: 0.1,
                        yAxisID: 'y'
                    },
                    {
                        label: ohSkillLabel,
                        data: skillData.oh || [],
                        borderColor: '#ff6384',
                        backgroundColor: 'rgba(255, 99, 132, 0.2)',
                        fill: true,
                        tension: 0.1,
                        yAxisID: 'y'
                    },
                    {
                        label: totalSkillLabel,
                        data: skillData.total || [],
                        borderColor: '#ffff00',
                        backgroundColor: 'rgba(255, 255, 0, 0.2)',
                        fill: true,
                        tension: 0.1,
                        yAxisID: 'y'
                    },
                    {
                        type: 'line',
                        data: [{x: 0, y: 30}, {x: 15, y: 30}],
                        borderColor: 'rgba(255, 255, 255, 0.5)',
                        borderWidth: 2,
                        fill: false,
                        pointRadius: 0,
                        borderDash: [5, 5],
                        yAxisID: 'y',
                        pointHoverRadius: 0,
                        pointHitRadius: 0,
                        label: ''
                    }
                ]
            },
            options: {
                ...commonOptions,
                scales: {
                    y: { ...commonOptions.scales.y, title: { display: false } },
                    x: {
                        type: 'linear',
                        position: 'bottom',
                        title: {
                            display: true,
                            text: translations['chart_added_skill_axis_label'] || 'Added Weapon Skill',
                            color: '#f0f0f0'
                        },
                        min: 0,
                        ticks: { color: '#f0f0f0', stepSize: 1, max: 15 },
                        grid: { color: '#444' }
                    }
                },
                plugins: {
                    ...commonOptions.plugins,
                    tooltip: {
                        callbacks: {
                            title: (context) => `+${context[0].raw.x} Skill`,
                            label: (context) => `DPS Gain: ${(parseFloat(context.raw.y) || 0).toFixed(2)}`
                        }
                    }
                }
            }
        });

        // Crit/Hit DPS Gain Chart
        critHitDpsChart = new Chart(critHitCtx, {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: critLabel,
                        data: critData,
                        borderColor: '#ff6384',
                        backgroundColor: 'rgba(255, 99, 132, 0.2)',
                        fill: true,
                        tension: 0.1,
                        yAxisID: 'y'
                    },
                    {
                        label: hitLabel,
                        data: hitData,
                        borderColor: '#4bc0c0',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        fill: true,
                        tension: 0.1,
                        yAxisID: 'y'
                    },
                    {
                        type: 'line',
                        data: [{x: 0, y: 30}, {x: 15, y: 30}],
                        borderColor: 'rgba(255, 255, 255, 0.5)',
                        borderWidth: 2,
                        fill: false,
                        pointRadius: 0,
                        borderDash: [5, 5],
                        yAxisID: 'y',
                        pointHoverRadius: 0,
                        pointHitRadius: 0,
                        label: ''
                    }
                ]
            },
            options: {
                ...commonOptions,
                scales: {
                    ...commonOptions.scales,
                    x: {
                        type: 'linear',
                        position: 'bottom',
                        title: {
                            display: true,
                            text: translations['chart_crit_hit_axis_label'] || 'Crit/Hit %',
                            color: '#f0f0f0'
                        },
                        min: 0,
                        ticks: { color: '#f0f0f0', stepSize: 1, max: 15 },
                        grid: { color: '#444' }
                    }
                },
                plugins: {
                    ...commonOptions.plugins,
                    tooltip: {
                        callbacks: {
                            title: (context) => `+${context[0].raw.x}%`,
                            label: (context) => `DPS Gain: ${(parseFloat(context.raw.y) || 0).toFixed(2)}`
                        }
                    }
                }
            }
        });
    }

    /**
     * Updates the details modal with the appropriate table based on the selected chart type.
     * @param {object} data - The full DPS gain details data.
     * @param {string} type - The type of details to display ('attack_power', 'weapon_skill', 'crit_hit', 'dps_stack').
     */
    function updateDetailsTable(data, type = 'attack_power') {
        detailsTableHead.innerHTML = '';
        detailsTableBody.innerHTML = '';
        const modalTitle = document.querySelector('#details-modal h2');

        if (type === 'crit_hit') {
            modalTitle.textContent = `${i18n[currentLang]['dps_gain_title'] || 'DPS Gain Details'} (${i18n[currentLang]['crit_hit_details_subtitle'] || 'Crit % / Hit %'})`;
            buildCritHitDetailsTable(data['crit'], data['hit']);
        } else if (type === 'weapon_skill') {
            modalTitle.textContent = `${i18n[currentLang]['dps_gain_title'] || 'DPS Gain Details'} (Weapon Skill)`;
            buildSkillDetailsTable(data['weapon_skill']['mh'], data['weapon_skill']['oh']);
        } else if (type === 'dps_stack') {
            modalTitle.textContent = i18n[currentLang]['dps_stack_details_title'] || 'DPS Simulation Stack Details';
            buildDpsStackDetailsTable(data);
        } else if (data[type]) {
            modalTitle.textContent = `${i18n[currentLang]['dps_gain_title'] || 'DPS Gain Details'} (Attack Power)`;
            buildDetailsTable(data[type]);
        }
    }

    /**
     * Builds the details table for Crit and Hit gains.
     * @param {Array} critData - The crit gain data.
     * @param {Array} hitData - The hit gain data.
     */
    function buildCritHitDetailsTable(critData, hitData) {
        if (!critData || critData.length === 0 || !hitData || hitData.length === 0) return;

        const critDataByAbility = Object.fromEntries(critData.map(row => [row.ability, row]));
        const hitDataByAbility = Object.fromEntries(hitData.map(row => [row.ability, row]));
        
        const allAbilities = [...new Set([...Object.keys(critDataByAbility), ...Object.keys(hitDataByAbility)])];

        // Sort abilities by 1% crit gain in descending order.
        allAbilities.sort((a, b) => {
            const critRowA = critDataByAbility[a] || {};
            const critRowB = critDataByAbility[b] || {};
            const gainA = parseFloat(critRowA['1%'] || 0);
            const gainB = parseFloat(critRowB['1%'] || 0);
            return gainB - gainA;
        });
        const headers = ['ability', ...Object.keys(critData[0] || {}).filter(k => k !== 'ability').sort((a, b) => parseInt(a) - parseInt(b))];

        const headerRow = document.createElement('tr');
        headers.forEach(headerText => {
            const th = document.createElement('th');
            th.textContent = headerText === 'ability' ? (i18n[currentLang]['ability_header'] || 'Ability') : headerText;
            headerRow.appendChild(th);
        });
        detailsTableHead.appendChild(headerRow);

        allAbilities.forEach(abilityName => {
            const tr = document.createElement('tr');
            const critRow = critDataByAbility[abilityName] || {};
            const hitRow = hitDataByAbility[abilityName] || {};

            headers.forEach(header => {
                const td = document.createElement('td');
                if (header === 'ability') {
                    td.textContent = translateAbilityName(abilityName, currentLang);
                } else {
                    const critGain = parseFloat(critRow[header] || 0).toFixed(1);
                    const hitGain = parseFloat(hitRow[header] || 0).toFixed(1);
                    td.textContent = `${critGain} / ${hitGain}`;
                }
                tr.appendChild(td);
            });
            detailsTableBody.appendChild(tr);
        });

        // Add a summary row at the bottom.
        const sumRow = document.createElement('tr');
        sumRow.classList.add('total-row');
        const sumData = { 'ability': 'Total' };
        headers.slice(1).forEach(header => {
            const critSum = critData.reduce((acc, row) => acc + (parseFloat(row[header]) || 0), 0);
            const hitSum = hitData.reduce((acc, row) => acc + (parseFloat(row[header]) || 0), 0);
            sumData[header] = `${critSum.toFixed(1)} / ${hitSum.toFixed(1)}`;
        });

        headers.forEach(header => {
            const td = document.createElement('td');
            td.textContent = header === 'ability' ? translateAbilityName(sumData[header], currentLang) : sumData[header];
            sumRow.appendChild(td);
        });
        detailsTableBody.appendChild(sumRow);
    }

    /**
     * Builds the details table for Main-Hand and Off-Hand weapon skill gains.
     * @param {Array} mhData - The main-hand skill gain data.
     * @param {Array} ohData - The off-hand skill gain data.
     */
    function buildSkillDetailsTable(mhData, ohData) {
        if (!mhData || mhData.length === 0 || !ohData || ohData.length === 0) return;

        const mhDataByAbility = Object.fromEntries(mhData.map(row => [row.ability, row]));
        const ohDataByAbility = Object.fromEntries(ohData.map(row => [row.ability, row]));
        
        const allAbilities = [...new Set([...Object.keys(mhDataByAbility), ...Object.keys(ohDataByAbility)])];

        // Sort abilities based on the combined DPS gain from +1 Main-Hand and Off-Hand skill, in descending order.
        // This provides a more comprehensive ranking of which abilities benefit most from weapon skill.
        allAbilities.sort((a, b) => {
            // Retrieve the data rows for ability A and B for both main-hand and off-hand.
            const mhRowA = mhDataByAbility[a] || {};
            const ohRowA = ohDataByAbility[a] || {};
            const mhRowB = mhDataByAbility[b] || {};
            const ohRowB = ohDataByAbility[b] || {};

            // Get the DPS gain from '+1 Skill' for ability A (main-hand and off-hand).
            const gainMA = parseFloat(mhRowA['+1 Skill'] || 0);
            const gainOA = parseFloat(ohRowA['+1 Skill'] || 0);

            // Get the DPS gain from '+1 Skill' for ability B (main-hand and off-hand).
            const gainMB = parseFloat(mhRowB['+1 Skill'] || 0);
            const gainOB = parseFloat(ohRowB['+1 Skill'] || 0);

            // Calculate the total gain for each ability and sort in descending order.
            return (gainMB + gainOB) - (gainMA + gainOA);
        });

        const headers = ['ability', ...Object.keys(mhData[0] || {}).filter(k => k !== 'ability').sort((a, b) => parseInt(a.replace('+','').replace(' Skill','')) - parseInt(b.replace('+','').replace(' Skill','')))];

        const headerRow = document.createElement('tr');
        headers.forEach(headerText => {
            const th = document.createElement('th');
            th.textContent = headerText === 'ability' ? (i18n[currentLang]['ability_header'] || 'Ability') : headerText.replace(' Skill', '');
            headerRow.appendChild(th);
        });
        detailsTableHead.appendChild(headerRow);

        allAbilities.forEach(abilityName => {
            const tr = document.createElement('tr');
            const mhRow = mhDataByAbility[abilityName] || {};
            const ohRow = ohDataByAbility[abilityName] || {};

            headers.forEach(header => {
                const td = document.createElement('td');
                if (header === 'ability') {
                    td.textContent = translateAbilityName(abilityName, currentLang);
                } else {
                    const mhGain = parseFloat(mhRow[header] || 0).toFixed(2);
                    const ohGain = parseFloat(ohRow[header] || 0).toFixed(2);
                    td.textContent = `${mhGain} / ${ohGain}`;
                }
                tr.appendChild(td);
            });
            detailsTableBody.appendChild(tr);
        });

        // Add a summary row at the bottom.
        const sumRow = document.createElement('tr');
        sumRow.classList.add('total-row');
        const sumData = { 'ability': 'Total' };
        headers.slice(1).forEach(header => {
            const mhSum = mhData.reduce((acc, row) => acc + (parseFloat(row[header]) || 0), 0);
            const ohSum = ohData.reduce((acc, row) => acc + (parseFloat(row[header]) || 0), 0);
            sumData[header] = `${mhSum.toFixed(2)} / ${ohSum.toFixed(2)}`;
        });

        headers.forEach(header => {
            const td = document.createElement('td');
            td.textContent = header === 'ability' ? translateAbilityName(sumData[header], currentLang) : sumData[header];
            sumRow.appendChild(td);
        });
        detailsTableBody.appendChild(sumRow);
    }

    /**
     * Builds a generic details table for a single attribute type (e.g., Attack Power).
     * @param {Array} tableData - The data for the table.
     */
    function buildDetailsTable(tableData) {
        if (!tableData || tableData.length === 0) return;
        const headers = ['ability', ...Object.keys(tableData[0]).filter(k => k !== 'ability').sort((a, b) => parseInt(a.replace(/\D/g, '')) - parseInt(b.replace(/\D/g, '')))];
        
        // Sort by the first gain column to show the most impacted abilities first.
        const firstGainColumn = headers[1];
        if (firstGainColumn) {
            tableData.sort((a, b) => {
                const gainA = parseFloat(a[firstGainColumn] || 0);
                const gainB = parseFloat(b[firstGainColumn] || 0);
                return gainB - gainA;
            });
        }

        const headerRow = document.createElement('tr');
        headers.forEach(headerText => {
            const th = document.createElement('th');
            th.textContent = headerText === 'ability' ? (i18n[currentLang]['ability_header'] || 'Ability') : headerText;
            headerRow.appendChild(th);
        });
        detailsTableHead.appendChild(headerRow);

        tableData.forEach(rowData => {
            const tr = document.createElement('tr');
            headers.forEach(header => {
                const td = document.createElement('td');
                if (header === 'ability') {
                    td.textContent = translateAbilityName(rowData[header], currentLang);
                } else {
                    td.textContent = (parseFloat(rowData[header]) || 0).toFixed(2);
                }
                tr.appendChild(td);
            });
            detailsTableBody.appendChild(tr);
        });

        // Add a summary row at the bottom.
        const sumRow = document.createElement('tr');
        sumRow.classList.add('total-row');
        const sumData = { 'ability': 'Total' };
        headers.slice(1).forEach(header => {
            sumData[header] = tableData.reduce((acc, row) => acc + (parseFloat(row[header]) || 0), 0);
        });

        headers.forEach(header => {
            const td = document.createElement('td');
            td.textContent = header === 'ability' ? translateAbilityName(sumData[header], currentLang) : (sumData[header] || 0).toFixed(2);
            sumRow.appendChild(td);
        });
        detailsTableBody.appendChild(sumRow);
    }

    /**
     * Builds the details table for the DPS stack simulation.
     * @param {object} data - The DPS stack simulation data.
     */
    function buildDpsStackDetailsTable(data) {
        if (!data) return;
    
        const individualGains = data.individual_gains || [];
        const totalGains = data.total_gains || {};
    
        const headers = [
            'ability', 
            ...individualGains.map(d => i18n[currentLang][`attr_${d.attribute.replace(/\s/g, '_').replace(/[()]/g, '')}`] || d.attribute),
            'Total'
        ];
        
        const allAbilities = [...new Set([
            ...Object.keys(totalGains),
            ...individualGains.flatMap(d => Object.keys(d.ability_gains))
        ])].sort();
    
        const headerRow = document.createElement('tr');
        headers.forEach(headerText => {
            const th = document.createElement('th');
            th.textContent = headerText === 'ability' ? (i18n[currentLang]['ability_header'] || 'Ability') : headerText;
            headerRow.appendChild(th);
        });
        detailsTableHead.appendChild(headerRow);
    
        allAbilities.forEach(ability => {
            const tr = document.createElement('tr');
            const rowData = {
                ability: translateAbilityName(ability, currentLang),
                Total: (parseFloat(totalGains[ability]) || 0).toFixed(2),
            };
            individualGains.forEach(gain => {
                const attributeName = i18n[currentLang][`attr_${gain.attribute.replace(/\s/g, '_').replace(/[()]/g, '')}`] || gain.attribute;
                rowData[attributeName] = (parseFloat(gain.ability_gains[ability]) || 0).toFixed(2);
            });
    
            headers.forEach(header => {
                const td = document.createElement('td');
                td.textContent = rowData[header];
                tr.appendChild(td);
            });
            detailsTableBody.appendChild(tr);
        });
    
        // Add a summary row at the bottom.
        const sumRow = document.createElement('tr');
        sumRow.classList.add('total-row');
        const sumData = { 'ability': 'Total' };
    
        individualGains.forEach(gain => {
            const attributeName = i18n[currentLang][`attr_${gain.attribute.replace(/\s/g, '_').replace(/[()]/g, '')}`] || gain.attribute;
            sumData[attributeName] = Object.values(gain.ability_gains).reduce((sum, val) => sum + (parseFloat(val) || 0), 0).toFixed(2);
        });
        sumData['Total'] = Object.values(totalGains).reduce((sum, val) => sum + (parseFloat(val) || 0), 0).toFixed(2);
    
        headers.forEach(header => {
            const td = document.createElement('td');
            td.textContent = header === 'ability' ? translateAbilityName(sumData.ability, currentLang) : sumData[header];
            sumRow.appendChild(td);
        });
        detailsTableBody.appendChild(sumRow);
    }

    /**
     * Renders the stacked bar chart for the DPS simulation.
     * @param {object} data - The DPS stack simulation data.
     */
    function renderDpsStackChart(data) {
        const ctx = document.getElementById('dps-stack-chart').getContext('2d');
        if (dpsStackChart) {
            dpsStackChart.destroy();
        }
    
        const individualGains = data.individual_gains || [];
        const totalGains = data.total_gains || {};
    
        const originalLabels = ['Total', ...individualGains.map(d => d.attribute)];
        const allAbilities = [...new Set([
            ...Object.keys(totalGains),
            ...individualGains.flatMap(d => Object.keys(d.ability_gains))
        ])];
    
        const datasets = allAbilities.map((ability, index) => {
            const abilityData = [
                totalGains[ability] || 0,
                ...individualGains.map(d => d.ability_gains[ability] || 0)
            ];
            return {
                label: translateAbilityName(ability, currentLang),
                data: abilityData,
                backgroundColor: getHarmoniousColors()[index % getHarmoniousColors().length],
                borderWidth: 0,
                borderSkipped: false,
            };
        });
    
        const totals = originalLabels.map((_, i) => {
            return datasets.reduce((sum, dataset) => {
                return sum + (parseFloat(dataset.data[i]) || 0);
            }, 0);
        });
    
        const newLabels = originalLabels.map((label, i) => {
            const total = totals[i];
            const translatedLabel = i18n[currentLang][`attr_${label.replace(/\s/g, '_').replace(/[()]/g, '')}`] || label;
            return `${translatedLabel} (${total >= 0 ? '+' : ''}${total.toFixed(2)})`;
        });
    
        dpsStackChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: newLabels,
                datasets: datasets
            },
            options: {
                devicePixelRatio: 1, // Final attempt to fix sub-pixel rendering issue
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                layout: { padding: { right: 30, left: 30 } },
                scales: {
                    x: {
                        stacked: true,
                        title: {
                            display: true,
                            text: i18n[currentLang]['chart_dps_gain_axis_label'] || 'DPS Gain',
                            color: '#f0f0f0'
                        },
                        ticks: { color: '#f0f0f0' },
                        grid: { color: '#444' }
                    },
                    y: {
                        stacked: true,
                        ticks: { color: '#f0f0f0' },
                        grid: { color: '#444' }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: { color: '#f0f0f0' }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) label += ': ';
                                if (context.parsed.x !== null) label += context.parsed.x.toFixed(2);
                                return label;
                            }
                        }
                    },
                    datalabels: { display: false }
                }
            }
        });
    }

    /**
     * Provides a set of harmonious colors for the charts.
     * @returns {Array<string>} An array of color hex codes.
     */
    function getHarmoniousColors() {
        const warm = ['#ff4500', '#ff7f50', '#ffa500', '#ffdab9', '#ffdead'];
        const cool = ['#1e90ff', '#add8e6', '#87cefa', '#b0c4de', '#afeeee'];
        const combined = [];
        for (let i = 0; i < Math.max(warm.length, cool.length); i++) {
            if (warm[i]) combined.push(warm[i]);
            if (cool[i]) combined.push(cool[i]);
        }
        return combined;
    }
});
