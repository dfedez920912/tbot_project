document.addEventListener('DOMContentLoaded', function () {
    console.log('cron.js: Cargado');

    function getCSRFToken() {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.startsWith('csrftoken=')) {
                    cookieValue = decodeURIComponent(cookie.substring(10));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // ← Manejar clic en "Editar"
    document.querySelectorAll('.edit-cron-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const jobName = this.dataset.job;
            fetch(`/services/cron/edit/${jobName}/`)
                .then(response => response.text())
                .then(html => {
                    document.querySelector('#edit-cron-modal .modal-body').innerHTML = html;
                    $('#edit-cron-modal').modal('show');
                })
                .catch(error => {
                    console.error('Error:', error);
                    toastr.error('Error al cargar el modal.');
                });
        });
    });

    // ✅ Manejar el cambio del toggle (delegado)
    document.addEventListener('change', function (e) {
        const $toggle = e.target.closest('.job-toggle');
        if (!$toggle) return;

        const jobName = $toggle.dataset.job;
        const isEnabled = $toggle.checked;

        fetch('/services/cron/save/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                job: jobName,
                enabled: isEnabled,
                schedule: $toggle.closest('tr').querySelector('.cron-schedule').value || '0 */6 * * *'
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                toastr.success(data.message);
            } else {
                toastr.error('Error: ' + data.message);
                // ← Restaurar estado si falla
                $toggle.checked = !isEnabled;
            }
        })
        .catch(error => {
            console.error('Error:', error);
            toastr.error('Error de conexión.');
            $toggle.checked = !isEnabled;
        });
    });

    // ✅ Botones rápidos y guardado
    document.addEventListener('click', function (e) {
        const modal = document.getElementById('edit-cron-modal');
        const scheduleInput = modal.querySelector('#manual-schedule');

        // ← Quick Schedule
        if (e.target.classList.contains('quick-schedule')) {
            scheduleInput.value = e.target.dataset.value;
        }

        // ← Aplicar
        if (e.target.id === 'apply-schedule') {
            const value = scheduleInput.value.trim();
            if (value) {
                modal.querySelector('input[name="schedule"]').value = value;
                toastr.info('Programación aplicada.');
            }
        }

        // ← Guardar
        if (e.target.id === 'save-cron-btn') {
            const jobName = modal.querySelector('#job-name').value;
            const schedule = modal.querySelector('#manual-schedule').value;
            const enabled = modal.querySelector('#enable-job').checked;

            fetch('/services/cron/save/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCSRFToken(),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ job: jobName, enabled, schedule })
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    toastr.success(data.message);
                    $('#edit-cron-modal').modal('hide');
                    location.reload(); // ← Actualiza UI
                } else {
                    toastr.error('Error: ' + data.message);
                }
            })
            .catch(() => toastr.error('Error de conexión.'));
        }
    });
});