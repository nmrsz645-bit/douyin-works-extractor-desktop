function syncExtractionPause(state) {
    const button = document.getElementById('pause-extract');
    if (!button) return;
    button.style.display = state.running ? 'inline-flex' : 'none';
    button.dataset.paused = String(Boolean(state.paused));
    button.textContent = state.paused ? '继续提取' : '暂停提取';
}

async function toggleExtractPause() {
    const button = document.getElementById('pause-extract');
    const action = button.dataset.paused === 'true' ? 'resume' : 'pause';
    button.disabled = true;
    try {
        const response = await fetch(`/api/extraction/${action}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({source: button.dataset.source}),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || '操作失败');
        syncExtractionPause({running: true, paused: result.paused});
        document.getElementById('status').textContent = result.paused
            ? '正在暂停；当前请求完成后停止继续提取。'
            : '已继续提取。';
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        button.disabled = false;
    }
}
