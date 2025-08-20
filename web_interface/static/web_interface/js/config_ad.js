console.log("config_ad.js cargado");

// Función para obtener el token CSRF
function getCSRFToken() {
    return $('input[name=csrfmiddlewaretoken]').val();
}

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

    // --- Guardar la configuración original al cargar ---
    const originalConfig = {};
    $('#ad-config-form :input').each(function () {
        if (this.name) {
            originalConfig[this.name] = $(this).val();
        }
    });

    // --- Detectar cambios y habilitar/deshabilitar botón de guardado ---
    function checkChanges() {
        let hasChanges = false;
        $('#ad-config-form :input').each(function () {
            if (this.name && originalConfig[this.name] !== $(this).val()) {
                hasChanges = true;
            }
        });
        $('#save-config-btn').prop('disabled', !hasChanges);
    }

    // Verificar cambios en cada input
    $('#ad-config-form :input').on('input change', checkChanges);

    // --- Probar conexión ---
    $('#test-connection').on('click', function () {
        $('#status-message')
            .removeClass('alert-success alert-danger')
            .text('Probando conexión...')
            .addClass('alert-info')
            .show();

        $.get('?action=test_connection', function (data) {
            const alertClass = data.success ? 'alert-success' : 'alert-danger';
            $('#status-message')
                .removeClass('alert-info alert-success alert-danger')
                .addClass(alertClass)
                .text(data.message);
        }).fail(function (jqXHR) {
            $('#status-message')
                .removeClass('alert-info alert-success')
                .addClass('alert-danger')
                .text('Error de conexión: ' + (jqXHR.responseJSON?.message || 'Verifique la consola'));
        });
    });

    // --- Guardar configuración con modal de confirmación ---
    $('#save-config-btn').on('click', function () {
        const changes = [];
        const formData = $('#ad-config-form').serializeArray();
        const dataToSend = { csrfmiddlewaretoken: getCSRFToken() };

        formData.forEach(field => {
            dataToSend[field.name] = field.value;
            if (originalConfig[field.name] !== field.value) {
                changes.push(`<strong>${field.name}</strong>: <code>${originalConfig[field.name] || '(vacío)'}</code> → <code>${field.value || '(vacío)'}</code>`);
            }
        });

        if (changes.length === 0) {
            toastr.info('No hay cambios para guardar.');
            return;
        }

        // Mostrar modal de confirmación
        $('#confirm-changes-list').html(changes.join('<br>'));
        $('#confirm-save-modal').modal('show');
    });

    // --- Confirmar guardado ---
    $('#confirm-save-btn').on('click', function () {
        const formData = $('#ad-config-form').serialize();
        $.post('', formData, function (data) {
            if (data.status === 'success') {
                toastr.success('Configuración guardada.');
                $('#confirm-save-modal').modal('hide');
                // Actualizar configuración original
                $('#ad-config-form :input').each(function () {
                    if (this.name) {
                        originalConfig[this.name] = $(this).val();
                    }
                });
                $('#save-config-btn').prop('disabled', true);
            } else {
                toastr.error('Error: ' + (data.message || 'Desconocido'));
                $('#confirm-save-modal').modal('hide');
            }
        }).fail(function (jqXHR) {
            toastr.error('Error de conexión: ' + (jqXHR.responseJSON?.message || 'Verifique la consola'));
            $('#confirm-save-modal').modal('hide');
        });
    });
});