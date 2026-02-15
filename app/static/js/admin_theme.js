/**
 * Theme Manager for GPT Team Management System
 * Handles theme switching and persistence
 */
class ThemeManager {
    constructor() {
        this.themeKey = 'gpt-team-theme';
        this.currentTheme = this.resolveInitialTheme();
        this.applyTheme(this.currentTheme);
        localStorage.setItem(this.themeKey, this.currentTheme);

        this.init();
    }

    resolveInitialTheme() {
        const toggleBtn = document.getElementById('themeToggleBtn');
        const buttonTheme = toggleBtn?.dataset?.currentTheme;
        const globalTheme = window.__GLOBAL_THEME__;
        const localTheme = localStorage.getItem(this.themeKey);
        return this.normalizeTheme(buttonTheme || globalTheme || localTheme);
    }

    normalizeTheme(theme) {
        return theme === 'cny' ? 'cny' : 'default';
    }

    init() {
        // Bind event listeners if toggle button exists
        const toggleBtn = document.getElementById('themeToggleBtn');
        if (toggleBtn) {
            this.updateButtonState(toggleBtn);
            toggleBtn.addEventListener('click', () => {
                this.toggleTheme();
            });
        }
    }

    async toggleTheme() {
        const toggleBtn = document.getElementById('themeToggleBtn');
        const nextTheme = this.currentTheme === 'cny' ? 'default' : 'cny';

        if (toggleBtn) {
            toggleBtn.disabled = true;
        }

        try {
            await this.persistTheme(nextTheme);
            this.currentTheme = nextTheme;
            this.applyTheme(this.currentTheme);
            localStorage.setItem(this.themeKey, this.currentTheme);

            if (toggleBtn) {
                toggleBtn.dataset.currentTheme = this.currentTheme;
                this.updateButtonState(toggleBtn);
            }

            if (typeof window.showToast === 'function') {
                const themeName = this.currentTheme === 'cny' ? '新春主题' : '默认主题';
                window.showToast(`已切换为${themeName}`, 'success');
            }
        } catch (error) {
            if (typeof window.showToast === 'function') {
                window.showToast(error.message || '主题更新失败', 'error');
            }
        } finally {
            if (toggleBtn) {
                toggleBtn.disabled = false;
            }
        }

        // Notify CoupletManager to check visibility
        if (window.coupletManager) {
            window.coupletManager.checkThemeAndStart();
        }
    }

    async persistTheme(theme) {
        const response = await fetch('/admin/settings/theme', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ theme: theme })
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
            throw new Error(data.error || '主题更新失败');
        }
    }

    applyTheme(theme) {
        if (this.normalizeTheme(theme) === 'cny') {
            document.documentElement.setAttribute('data-theme', 'cny');
            // Ensure icons are refreshed if changed
            if (window.lucide) window.lucide.createIcons();
        } else {
            document.documentElement.removeAttribute('data-theme');
            if (window.lucide) window.lucide.createIcons();
        }
    }

    updateButtonState(btn) {
        // Update button icon or text based on theme
        // Structure expected: <button> <i data-lucide="..."></i> <span>Text</span> </button>
        let iconName = this.currentTheme === 'cny' ? 'sun' : 'flower-2';
        // User request: In CNY theme, display "新春主题" (Current State), not "默认主题" (Action)
        let text = this.currentTheme === 'cny' ? '新春主题' : '默认主题';

        // Re-construct button content to ensure lucide can re-process
        btn.innerHTML = `<i data-lucide="${iconName}" style="width: 16px; height: 16px; margin-right: 0.5rem;"></i><span class="theme-text">${text}</span>`;

        if (window.lucide) {
            window.lucide.createIcons();
        }
    }
}

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
        this.checkThemeAndStart();
    }

    checkThemeAndStart() {
        const isCNY = document.documentElement.getAttribute('data-theme') === 'cny';
        if (isCNY) {
            this.startRotation();
        } else {
            this.stopRotation();
        }
    }

    startRotation() {
        if (this.intervalId) return;

        // Rotate every 10 seconds
        this.intervalId = setInterval(() => {
            this.rotate();
        }, 10000);
    }

    stopRotation() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }

    rotate() {
        // Only run if elements exist
        const leftEl = document.querySelector('#coupletLeft .couplet-text');
        const rightEl = document.querySelector('#coupletRight .couplet-text');
        const leftContainer = document.getElementById('coupletLeft');
        const rightContainer = document.getElementById('coupletRight');

        if (!leftEl || !rightEl || !leftContainer || !rightContainer) return;

        // Only rotate if visible
        if (window.getComputedStyle(leftContainer).display === 'none') return;

        // 1. Add flipping class to trigger rotateY(90deg)
        leftContainer.classList.add('flipping');
        rightContainer.classList.add('flipping');

        // 2. Wait for half transition (0.4s), change text
        setTimeout(() => {
            this.currentIndex = (this.currentIndex + 1) % this.couplets.length;
            const nextCouplet = this.couplets[this.currentIndex];

            leftEl.textContent = nextCouplet.up;
            rightEl.textContent = nextCouplet.down;

        }, 400); // Admin theme transition is usually 0.8s total

        // 3. Remove flipping class to rotate back to 0deg
        setTimeout(() => {
            leftContainer.classList.remove('flipping');
            rightContainer.classList.remove('flipping');
        }, 800); // Full transition time
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.themeManager = new ThemeManager();
    window.coupletManager = new CoupletManager();
});
