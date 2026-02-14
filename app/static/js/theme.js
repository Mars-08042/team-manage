/**
 * Theme Manager for GPT Team Management System
 * Handles theme switching and persistence
 */
class ThemeManager {
    constructor() {
        this.themeKey = 'gpt-team-theme';
        this.currentTheme = localStorage.getItem(this.themeKey) || 'light';
        this.init();
    }

    init() {
        // Apply saved theme on startup
        this.applyTheme(this.currentTheme);

        // Bind event listeners if toggle button exists
        const toggleBtn = document.getElementById('themeToggleBtn');
        if (toggleBtn) {
            this.updateButtonState(toggleBtn);
            toggleBtn.addEventListener('click', () => this.toggleTheme());
        }
    }

    toggleTheme() {
        this.currentTheme = this.currentTheme === 'light' ? 'cny' : 'light';
        this.applyTheme(this.currentTheme);
        localStorage.setItem(this.themeKey, this.currentTheme);

        const toggleBtn = document.getElementById('themeToggleBtn');
        if (toggleBtn) {
            this.updateButtonState(toggleBtn);
        }
    }

    applyTheme(theme) {
        if (theme === 'cny') {
            document.documentElement.setAttribute('data-theme', 'cny');
        } else {
            document.documentElement.removeAttribute('data-theme');
        }
    }

    updateButtonState(btn) {
        // Update button icon or text based on theme
        const iconSpan = btn.querySelector('.theme-icon');
        const textSpan = btn.querySelector('.theme-text');

        if (this.currentTheme === 'cny') {
            if (iconSpan) iconSpan.setAttribute('data-lucide', 'sun'); // Switch back to light
            if (textSpan) textSpan.textContent = '默认主题';
        } else {
            if (iconSpan) iconSpan.setAttribute('data-lucide', 'flower-2'); // Switch to CNY
            if (textSpan) textSpan.textContent = '新春主题';
        }

        // Refresh icons if lucide is available
        if (window.lucide) {
            window.lucide.createIcons();
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.themeManager = new ThemeManager();
    window.coupletManager = new CoupletManager();
});

/**
 * Couplet Manager
 * Handles the rotation of Chinese New Year couplet text
 */
class CoupletManager {
    constructor() {
        this.couplets = [
            { up: "春风入喜财入户", down: "岁月更新福满门" },
            { up: "天增岁月人增寿", down: "春满乾坤福满门" },
            { up: "一帆风顺年年好", down: "万事如意步步高" },
            { up: "和顺一门有百福", down: "平安二字值千金" },
            { up: "迎喜迎春迎富贵", down: "接财接福接平安" }
        ];
        this.currentIndex = 0;
        this.intervalId = null;
        this.init();
    }

    init() {
        // Start rotation only if theme is CNY
        this.checkThemeAndStart();

        // Listen for theme changes (dispatched by simple custom event or checking interval)
        // Since ThemeManager doesn't dispatch events yet, we can poll or expose a method.
        // For simplicity, we'll hook into the global window object or standard events if possible.
        // Here we'll just set an interval to check theme status occasionally or rely on page reload for now
        // But better: Let ThemeManager call us.

        // For now, let's start the interval. If hidden, it runs in background but invisible.
        // Optimization: Only run if visible.
        this.startRotation();
    }

    startRotation() {
        if (this.intervalId) return;

        // Rotate every 10 seconds
        this.intervalId = setInterval(() => {
            this.rotate();
        }, 10000);
    }

    rotate() {
        const leftEl = document.querySelector('#coupletLeft .couplet-text');
        const rightEl = document.querySelector('#coupletRight .couplet-text');
        const leftContainer = document.getElementById('coupletLeft');
        const rightContainer = document.getElementById('coupletRight');

        if (!leftEl || !rightEl) return;

        // 1. Add flipping class to trigger rotateY(90deg)
        leftContainer.classList.add('flipping');
        rightContainer.classList.add('flipping');

        // 2. Wait for half transition (0.4s), change text
        setTimeout(() => {
            this.currentIndex = (this.currentIndex + 1) % this.couplets.length;
            const nextCouplet = this.couplets[this.currentIndex];

            leftEl.textContent = nextCouplet.up;
            rightEl.textContent = nextCouplet.down;

        }, 400); // Half of 0.8s transition

        // 3. Remove flipping class to rotate back to 0deg
        setTimeout(() => {
            leftContainer.classList.remove('flipping');
            rightContainer.classList.remove('flipping');
        }, 800); // Full transition time
    }

    checkThemeAndStart() {
        // Logic to pause/resume based on theme could go here
    }
}
