// web_interface/static/web_interface/js/dashboard.js

document.addEventListener('DOMContentLoaded', function () {
    const ctx = document.getElementById('activityChart')?.getContext('2d');
    if (!ctx) return;

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'],
            datasets: [{
                label: 'Actividad Diaria',
                data: [12, 19, 15, 23, 18, 14, 20],
                borderColor: '#007bff',
                backgroundColor: 'rgba(0, 123, 255, 0.1)',
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { stepSize: 5 }
                }
            }
        }
    });
});
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const btn = document.querySelector('.toggle-btn');

    sidebar.classList.toggle('collapsed');

    // Cambiar flecha
    if (sidebar.classList.contains('collapsed')) {
        btn.innerHTML = '<i class="fas fa-chevron-right"></i>';
    } else {
        btn.innerHTML = '<i class="fas fa-chevron-left"></i>';
    }
}