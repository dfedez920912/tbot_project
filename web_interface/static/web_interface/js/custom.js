console.log("Custom JS cargado");

function getCSRFToken() {
    return $('input[name=csrfmiddlewaretoken]').val();
}

$(document).ready(function () {
    const currentPath = window.location.pathname;
    $('.nav-item a').each(function () {
        const href = $(this).attr('href') || '';
        if (href === currentPath || currentPath.startsWith(href.replace(/\/$/, '') + '/')) {
            $(this).addClass('active');
            $(this).closest('.has-treeview').addClass('menu-open').find('> a').addClass('active');
        }
    });
});

// Mostrar modal
$('#show-import-modal').on('click', function () {
    $('#importModal').modal('show');
});

// Cargar usuarios del grupo AD
$('#load-users-btn').on('click', function () {
    $('#modalTitle').text('Cargando Usuarios del Grupo AD');
    $('#step-confirmation').hide();
    $('#step-loading').show();
    $('#load-users-btn').hide();

    $.get('?action=fetch_ad_admins', function (data) {
        $('#step-loading').hide();
        if (data.success && data.users && data.users.length > 0) {
            const $tbody = $('#ad-users-body');
            $tbody.empty();
            data.users.forEach(user => {
                const row = `
                    <tr>
                        <td><input type="checkbox" class="user-checkbox" 
                        value="${user.username}" 
                        data-first-name="${user.first_name}" 
                        data-last-name="${user.last_name}" 
                        data-email="${user.email}" checked></td>
                        <td>${user.username}</td>
                        <td>${user.name}</td>
                        <td>${user.email}</td>
                    </tr>`;
                $tbody.append(row);
            });
            $('#step-users').show();
            $('#confirm-import').show();
        } else {
            const message = data.message || 'No se encontraron usuarios en el grupo.';
            toastr.warning(message);
            $('#importModal').modal('hide');
        }
    }).fail(function (jqXHR, textStatus, errorThrown) {
        toastr.error('Error de conexión: ' + (jqXHR.responseJSON?.message || 'Desconocido'));
        $('#importModal').modal('hide');
    });
});

// Seleccionar/deseleccionar todos
$(document).on('click', '#select-all', function () {
    $('.user-checkbox').prop('checked', this.checked);
});

// Importar usuarios seleccionados
$('#confirm-import').on('click', function () {
    const selectedUsers = [];
    $('.user-checkbox:checked').each(function () {
        selectedUsers.push({
            username: $(this).val(),
            first_name: $(this).data('first-name'),
            last_name: $(this).data('last-name'),
            email: $(this).data('email')
        });
    });

    // ← Depuración: Verifica qué se está enviando
    console.log("Usuarios seleccionados para importar:", selectedUsers);

    if (selectedUsers.length === 0) {
        toastr.warning('No ha seleccionado ningún usuario.');
        return;
    }

    // ← Depuración: Verifica el token CSRF
    const csrfToken = $('input[name=csrfmiddlewaretoken]').val();
    console.log("CSRF Token:", csrfToken);

    // Mostrar estado de carga
    $('#modalTitle').text('Importando usuarios...');
    $('#step-users').hide();
    $('#step-loading').show();
    $('#confirm-import').hide();

    // ← Enviar la petición
    $.post('', {
        'action': 'import_ad_admins',
        'users': JSON.stringify(selectedUsers),
        'csrfmiddlewaretoken': csrfToken
    }, function (data) {
        if (data.success) {
            $('#step-loading').html(`
                <div class="text-center text-success">
                    <i class="fas fa-check-circle" style="font-size: 48px;"></i>
                    <p>¡Importados: ${data.count} usuarios!</p>
                </div>
            `);
            setTimeout(() => {
                $('#importModal').modal('hide');
                location.reload();
            }, 1500);
        } else {
            $('#step-loading').html(`
                <div class="text-center text-danger">
                    <i class="fas fa-times-circle" style="font-size: 48px;"></i>
                    <p>Error: ${data.message}</p>
                </div>
            `);
            setTimeout(() => {
                $('#importModal').modal('hide');
            }, 2000);
        }
    }).fail(function (jqXHR, textStatus, errorThrown) {
        // ← Este es el error que ves en el modal
        console.error('Error AJAX:', textStatus, errorThrown);
        console.error('Respuesta del servidor:', jqXHR.responseText);

        // ← Muestra el error real en el modal
        const errorMessage = jqXHR.responseJSON?.message || 'Error desconocido';
        $('#step-loading').html(`
            <div class="text-center text-danger">
                <i class="fas fa-times-circle" style="font-size: 48px;"></i>
                <p>Error: ${errorMessage}</p>
            </div>
        `);
        setTimeout(() => {
            $('#importModal').modal('hide');
        }, 2000);
    });
});


// Habilitar/Deshabilitar usuario
$(document).on('click', '.disable-user', function () {
    const $btn = $(this);
    const username = $btn.data('username');

    $.post('', {
        'action': 'toggle_user',
        'username': username,
        'csrfmiddlewaretoken': getCSRFToken()
    }, function (data) {
        if (data.success) {
            const newStatus = !JSON.parse($btn.data('is-active'));
            $btn.data('is-active', newStatus);
            $btn.find('i').removeClass('fa-times fa-check')
                          .addClass(newStatus ? 'fa-check' : 'fa-times');
            toastr.success(`Estado actualizado.`);
        } else {
            toastr.error('Error al cambiar estado.');
        }
    }).fail(function (jqXHR) {
        toastr.error('Error de conexión: ' + (jqXHR.responseJSON?.message || 'Desconocido'));
    });
});

// Eliminar usuario (con modal)
$(document).on('click', '.delete-user', function () {
    const username = $(this).data('username');
    $('#confirm-delete-modal').data('username', username).modal('show');
});

$('#confirm-delete-btn').on('click', function () {
    const $modal = $('#confirm-delete-modal');
    const username = $modal.data('username');

    $.post('', {
        'action': 'delete_user',
        'username': username,
        'csrfmiddlewaretoken': getCSRFToken()
    }, function (data) {
        if (data.success) {
            toastr.success('Usuario eliminado.');
            $modal.modal('hide');
            location.reload();
        } else {
            toastr.error('Error: ' + data.message);
        }
    }).fail(function (jqXHR) {
        toastr.error('Error: ' + (jqXHR.responseJSON?.message || 'Desconocido'));
    });
});