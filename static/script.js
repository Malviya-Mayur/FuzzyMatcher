document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const targetFileInput  = document.getElementById('target-file');
    const sourceFileInput  = document.getElementById('source-file');
    const targetLabel      = document.getElementById('target-upload-box').querySelector('.upload-label');
    const sourceLabel      = document.getElementById('source-upload-box').querySelector('.upload-label');
    const targetFileName   = document.getElementById('target-file-name');
    const sourceFileName   = document.getElementById('source-file-name');
    const targetLoader     = document.getElementById('target-loader');
    const sourceLoader     = document.getElementById('source-loader');

    const targetColSelect  = document.getElementById('target-col-select');
    const sourceColSelect  = document.getElementById('source-col-select');
    const columnsSection   = document.getElementById('columns-section');

    const thresholdInput   = document.getElementById('threshold');
    const thresholdVal     = document.getElementById('threshold-val');

    const runBtn           = document.getElementById('run-btn');
    const btnText          = runBtn.querySelector('.btn-text');
    const runLoader        = document.getElementById('run-loader');
    const downloadBtn      = document.getElementById('download-btn');
    const statusMessage    = document.getElementById('status-message');

    const progressSection  = document.getElementById('progress-section');
    const progressBarFill  = document.getElementById('progress-bar-fill');
    const progressLabel    = document.getElementById('progress-label');

    const scorerSelect     = document.getElementById('scorer');

    let targetFileUploaded = '';
    let sourceFileUploaded = '';
    let pollTimer          = null;

    // ----------------------------------------------------------------
    // Load plugin scorers dynamically on startup
    // ----------------------------------------------------------------
    fetch('/api/scorers')
        .then(r => r.json())
        .then(scorers => {
            // Clear existing options then re-populate
            scorerSelect.innerHTML = '';
            for (const [key, label] of Object.entries(scorers)) {
                const opt = document.createElement('option');
                opt.value = key;
                opt.textContent = label;
                scorerSelect.appendChild(opt);
            }
        })
        .catch(() => { /* keep the static fallback options */ });

    // ----------------------------------------------------------------
    // File upload handlers
    // ----------------------------------------------------------------
    targetFileInput.addEventListener('change', e => handleFileUpload(e.target.files[0], 'target'));
    sourceFileInput.addEventListener('change', e => handleFileUpload(e.target.files[0], 'source'));

    [targetLabel, sourceLabel].forEach(label => {
        label.addEventListener('dragover', e => {
            e.preventDefault();
            label.style.borderColor = 'var(--primary)';
        });
        label.addEventListener('dragleave', e => {
            e.preventDefault();
            label.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        });
    });

    targetLabel.addEventListener('drop', e => {
        e.preventDefault();
        targetLabel.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        if (e.dataTransfer.files.length) handleFileUpload(e.dataTransfer.files[0], 'target');
    });

    sourceLabel.addEventListener('drop', e => {
        e.preventDefault();
        sourceLabel.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        if (e.dataTransfer.files.length) handleFileUpload(e.dataTransfer.files[0], 'source');
    });

    thresholdInput.addEventListener('input', e => {
        thresholdVal.textContent = e.target.value;
    });

    runBtn.addEventListener('click', runMatch);

    async function handleFileUpload(file, type) {
        if (!file) return;
        const isTarget = type === 'target';
        const nameEl   = isTarget ? targetFileName : sourceFileName;
        const labelEl  = isTarget ? targetLabel    : sourceLabel;
        const loaderEl = isTarget ? targetLoader   : sourceLoader;
        const selectEl = isTarget ? targetColSelect: sourceColSelect;

        nameEl.style.opacity = '0';
        loaderEl.style.display = 'block';

        const formData = new FormData();
        formData.append('file', file);
        formData.append('csv_separator', document.getElementById('csv-separator').value);
        formData.append('csv_quotechar', document.getElementById('csv-quotechar').value);

        try {
            const response = await fetch('/api/upload', { method: 'POST', body: formData });
            const data = await response.json();
            if (response.ok) {
                if (isTarget) targetFileUploaded = data.filename;
                else          sourceFileUploaded = data.filename;

                nameEl.textContent = file.name;
                labelEl.classList.add('success');
                populateDropdown(selectEl, data.columns);
                selectEl.disabled = false;
                checkReadyState();
            } else {
                throw new Error(data.detail || data.error || 'Upload failed');
            }
        } catch (error) {
            showStatus(`Error uploading ${type} file: ${error.message}`, 'error');
            nameEl.textContent = 'Upload Failed';
            labelEl.classList.remove('success');
        } finally {
            loaderEl.style.display = 'none';
            nameEl.style.opacity = '1';
        }
    }

    function populateDropdown(selectElement, columns) {
        selectElement.innerHTML = '';
        if (!columns.length) {
            selectElement.innerHTML = '<option value="">No columns found</option>';
            return;
        }
        columns.forEach(col => {
            const opt = document.createElement('option');
            opt.value = col;
            opt.textContent = col;
            selectElement.appendChild(opt);
        });
    }

    function checkReadyState() {
        if (targetFileUploaded && sourceFileUploaded) {
            columnsSection.classList.remove('disabled');
            runBtn.disabled = false;
        }
    }

    // ----------------------------------------------------------------
    // Match job — POST then poll
    // ----------------------------------------------------------------
    async function runMatch() {
        if (!targetColSelect.value || !sourceColSelect.value) {
            showStatus('Please select both columns before running.', 'error');
            return;
        }

        runBtn.disabled = true;
        btnText.style.display = 'none';
        runLoader.style.display = 'block';
        downloadBtn.classList.add('hidden');
        progressSection.classList.remove('hidden');
        setProgress(0, 0);
        showStatus('Submitting job…', '');

        const payload = {
            target_file:   targetFileUploaded,
            source_file:   sourceFileUploaded,
            target_col:    targetColSelect.value,
            source_col:    sourceColSelect.value,
            scorer:        document.getElementById('scorer').value,
            threshold:     parseFloat(thresholdInput.value),
            export_format: document.getElementById('export-format').value,
            csv_separator: document.getElementById('csv-separator').value,
            csv_quotechar: document.getElementById('csv-quotechar').value,
            preprocess_options: {
                lowercase:        document.getElementById('opt-lowercase').checked,
                trim:             document.getElementById('opt-trim').checked,
                remove_punct:     document.getElementById('opt-remove-punct').checked,
                remove_stopwords: document.getElementById('opt-remove-stopwords').checked,
                stem:             document.getElementById('opt-stem').checked,
                normalize_accents:document.getElementById('opt-normalize-accents').checked,
            }
        };

        try {
            const res  = await fetch('/api/jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Job creation failed');

            showStatus('Running fuzzy match…', '');
            pollJobStatus(data.job_id);

        } catch (error) {
            showStatus(`Error: ${error.message}`, 'error');
            resetRunButton();
        }
    }

    function pollJobStatus(jobId) {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(async () => {
            try {
                const res  = await fetch(`/api/jobs/${jobId}`);
                const data = await res.json();

                if (data.status === 'running' || data.status === 'queued') {
                    setProgress(data.progress, data.total);
                    showStatus(data.total > 0
                        ? `Processing batch ${data.progress} / ${data.total}…`
                        : 'Starting…', '');

                } else if (data.status === 'done') {
                    clearInterval(pollTimer);
                    setProgress(data.total || 1, data.total || 1);
                    showStatus('Match completed successfully!', 'success');
                    downloadBtn.href = `/api/download/${data.output_file}`;
                    downloadBtn.classList.remove('hidden');
                    resetRunButton();

                } else if (data.status === 'error') {
                    clearInterval(pollTimer);
                    showStatus(`Error: ${data.error}`, 'error');
                    resetRunButton();
                }
            } catch (e) {
                // network blip — keep polling
            }
        }, 800);
    }

    function setProgress(completed, total) {
        const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
        progressBarFill.style.width = pct + '%';
        progressLabel.textContent = total > 0
            ? `Batch ${completed} / ${total} (${pct}%)`
            : 'Preparing…';
    }

    function resetRunButton() {
        runBtn.disabled = false;
        btnText.style.display = 'block';
        runLoader.style.display = 'none';
    }

    function showStatus(msg, type) {
        statusMessage.textContent = msg;
        statusMessage.className = 'status-message';
        if (type === 'error')   statusMessage.classList.add('status-error');
        if (type === 'success') statusMessage.classList.add('status-success');
    }
});