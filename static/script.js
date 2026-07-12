document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const targetFileInput = document.getElementById('target-file');
    const sourceFileInput = document.getElementById('source-file');
    const targetLabel = document.getElementById('target-upload-box').querySelector('.upload-label');
    const sourceLabel = document.getElementById('source-upload-box').querySelector('.upload-label');
    const targetFileName = document.getElementById('target-file-name');
    const sourceFileName = document.getElementById('source-file-name');
    const targetLoader = document.getElementById('target-loader');
    const sourceLoader = document.getElementById('source-loader');
    
    const targetColSelect = document.getElementById('target-col-select');
    const sourceColSelect = document.getElementById('source-col-select');
    const columnsSection = document.getElementById('columns-section');
    
    const thresholdInput = document.getElementById('threshold');
    const thresholdVal = document.getElementById('threshold-val');
    
    const runBtn = document.getElementById('run-btn');
    const btnText = runBtn.querySelector('.btn-text');
    const runLoader = document.getElementById('run-loader');
    const downloadBtn = document.getElementById('download-btn');
    const statusMessage = document.getElementById('status-message');

    // State
    let targetFileUploaded = '';
    let sourceFileUploaded = '';

    // Event Listeners for File Uploads
    targetFileInput.addEventListener('change', (e) => handleFileUpload(e.target.files[0], 'target'));
    sourceFileInput.addEventListener('change', (e) => handleFileUpload(e.target.files[0], 'source'));

    // Drag and drop handlers
    [targetLabel, sourceLabel].forEach(label => {
        label.addEventListener('dragover', (e) => {
            e.preventDefault();
            label.style.borderColor = 'var(--primary)';
        });
        label.addEventListener('dragleave', (e) => {
            e.preventDefault();
            label.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        });
    });

    targetLabel.addEventListener('drop', (e) => {
        e.preventDefault();
        targetLabel.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        if (e.dataTransfer.files.length) {
            handleFileUpload(e.dataTransfer.files[0], 'target');
        }
    });

    sourceLabel.addEventListener('drop', (e) => {
        e.preventDefault();
        sourceLabel.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        if (e.dataTransfer.files.length) {
            handleFileUpload(e.dataTransfer.files[0], 'source');
        }
    });

    // Threshold value updater
    thresholdInput.addEventListener('input', (e) => {
        thresholdVal.textContent = e.target.value;
    });

    // Run Button
    runBtn.addEventListener('click', runMatch);

    async function handleFileUpload(file, type) {
        if (!file) return;

        const isTarget = type === 'target';
        const nameEl = isTarget ? targetFileName : sourceFileName;
        const labelEl = isTarget ? targetLabel : sourceLabel;
        const loaderEl = isTarget ? targetLoader : sourceLoader;
        const selectEl = isTarget ? targetColSelect : sourceColSelect;

        // UI Loading State
        nameEl.style.opacity = '0';
        loaderEl.style.display = 'block';
        
        const formData = new FormData();
        formData.append('file', file);
        formData.append('csv_separator', document.getElementById('csv-separator').value);
        formData.append('csv_quotechar', document.getElementById('csv-quotechar').value);

        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();

            if (response.ok) {
                // Update State
                if (isTarget) targetFileUploaded = data.filename;
                else sourceFileUploaded = data.filename;

                // Update UI
                nameEl.textContent = file.name;
                labelEl.classList.add('success');
                
                // Populate Dropdown
                populateDropdown(selectEl, data.columns);
                selectEl.disabled = false;
                
                checkReadyState();
            } else {
                throw new Error(data.error || 'Upload failed');
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
        if (columns.length === 0) {
            selectElement.innerHTML = '<option value="">No columns found</option>';
            return;
        }
        columns.forEach(col => {
            const option = document.createElement('option');
            option.value = col;
            option.textContent = col;
            selectElement.appendChild(option);
        });
    }

    function checkReadyState() {
        if (targetFileUploaded && sourceFileUploaded) {
            columnsSection.classList.remove('disabled');
            runBtn.disabled = false;
        }
    }

    async function runMatch() {
        if (!targetColSelect.value || !sourceColSelect.value) {
            showStatus('Please select both columns before running.', 'error');
            return;
        }

        // Set loading state
        runBtn.disabled = true;
        btnText.style.display = 'none';
        runLoader.style.display = 'block';
        downloadBtn.classList.add('hidden');
        showStatus('Running fuzzy match...', '');

        const payload = {
            target_file: targetFileUploaded,
            source_file: sourceFileUploaded,
            target_col: targetColSelect.value,
            source_col: sourceColSelect.value,
            scorer: document.getElementById('scorer').value,
            threshold: parseFloat(thresholdInput.value),
            export_format: document.getElementById('export-format').value,
            csv_separator: document.getElementById('csv-separator').value,
            csv_quotechar: document.getElementById('csv-quotechar').value,
            preprocess_options: {
                lowercase: document.getElementById('opt-lowercase').checked,
                trim: document.getElementById('opt-trim').checked,
                remove_punct: document.getElementById('opt-remove-punct').checked,
                remove_stopwords: document.getElementById('opt-remove-stopwords').checked,
                stem: document.getElementById('opt-stem').checked
            }
        };

        try {
            const response = await fetch('/api/match', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            const data = await response.json();

            if (response.ok && data.success) {
                showStatus('Match completed successfully!', 'success');
                downloadBtn.href = `/api/download/${data.output_file}`;
                downloadBtn.classList.remove('hidden');
            } else {
                throw new Error(data.error || 'Match failed');
            }
        } catch (error) {
            showStatus(`Error during matching: ${error.message}`, 'error');
        } finally {
            runBtn.disabled = false;
            btnText.style.display = 'block';
            runLoader.style.display = 'none';
        }
    }

    function showStatus(msg, type) {
        statusMessage.textContent = msg;
        statusMessage.className = 'status-message'; // reset
        if (type === 'error') statusMessage.classList.add('status-error');
        if (type === 'success') statusMessage.classList.add('status-success');
    }
});
