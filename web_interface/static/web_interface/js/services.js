// ← Esperar a que el DOM esté listo
$(document).ready(function () {
    console.log("services.js: DOM cargado y listo");

    // ← URLs de los endpoints
    const TELEGRAM_START_URL = '/services/telegram/start/';
    const TELEGRAM_STOP_URL = '/services/telegram/stop/';
    const TELEGRAM_STATUS_URL = '/services/telegram/status/';

    // ← Variables de estado
    let botRunning = false;
    let startTime = null;
    let uptimeInterval = null; // ← ID del intervalo del contador
    let statusInterval = null; // ← ID del intervalo de estado
    let lastKnownRunning = null;

    // ← Control de operación
    let isProcessing = false;

    // ← Elementos del DOM
    const $container = $('.custom-control.custom-switch');
    const $modal = $('#confirm-modal');
    const $confirmBtn = $('#confirm-action-btn');
    const $cancelBtn = $modal.find('[data-dismiss="modal"]');
    const $uptimeElement = $('#uptime'); // ← Elemento del DOM
    const $autoStart = $('#auto_start');

    if ($container.length === 0) {
        console.error("services.js: No se encontró el contenedor del toggle");
        return;
    }

    if ($modal.length === 0) {
        console.error("services.js: No se encontró el modal #confirm-modal");
        return;
    }

    if (!$uptimeElement.length) {
        console.error("services.js: No se encontró #uptime");
        return;
    }

    // ← Función para obtener CSRF Token
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

    // ← Mostrar spinner
    function showSpinner() {
        $container.html('<div class="d-flex justify-content-center"><span class="spinner-border spinner-border-sm" role="status"></span></div>');
    }

    // ← Restaurar toggle con estado
    function restoreToggle(checked) {
        $container.html(`
            <input type="checkbox" class="custom-control-input" id="telegram_running">
            <label class="custom-control-label" for="telegram_running"></label>
        `);
        const $newToggle = $('#telegram_running');
        if (checked) $newToggle.prop('checked', true);
        // ← No asignar evento aquí, se delega
    }

    // ← Formatear el tiempo: 01Y, 01M, 01d, 01:50:50
    function formatUptime(totalSeconds) {
        if (totalSeconds < 0) return '00:00:00';

        const secs = Math.floor(totalSeconds) % 60;
        const mins = Math.floor(totalSeconds / 60) % 60;
        const hours = Math.floor(totalSeconds / 3600) % 24;
        const days = Math.floor(totalSeconds / 86400) % 30;
        const months = Math.floor(totalSeconds / 2592000) % 12;
        const years = Math.floor(totalSeconds / 31536000);

        const parts = [];
        if (years > 0) parts.push(`${years}Y`);
        if (months > 0) parts.push(`${months}M`);
        if (days > 0) parts.push(`${days}d`);

        const timePart = `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

        return parts.length > 0 ? parts.join(', ') + ', ' + timePart : timePart;
    }

    // ← Actualizar el contador
    function updateUptime() {
        if (botRunning && startTime) {
            const now = Math.floor(Date.now() / 1000);
            const elapsed = now - startTime;
            $uptimeElement.text(formatUptime(elapsed));
        } else {
            $uptimeElement.text('--:--:--');
        }
    }

    // ← Iniciar el contador
    function startUptime() {
        clearInterval(uptimeInterval);
        uptimeInterval = setInterval(updateUptime, 1000);
        updateUptime();
    }

    // ← Detener el contador
    function stopUptime() {
        clearInterval(uptimeInterval);
        $uptimeElement.text('--:--:--'); // ← Corregido: era $uptimeInterval
    }

    // ← Mostrar notificación
    function showNotification(message, type = 'info') {
        if (typeof toastr !== 'undefined') {
            toastr[type](message);
        }
    }

    // ← Detectar cambios de estado
    function handleStatusChange(newState, newStartTime) {
        if (lastKnownRunning === null) {
            lastKnownRunning = newState;
            return;
        }

        if (lastKnownRunning && !newState) {
            if (isProcessing) {
                showNotification('🔴 El bot ha sido <strong>detenido</strong>.', 'error');
                restoreToggle(false);
                stopUptime();
                isProcessing = false;
            }
        } else if (!lastKnownRunning && newState) {
            showNotification('🟢 El bot ha sido <strong>iniciado</strong>.', 'success');
        }

        if (newState && startTime && newStartTime && newStartTime !== startTime) {
            showNotification('🔄 El bot ha sido <strong>reiniciado</strong>.', 'info');
        }

        startTime = newStartTime;
        lastKnownRunning = newState;
    }

    // ← Obtener estado del bot
    async function getTelegramStatus() {
        if (isProcessing) return;

        try {
            const response = await fetch(TELEGRAM_STATUS_URL, {
                method: 'GET',
                headers: {
                    'X-CSRFToken': getCSRFToken(),
                    'Content-Type': 'application/json'
                },
                credentials: 'same-origin',
                cache: 'no-store'
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            if (data.status === 'success') {
                const wasRunning = botRunning;
                const oldStartTime = startTime;

                botRunning = data.data.running;
                startTime = data.data.start_time;

                handleStatusChange(botRunning, startTime);

                if (wasRunning !== botRunning || startTime !== oldStartTime) {
                    restoreToggle(botRunning);
                }

                if (botRunning && startTime) {
                    startUptime();
                } else {
                    stopUptime();
                }
            }
        } catch (error) {
            console.error('Error en getTelegramStatus:', error);
        }
    }

    // ← Iniciar el bot
    async function startTelegram() {
        if (isProcessing) return;
        isProcessing = true;
        showSpinner();
        try {
            const response = await fetch(TELEGRAM_START_URL, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCSRFToken(),
                    'Content-Type': 'application/json'
                },
                credentials: 'same-origin'
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            if (data.status === 'success') {
                botRunning = true;
                if (data.data && data.data.start_time) {
                    startTime = data.data.start_time;
                } else {
                    startTime = Math.floor(Date.now() / 1000);
                }
                startUptime();
                restoreToggle(true);
                showNotification('🚀 Bot <strong>iniciado</strong>.', 'success');
            } else {
                restoreToggle(false);
                showNotification('❌ Error al iniciar: ' + data.message, 'error');
            }
        } catch (error) {
            console.error('Error en startTelegram:', error);
            restoreToggle(false);
            showNotification('⚠️ Error de conexión.', 'error');
        } finally {
            isProcessing = false;
        }
    }

    // ← Detener el bot
    async function stopTelegram() {
        $modal.modal('hide');
        showSpinner();
        try {
            const response = await fetch(TELEGRAM_STOP_URL, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCSRFToken(),
                    'Content-Type': 'application/json'
                },
                credentials: 'same-origin'
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            if (data.status === 'success') {
                botRunning = false;
                showNotification('🛑 Bot <strong>detenido</strong>.', 'success');
            } else {
                botRunning = true;
                startUptime();
                restoreToggle(true);
                showNotification('❌ Error al detener: ' + data.message, 'error');
            }
        } catch (error) {
            console.error('Error en stopTelegram:', error);
            botRunning = true;
            startUptime();
            showNotification('⚠️ Error de conexión.', 'error');
            restoreToggle(true);
        }
    }

    // ✅ Manejar el cambio del toggle usando DELEGACIÓN
    $container.on('change', '#telegram_running', function () {
        if (isProcessing) {
            restoreToggle(botRunning);
            return;
        }

        if ($(this).is(':checked')) {
            startTelegram();
        } else {
            showSpinner();
            $modal.modal('show');

            $confirmBtn.off('click.confirm').on('click.confirm', function () {
                stopTelegram();
            });

            $cancelBtn.off('click.cancel').on('click.cancel', function () {
                $modal.one('hidden.bs.modal', function () {
                    restoreToggle(true);
                });
            });
        }
    });

    // ✅ Inicializar estado al cargar
    getTelegramStatus();

    // ✅ Iniciar actualización automática cada 5 segundos
    statusInterval = setInterval(getTelegramStatus, 5000);

    // ✅ Limpieza opcional
    $(window).on('beforeunload', function () {
        clearInterval(uptimeInterval);
        clearInterval(statusInterval);
    });
});