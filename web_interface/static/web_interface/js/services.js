console.log("services.js cargado");

let botRunning = typeof BOT_RUNNING !== 'undefined' ? BOT_RUNNING : false;
let startTime = START_TIME ? new Date(START_TIME) : null;
let uptimeInterval = null;

const $toggle = $('#telegram_running');
const $autoStart = $('#auto_start');
const $loading = $('<span class="spinner-border spinner-border-sm" role="status"></span>');

function updateUI() {
    $toggle.prop('checked', botRunning);
    $autoStart.prop('checked', {{ auto_start|default:"false"|lower }});
}

async function toggleTelegram() {
    const action = $toggle.is(':checked') ? 'start' : 'stop';
    replaceWithLoading($toggle);
    try {
        const response = await fetch('/services/telegram/toggle/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ action: action })
        });
        const data = await response.json();
        if (data.status === 'success') {
            botRunning = action === 'start';
            startTime = botRunning ? new Date() : null;
            updateUI();
            toastr.success(data.message);
        } else {
            restoreToggle();
            toastr.error('Error: ' + data.message);
            $toggle.prop('checked', !botRunning);
        }
    } catch (error) {
        restoreToggle();
        toastr.error('Error: ' + error.message);
        $toggle.prop('checked', !botRunning);
    }
}

async function toggleAutoStart() {
    const enable = $autoStart.is(':checked');
    try {
        const response = await fetch('/services/telegram/set_auto_start/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ enable: enable })
        });
        const data = await response.json();
        if (data.status === 'success') {
            toastr.success(data.message);
        } else {
            $autoStart.prop('checked', !$autoStart.is(':checked'));
            toastr.error('Error: ' + data.message);
        }
    } catch (error) {
        $autoStart.prop('checked', !$autoStart.is(':checked'));
        toastr.error('Error: ' + error.message);
    }
}

function replaceWithLoading($element) {
    const parent = $element.parent();
    const wrapper = $('<div class="d-flex justify-content-center"></div>');
    wrapper.append($loading.clone());
    $element.replaceWith(wrapper);
}

function restoreToggle() {
    const parent = $loading.parent();
    parent.replaceWith($toggle);
}

function getCSRFToken() {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, 10) === ('csrftoken' + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(10));
                break;
            }
        }
    }
    return cookieValue;
}

// ← Event Listeners
$toggle.on('change', toggleTelegram);
$autoStart.on('change', toggleAutoStart);

// ← Inicializar UI
updateUI();

// ← Inicializar componentes de MDB
document.addEventListener("DOMContentLoaded", function () {
    const inputs = document.querySelectorAll('.form-outline');
    inputs.forEach(input => {
        new mdb.Input(input);
    });
});

// ← Función para buscar servicios
function searchServices() {
    const searchTerm = document.getElementById('filter-service').value.toLowerCase();
    // ← Aquí puedes agregar lógica para filtrar filas de la tabla
    console.log("Buscando:", searchTerm);
    toastr.info("Buscar servicios...");
}