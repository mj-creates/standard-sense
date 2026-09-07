/**
 * StandardSense — SIH 2026
 * app.js: UI interaction logic for persona selector & fake login
 * No backend. Pure MVP demo.
 */

// ─── State ──────────────────────────────────────────────────────────────────

let selectedRole = 'officer'; // 'officer' | 'vendor'

const ROLE_CONFIG = {
  officer: {
    label:       'GeM Nodal Officer',
    email:       'officer@nic.in',
    description: 'Access tender management, compliance reports & BIS standard mappings.',
    initials:    'NO',
    bannerTitle: 'GeM Nodal Officer Portal',
    welcome:     'Welcome to the GeM Nodal Officer Portal',
  },
  vendor: {
    label:       'MSME / OEM Vendor',
    email:       'vendor@msme.gov.in',
    description: 'Upload product specs, check BIS compliance status & manage certifications.',
    initials:    'MV',
    bannerTitle: 'MSME / OEM Vendor Portal',
    welcome:     'Welcome to the MSME / OEM Vendor Portal',
  },
};

// ─── Tab Switching ───────────────────────────────────────────────────────────

/**
 * Switch the active persona tab and update the email pre-fill.
 * @param {'officer'|'vendor'} role
 */
function selectTab(role) {
  selectedRole = role;

  const config      = ROLE_CONFIG[role];
  const tabOfficer  = document.getElementById('tab-officer');
  const tabVendor   = document.getElementById('tab-vendor');
  const emailInput  = document.getElementById('email-input');
  const roleDesc    = document.getElementById('role-description');

  // Toggle active/inactive classes
  if (role === 'officer') {
    tabOfficer.className = 'tab-active flex-1 py-3.5 px-4 text-sm font-semibold transition-all duration-200 flex items-center justify-center gap-2';
    tabVendor.className  = 'tab-inactive flex-1 py-3.5 px-4 text-sm font-semibold transition-all duration-200 flex items-center justify-center gap-2';
  } else {
    tabVendor.className  = 'tab-active flex-1 py-3.5 px-4 text-sm font-semibold transition-all duration-200 flex items-center justify-center gap-2';
    tabOfficer.className = 'tab-inactive flex-1 py-3.5 px-4 text-sm font-semibold transition-all duration-200 flex items-center justify-center gap-2';
  }

  // Update pre-filled email
  if (emailInput) emailInput.value = config.email;

  // Update role description banner
  if (roleDesc) roleDesc.textContent = config.description;
}

// ─── Fake Login ──────────────────────────────────────────────────────────────

/**
 * Handle form submission or SSO button click.
 * Bypasses all auth — simply flips from login to dashboard.
 * @param {Event} event
 */
function handleLogin(event) {
  event.preventDefault();

  const config        = ROLE_CONFIG[selectedRole];
  const loginPage     = document.getElementById('login-page');
  const dashboardPage = document.getElementById('dashboard-page');
  const dashTitle     = document.getElementById('dashboard-title');
  const bannerTitle   = document.getElementById('banner-title');
  const avatarEl      = document.getElementById('avatar-initials');
  const subtitleEl    = document.getElementById('dashboard-subtitle');
  const emailInput    = document.getElementById('email-input');

  // ── Simulate a brief loading state on the button ──
  const submitBtn = event.target.closest('button') || event.target.querySelector('button[type="submit"]');
  if (submitBtn) {
    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML = `
      <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
      </svg>
      Authenticating…
    `;
    submitBtn.disabled = true;

    setTimeout(() => {
      submitBtn.innerHTML = originalText;
      submitBtn.disabled  = false;
      _showDashboard(config, loginPage, dashboardPage, dashTitle, bannerTitle, avatarEl, subtitleEl, emailInput);
    }, 900);

    return;
  }

  _showDashboard(config, loginPage, dashboardPage, dashTitle, bannerTitle, avatarEl, subtitleEl, emailInput);
}

/**
 * Internal helper: swap visibility and populate dashboard values.
 */
function _showDashboard(config, loginPage, dashboardPage, dashTitle, bannerTitle, avatarEl, subtitleEl, emailInput) {
  // Populate dynamic content
  if (dashTitle)   dashTitle.textContent   = config.welcome;
  if (bannerTitle) bannerTitle.textContent = config.bannerTitle;
  if (avatarEl)    avatarEl.textContent    = config.initials;
  if (subtitleEl)  subtitleEl.textContent  = `${emailInput ? emailInput.value : config.email}  ·  Session active`;

  // Swap visibility
  loginPage.classList.add('hidden');
  loginPage.classList.remove('flex');

  dashboardPage.classList.remove('hidden');
  dashboardPage.classList.add('flex');

  // Scroll to top
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ─── Logout ──────────────────────────────────────────────────────────────────

/**
 * Return to the login screen.
 */
function handleLogout() {
  const loginPage     = document.getElementById('login-page');
  const dashboardPage = document.getElementById('dashboard-page');

  dashboardPage.classList.add('hidden');
  dashboardPage.classList.remove('flex');

  loginPage.classList.remove('hidden');
  loginPage.classList.add('flex');

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ─── Password Visibility Toggle ──────────────────────────────────────────────

/**
 * Toggle the password field between text and password type.
 */
function togglePassword() {
  const pwInput = document.getElementById('password-input');
  const eyeIcon = document.getElementById('eye-icon');

  if (!pwInput) return;

  if (pwInput.type === 'password') {
    pwInput.type = 'text';
    eyeIcon.innerHTML = `
      <path stroke-linecap="round" stroke-linejoin="round"
        d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7
           a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878
           l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59
           3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025
           10.025 0 01-4.132 5.411m0 0L21 21"/>
    `;
  } else {
    pwInput.type = 'password';
    eyeIcon.innerHTML = `
      <path stroke-linecap="round" stroke-linejoin="round"
        d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
      <path stroke-linecap="round" stroke-linejoin="round"
        d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943
           9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
    `;
  }
}

// ─── Keyboard Accessibility ──────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Allow Enter key on tab buttons to switch tabs
  ['tab-officer', 'tab-vendor'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.setAttribute('role', 'tab');
    el.setAttribute('tabindex', '0');
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        el.click();
      }
    });
  });
});
