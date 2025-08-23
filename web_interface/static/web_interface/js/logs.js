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

    // --- Inicializar variable ---
    const logsUrl = LOGS_API_URL;

    let autoRefresh = true;
    let refreshInterval;

    // --- Función para cargar logs ---
    function loadLogs() {
        const params = new URLSearchParams({
            level: $("#filter-level").val(),
            source: $("#filter-source").val(),
            search: $("#search-input").val(),
            from_date: $("#from-date").val(),
            to_date: $("#to-date").val(),
            page_size: $("#page-size").val(),
            page: $(".page-item.active").data("page") || 1,
        });

        $.getJSON(logsUrl + "?" + params, function (data) {
            const tbody = $("#logs-body");
            tbody.empty();

            data.logs.forEach((log) => {
                const row = `
                    <tr>
                        <td>${log.timestamp}</td>
                        <td>
                            <span class="badge bg-${
                                {
                                    INFO: "info",
                                    WARNING: "warning",
                                    ERROR: "danger",
                                    CRITICAL: "dark",
                                    DEBUG: "success",
                                    EXCEPTION: "primary",
                                }[log.level]
                            }">${log.level}</span>
                        </td>
                        <td>${log.message.substring(0, 100)}${
                            log.message.length > 100 ? "..." : ""
                        }</td>
                        <td><span class="badge bg-secondary">${log.source}</span></td>
                    </tr>`;
                tbody.append(row);
            });

            const pagination = $("#pagination");
            pagination.empty();

            if (data.pagination.has_previous) {
                pagination.append(
                    `<li class="page-item"><a class="page-link" href="#" data-page="${
                        data.pagination.current_page - 1
                    }">&laquo;</a></li>`
                );
            }

            for (let i = 1; i <= data.pagination.num_pages; i++) {
                const active = i === data.pagination.current_page ? "active" : "";
                pagination.append(
                    `<li class="page-item ${active}" data-page="${i}"><a class="page-link" href="#">${i}</a></li>`
                );
            }

            if (data.pagination.has_next) {
                pagination.append(
                    `<li class="page-item"><a class="page-link" href="#" data-page="${
                        data.pagination.current_page + 1
                    }">&raquo;</a></li>`
                );
            }
        }).fail(function (jqXHR, textStatus, errorThrown) {
            console.error('Error AJAX:', textStatus, errorThrown);
            toastr.error('Error al cargar los logs.');
        });
    }

    // --- Eventos ---
    $("#refresh-btn").click(loadLogs);

    $("#auto-refresh-toggle").click(function () {
        autoRefresh = !autoRefresh;
        $(this).text("Auto: " + (autoRefresh ? "ON" : "OFF"));
        $(this).toggleClass("btn-outline-info btn-outline-danger");
        if (autoRefresh) {
            refreshInterval = setInterval(loadLogs, 30000);
        } else {
            clearInterval(refreshInterval);
        }
    });

    refreshInterval = setInterval(loadLogs, 30000);

    $("#filter-level, #filter-source, #search-input, #from-date, #to-date, #page-size").change(loadLogs);

    $(document).on("click", ".page-link", function (e) {
        e.preventDefault();
        $(".page-item").removeClass("active");
        $(this).parent().addClass("active");
        loadLogs();
    });

    // --- Cargar logs al inicio ---
    loadLogs();
});