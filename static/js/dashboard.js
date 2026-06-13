document.addEventListener('DOMContentLoaded', () => {
    console.log("CampusFix Dashboard Initialized.");

    // Auto-dismiss Flash Messages after 4 seconds
    const flashMessages = document.querySelectorAll('.max-w-4xl > div');
    
    if (flashMessages.length > 0) {
        setTimeout(() => {
            flashMessages.forEach(msg => {
                msg.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                msg.style.opacity = '0';
                msg.style.transform = 'translateY(-10px)';
                
                // Remove from DOM after fade out
                setTimeout(() => msg.remove(), 500);
            });
        }, 4000);
    }
});
