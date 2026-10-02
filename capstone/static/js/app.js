// Lightbox for photo previews
function openLightbox(src, caption) {
    const lb = document.getElementById('lightbox');
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox-caption').textContent = caption || '';
    lb.classList.add('open');
    document.body.style.overflow = 'hidden';
}
function closeLightbox() {
    const lb = document.getElementById('lightbox');
    lb.classList.remove('open');
    document.getElementById('lightbox-img').src = '';
    document.body.style.overflow = '';
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        closeLightbox();
    }
});
const lightbox = document.getElementById('lightbox');
if (lightbox) {
    lightbox.addEventListener('click', e => {
        if (e.target.id === 'lightbox') closeLightbox();
    });
}

// Loading state on submit buttons + auto-dismiss alerts
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', () => {
            const btn = form.querySelector('[data-loading]');
            if (btn && form.checkValidity()) {
                btn.classList.add('loading');
                btn.disabled = true;
            }
        });
    });
    document.querySelectorAll('.alert-success, .alert-info').forEach(a => {
        setTimeout(() => { a.style.transition = 'opacity .5s'; a.style.opacity = '0'; setTimeout(() => a.remove(), 500); }, 4500);
    });
});
