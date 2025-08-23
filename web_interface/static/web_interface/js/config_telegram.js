console.log("config_telegram.js cargado");

$(document).ready(function () {
    // --- Activar ítem del sidebar ---
    const currentPath = window.location.pathname;
    $('.nav-item a').each(function () {
        const href = $(this).attr('href') || '';
        if (href === currentPath || currentPath.startsWith(href.replace(/\/$/, '') + '/')) {
            $(this).addClass('active');
            $(this).closest('.has-treeview').addClass('menu-open').find('> a').addClass('active');
        }
    });

    // --- Guardar configuración original ---
    const originalConfig = {
        token: $('#TELEGRAM_BOT_TOKEN').val().trim(),
        messages: {}
    };

    $('#messages-form textarea').each(function () {
        originalConfig.messages[this.name] = $(this).val().trim();
    });

    // --- Función para detectar cambios ---
    function checkChanges() {
        // ← Verificar si el token ha cambiado
        const currentToken = $('#TELEGRAM_BOT_TOKEN').val().trim();
        const tokenChanged = currentToken !== originalConfig.token;
        $('#save-api-btn').prop('disabled', !tokenChanged);

        // ← Verificar cambios en mensajes
        let messagesChanged = false;
        $('#messages-form textarea').each(function () {
            if ($(this).val().trim() !== originalConfig.messages[this.name]) {
                messagesChanged = true;
            }
        });
        $('#save-messages-btn').prop('disabled', !messagesChanged);
    }

    // ← Detectar cambios en tiempo real
    $('#api-form :input').on('input change', checkChanges);
    $('#messages-form :input').on('input change', checkChanges);

    // ← Llamar a checkChanges al cargar para establecer estado inicial
    checkChanges();

    // --- Verificar Token con protección contra eventos duplicados ---
    $('#test-token-btn').off('click').on('click', function () {
        const token = $('#TELEGRAM_BOT_TOKEN').val().trim();
        if (!token) {
            toastr.warning('Debe ingresar un token.');
            return;
        }

        const $btn = $(this);
        $btn.prop('disabled', true);

        // ← Ocultar botones y mostrar loading
        $('#test-token-btn, #save-api-btn').hide();
        $('#loading-api').show();

        $.post('', {
            'action': 'test_token',
            'TELEGRAM_BOT_TOKEN': token,
            'csrfmiddlewaretoken': getCSRFToken()
        }, function (data) {
            if (data.status === 'success') {
                toastr.success(data.message);
            } else {
                toastr.error(data.message);
            }
        }).fail(function (jqXHR, textStatus, errorThrown) {
            const errorMsg = jqXHR.responseJSON?.message || 'Error de conexión';
            toastr.error('Error: ' + errorMsg);
        }).always(function () {
            // ← Siempre ocultar loading, mostrar botones y reactivar el botón
            $('#loading-api').hide();
            $('#test-token-btn, #save-api-btn').show();
            $btn.prop('disabled', false);
            // ← Volver a verificar cambios después de la respuesta
            checkChanges();
        });
    });

    // --- Vista Previa ---
    $('#preview-btn').off('click').on('click', function () {
        let content = '<div style="font-family: Arial, sans-serif; padding: 10px; border: 1px solid var(--border); border-radius: 0.375rem; background: var(--bg-secondary);">';
        $('#messages-form textarea').each(function () {
            const key = $(this).attr('name');
            const value = $(this).val();
            const label = $(this).prev('label').text() || key;
            content += `<p><strong>${label}:</strong><br>${value}</p>`;
        });
        content += '</div>';
        $('#preview-content').html(content);
        $('#preview-modal').modal('show');
    });

    // --- Guardar API ---
    $('#save-api-btn').off('click').on('click', function () {
        currentFormAction = 'save_api';
        const changes = [];
        if ($('#TELEGRAM_BOT_TOKEN').val().trim() !== originalConfig.token) {
            changes.push(`<li><strong>Token</strong>: <code>${originalConfig.token || '(vacío)'}</code> → <code>${$('#TELEGRAM_BOT_TOKEN').val().trim() || '(vacío)'}</code></li>`);
        }
        $('#changes-list').html(changes.join(''));
        $('#confirm-save-modal').modal('show');
    });

    // --- Guardar Mensajes ---
    $('#save-messages-btn').off('click').on('click', function () {
        currentFormAction = 'save_messages';
        const changes = [];
        $('#messages-form textarea').each(function () {
            if ($(this).val().trim() !== originalConfig.messages[this.name]) {
                changes.push(`<li><strong>${$(this).attr('name')}</strong>: <code>${originalConfig.messages[this.name] || '(vacío)'}</code> → <code>${$(this).val().trim() || '(vacío)'}</code></li>`);
            }
        });
        $('#changes-list').html(changes.join(''));
        $('#confirm-save-modal').modal('show');
    });

    // --- Confirmar Guardado ---
    $('#confirm-save-btn').off('click').on('click', function () {
        const formData = $('#api-form').serialize() + '&' + $('#messages-form').serialize();

        if (currentFormAction === 'save_api') {
            const tokenData = $('#api-form').serialize() + '&action=save_config';
            $.post('', tokenData, function (data) {
                if (data.status === 'success') {
                    toastr.success('API guardada.');
                    // ← Actualizar valor original
                    originalConfig.token = $('#TELEGRAM_BOT_TOKEN').val().trim();
                    $('#save-api-btn').prop('disabled', true);
                } else {
                    toastr.error('Error: ' + (data.message || 'Desconocido'));
                }
                $('#confirm-save-modal').modal('hide');
            }).fail(function (jqXHR) {
                toastr.error('Error: ' + (jqXHR.responseJSON?.message || 'Verifique la consola'));
                $('#confirm-save-modal').modal('hide');
            });
        } else if (currentFormAction === 'save_messages') {
            $.post('', formData + '&action=save_config', function (data) {
                if (data.status === 'success') {
                    toastr.success('Mensajes guardados.');
                    // ← Actualizar valores originales
                    $('#messages-form textarea').each(function () {
                        originalConfig.messages[this.name] = $(this).val().trim();
                    });
                    $('#save-messages-btn').prop('disabled', true);
                } else {
                    toastr.error('Error: ' + (data.message || 'Desconocido'));
                }
                $('#confirm-save-modal').modal('hide');
            }).fail(function (jqXHR) {
                toastr.error('Error: ' + (jqXHR.responseJSON?.message || 'Verifique la consola'));
                $('#confirm-save-modal').modal('hide');
            });
        }
    });
});