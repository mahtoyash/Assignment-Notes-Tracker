/**
 * Frontend JavaScript for GSM Assignment Alert System Dashboard
 */

document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
});

function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 4500);
}

function initEventListeners() {
    // 1. Single User Test Call Buttons
    document.querySelectorAll('.btn-test-call').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const userId = btn.dataset.userId;
            const userName = btn.dataset.userName || 'Student';
            
            const originalText = btn.innerHTML;
            btn.innerHTML = '⏳ Dialing...';
            btn.disabled = true;

            try {
                showToast(`📞 Dialing GSM call to <b>${userName}</b>...`, 'info');
                const res = await fetch(`/api/users/${userId}/call`, { method: 'POST' });
                const data = await res.json();

                if (data.success) {
                    showToast(`✅ Call completed (${data.status}): "${data.message}"`, 'success');
                    setTimeout(() => location.reload(), 1500);
                } else {
                    showToast(`❌ Call failed: ${data.error}`, 'error');
                }
            } catch (err) {
                showToast(`❌ Network error initiating call`, 'error');
            } finally {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        });
    });

    // 2. Trigger Batch Alert for All Active Students
    const btnBatchAlert = document.getElementById('btn-batch-alert');
    if (btnBatchAlert) {
        btnBatchAlert.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to trigger automated GSM calls to ALL active students right now?')) {
                return;
            }

            const originalText = btnBatchAlert.innerHTML;
            btnBatchAlert.innerHTML = '⏳ Calling Queue...';
            btnBatchAlert.disabled = true;

            try {
                showToast('🚀 Processing batch alert queue...', 'info');
                const res = await fetch('/api/alerts/trigger-all', { method: 'POST' });
                const data = await res.json();

                if (data.success) {
                    showToast(`✅ Batch queue finished! Dispatched ${data.dispatched} call(s).`, 'success');
                    setTimeout(() => location.reload(), 1800);
                } else {
                    showToast(`❌ Batch trigger error: ${data.error}`, 'error');
                }
            } catch (err) {
                showToast('❌ Error executing batch alert queue', 'error');
            } finally {
                btnBatchAlert.innerHTML = originalText;
                btnBatchAlert.disabled = false;
            }
        });
    }

    // 3. Toggle User Active Status
    document.querySelectorAll('.btn-toggle-user').forEach(btn => {
        btn.addEventListener('click', async () => {
            const userId = btn.dataset.userId;
            try {
                const res = await fetch(`/api/users/${userId}/toggle`, { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    showToast(`Alerts ${data.is_active ? 'Activated' : 'Paused'} for student`, 'info');
                    setTimeout(() => location.reload(), 600);
                }
            } catch (e) {
                showToast('Failed to toggle status', 'error');
            }
        });
    });

    // 4. Delete User
    document.querySelectorAll('.btn-delete-user').forEach(btn => {
        btn.addEventListener('click', async () => {
            const userId = btn.dataset.userId;
            const userName = btn.dataset.userName || 'Student';
            if (!confirm(`Are you sure you want to remove ${userName} from the alert system?`)) {
                return;
            }

            try {
                const res = await fetch(`/api/users/${userId}/delete`, { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    showToast(`Student removed successfully`, 'success');
                    setTimeout(() => location.reload(), 600);
                }
            } catch (e) {
                showToast('Failed to delete student', 'error');
            }
        });
    });
}
