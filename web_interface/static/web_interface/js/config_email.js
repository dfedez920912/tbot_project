console.log("config_email.js cargado");

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
    const originalConfig = {};
    $('#email-config-form :input').each(function () {
        if (this.name) {
            originalConfig[this.name] = $(this).val();
        }
    });

    // --- Detectar cambios ---
    function checkChanges() {
        let hasChanges = false;
        const changes = [];
        $('#email-config-form :input').each(function () {
            if (this.name && originalConfig[this.name] !== $(this).val()) {
                hasChanges = true;
                changes.push(`<li><strong>${this.name}</strong>: <code>${originalConfig[this.name] || '(vacío)'}</code> → <code>${$(this).val() || '(vacío)'}</code></li>`);
            }
        });
        $('#save-config-btn').prop('disabled', !hasChanges);
        $('#changes-list').html(changes.join(''));
    }

    $('#email-config-form :input').on('input change', checkChanges);

    // --- Probar correo ---
    $('#test-email-btn').on('click', function () {
        $('#test-recipient').val('');
        $('#test-email-modal').modal('show');
    });

    $('#send-test-btn').on('click', function () {
        const recipient = $('#test-recipient').val().trim();
        if (!recipient) {
            toastr.warning('Debe ingresar un correo de destino.');
            return;
        }

        $.post('', {
            'action': 'test_email',
            'recipient': recipient,
            'csrfmiddlewaretoken': getCSRFToken()
        }, function (data) {
            if (data.status === 'success') {
                toastr.success('Correo de prueba enviado.');
                $('#test-email-modal').modal('hide');
            } else {
                toastr.error('Error: ' + (data.message || 'Desconocido'));
            }
        }).fail(function (jqXHR) {
            toastr.error('Error de conexión: ' + (jqXHR.responseJSON?.message || 'Verifique la consola'));
            $('#test-email-modal').modal('hide');
        });
    });

    // --- Guardar configuración ---
    $('#save-config-btn').on('click', function () {
        $('#confirm-save-modal').modal('show');
    });

    // --- Confirmar guardado ---
    $('#confirm-save-btn').on('click', function () {
        // ← Serializar el formulario y añadir manualmente 'action'
        const formData = $('#email-config-form').serialize();
        const dataToSend = `${formData}&action=save_config`;

        $.post('', dataToSend, function (data) {
            if (data.status === 'success') {
                toastr.success('Configuración guardada.');
                $('#confirm-save-modal').modal('hide');
                // Actualizar configuración original
                $('#email-config-form :input').each(function () {
                    if (this.name) {
                        originalConfig[this.name] = $(this).val();
                    }
                });
                $('#save-config-btn').prop('disabled', true);
            } else {
                const errorMsg = data?.message || 'Error desconocido';
                toastr.error('Error: ' + errorMsg);
                $('#confirm-save-modal').modal('hide');
            }
        }).fail(function (jqXHR, textStatus, errorThrown) {
            console.error('Error AJAX:', textStatus, errorThrown);
            console.error('Respuesta:', jqXHR.responseText);
            toastr.error('Error de conexión: ' + (jqXHR.responseJSON?.message || 'Verifique la consola'));
            $('#confirm-save-modal').modal('hide');
        });
    });
});