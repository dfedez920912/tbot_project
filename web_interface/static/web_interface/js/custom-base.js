console.log("custom-base.js cargado");

$(document).ready(function () {
    const $body = $('body');
    const $container = $('.toggle-container');
    const $thumb = $('.toggle-thumb');

    // Verificar preferencia guardada
    const isDarkMode = localStorage.getItem('darkMode') === 'true';

    // Aplicar estado inicial
    if (isDarkMode) {
        $body.addClass('dark-mode');
    }

    // Actualizar posición del thumb
    function updateToggle() {
        if ($body.hasClass('dark-mode')) {
            $thumb.css('left', '28px');
        } else {
            $thumb.css('left', '2px');
        }
    }

    updateToggle();

    // Cambiar tema al hacer clic
    $('.theme-toggle-dual').on('click', function () {
        if ($body.hasClass('dark-mode')) {
            $body.removeClass('dark-mode');
            localStorage.setItem('darkMode', 'false');
        } else {
            $body.addClass('dark-mode');
            localStorage.setItem('darkMode', 'true');
        }
        updateToggle();
    });
});