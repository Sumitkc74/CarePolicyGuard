let currentToken = null;
let currentRole = "Auditor";
let currentUser = "auditor@medicare.cms.gov";
let selectedDemoRole = "auditor";
let clinicalPresets = [];
let lastAdjudicationResult = null;
let cachedPoliciesList = [];
let currentCoveragePacket = null;

// Demo credentials
// Demo credentials
const DEMO_CREDENTIALS = {
    clinician: { username: "clinician@hospital.org", password: "ClinicianCare!2026", role: "Clinician" },
    auditor: { username: "auditor@medicare.cms.gov", password: "AuditorSecure!2026", role: "Auditor" },
    admin: { username: "admin@carepolicyguard.med", password: "AdminGuard!2026", role: "Admin" }
};

document.addEventListener("DOMContentLoaded", async () => {
    await checkSessionOrShowGate();
    setupUploadDropzone();
    updateWorkflowRibbon(1);
    initHipaaInactivityWatcher();
});

// =============================================================================
// NAVIGATION & TABS
// =============================================================================
function switchMainTab(tabName) {
    document.querySelectorAll(".nav-btn").forEach(btn => btn.classList.remove("active"));
    document.querySelectorAll(".view-panel").forEach(panel => panel.classList.remove("active"));

    if (tabName === "adjudicate") {
        document.getElementById("tab-adjudicate-btn").classList.add("active");
        document.getElementById("adjudicate-view").classList.add("active");
    } else if (tabName === "audit") {
        document.getElementById("tab-audit-btn").classList.add("active");
        document.getElementById("audit-view").classList.add("active");
        loadAuditLogs();
    } else if (tabName === "batch") {
        const batchBtn = document.getElementById("tab-batch-btn");
        if (batchBtn) batchBtn.classList.add("active");
        const batchView = document.getElementById("batch-view");
        if (batchView) batchView.classList.add("active");
        if (!window._activeBatchLoaded) {
            loadSampleBatchRoster('cardiology');
        }
    } else if (tabName === "benchmark") {
        document.getElementById("tab-benchmark-btn").classList.add("active");
        document.getElementById("benchmark-view").classList.add("active");
        runLiveBenchmark();
    } else if (tabName === "crd") {
        const btn = document.getElementById("tab-crd-btn");
        if (btn) btn.classList.add("active");
        const view = document.getElementById("crd-view");
        if (view) view.classList.add("active");
        initCrdSimulator();
    } else if (tabName === "telemetry") {
        const btn = document.getElementById("tab-telemetry-btn");
        if (btn) btn.classList.add("active");
        const view = document.getElementById("telemetry-view");
        if (view) view.classList.add("active");
        loadLiveTelemetry();
    }
}

// =============================================================================
// AUTHENTICATION, LOGIN GATE & RBAC
// =============================================================================

async function checkSessionOrShowGate() {
    const savedToken = sessionStorage.getItem("carepolicyguard_token");
    const savedRole = sessionStorage.getItem("carepolicyguard_role");
    const savedUser = sessionStorage.getItem("carepolicyguard_user");

    if (savedToken) {
        currentToken = savedToken;
        currentRole = savedRole || "Clinician";
        currentUser = savedUser || "clinician@hospital.org";
        hideLoginGate();
        updateUserBadge();
        await loadPolicies();
        await loadPresets();
        await loadAuditLogs();
    } else {
        showLoginGate();
    }
}

function showLoginGate() {
    const gate = document.getElementById("login-gate-screen");
    if (gate) gate.classList.remove("hidden");
}

function hideLoginGate() {
    const gate = document.getElementById("login-gate-screen");
    if (gate) gate.classList.add("hidden");
}

function switchLoginMode(mode) {
    const signinBtn = document.getElementById("btn-tab-signin");
    const registerBtn = document.getElementById("btn-tab-register-pro");
    const signinSec = document.getElementById("login-section-signin");
    const registerSec = document.getElementById("login-section-register");

    [signinBtn, registerBtn].forEach(b => b && b.classList.remove("active"));
    [signinSec, registerSec].forEach(s => s && s.classList.add("hidden"));

    if (mode === "register") {
        if (registerBtn) registerBtn.classList.add("active");
        if (registerSec) registerSec.classList.remove("hidden");
    } else {
        if (signinBtn) signinBtn.classList.add("active");
        if (signinSec) signinSec.classList.remove("hidden");
    }
}

function autofillLogin(email, password) {
    const uInput = document.getElementById("login-username-input");
    const pInput = document.getElementById("login-password-input");
    if (uInput) uInput.value = email;
    if (pInput) pInput.value = password;
    showToast(`Autofilled credentials for ${email}. Click "Sign In & Authenticate" to verify.`);
}

// Client-Side CMS Luhn Checksum for NPI (Prefix 80840)
function validateNpiLuhnClient(npi) {
    if (!npi || npi.length !== 10 || !/^\d+$/.test(npi)) return false;
    if (npi[0] !== '1' && npi[0] !== '2') return false;
    const fullStr = '80840' + npi;
    let checksum = 0;
    for (let i = 0; i < fullStr.length; i++) {
        let d = parseInt(fullStr[fullStr.length - 1 - i], 10);
        if (i % 2 === 1) {
            d *= 2;
            if (d > 9) d -= 9;
        }
        checksum += d;
    }
    return checksum % 10 === 0;
}

function handleNpiInputLive(val) {
    const badge = document.getElementById("npi-live-badge");
    if (!badge) return;
    const clean = (val || "").trim();
    if (clean.length === 0) {
        badge.textContent = "10 Digits";
        badge.className = "npi-status-badge";
        return;
    }
    if (clean.length < 10) {
        badge.textContent = `${clean.length}/10 Digits`;
        badge.className = "npi-status-badge";
        return;
    }
    if (clean.length === 10) {
        if (validateNpiLuhnClient(clean)) {
            badge.textContent = " Valid CMS NPI";
            badge.className = "npi-status-badge valid";
        } else {
            badge.textContent = " Invalid NPI Checksum";
            badge.className = "npi-status-badge invalid";
        }
    }
}

function handleEmailInputLive(val) {
    const hint = document.getElementById("email-live-hint");
    if (!hint) return;
    const email = (val || "").trim().toLowerCase();
    const disallowed = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com", "mail.com", "protonmail.com"];
    const domain = email.split("@")[1] || "";
    
    if (disallowed.includes(domain)) {
        hint.className = "field-feedback-hint error";
        hint.innerHTML = `<span class="med-icon icon-xs"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg></span><span>Personal email prohibited under HIPAA. Use hospital or institutional email.</span>`;
    } else if (email.includes("@") && email.includes(".") && domain.length > 3) {
        hint.className = "field-feedback-hint success";
        hint.innerHTML = `<span class="med-icon icon-xs"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg></span><span>Institutional domain recognized.</span>`;
    } else {
        hint.className = "field-feedback-hint";
        hint.innerHTML = `<span class="med-icon icon-xs"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg></span><span>Hospital/health system email required. Personal webmail (@gmail, @yahoo) prohibited under HIPAA.</span>`;
    }
}

async function handleMedicalRegistration(event) {
    event.preventDefault();
    const errorBox = document.getElementById("reg-error-box");
    if (errorBox) errorBox.classList.add("hidden");

    const fullname = document.getElementById("reg-fullname")?.value.trim() || "";
    const credential = document.getElementById("reg-credential")?.value || "MD";
    const email = document.getElementById("reg-email")?.value.trim() || "";
    const npi = document.getElementById("reg-npi")?.value.trim() || "";
    const licenseState = document.getElementById("reg-license-state")?.value || "CA";
    const licenseNum = document.getElementById("reg-license-num")?.value.trim() || "";
    const specialty = document.getElementById("reg-specialty")?.value.trim() || "";
    const organization = document.getElementById("reg-organization")?.value.trim() || "";
    const password = document.getElementById("reg-password")?.value || "";
    const attestation = document.getElementById("reg-attestation-check")?.checked;

    if (!attestation) {
        showToast("You must solemnly attest to your medical licensure status.", true);
        return;
    }

    if (!validateNpiLuhnClient(npi)) {
        if (errorBox) {
            errorBox.innerHTML = `<strong>NPI Checksum Error:</strong> National Provider Identifier '${npi}' failed CMS standard Luhn validation. Please provide an authentic 10-digit NPI number.`;
            errorBox.classList.remove("hidden");
        }
        showToast("Invalid NPI: Check digit checksum failure.", true);
        return;
    }

    const submitBtn = document.getElementById("btn-reg-pro-submit");
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `Verifying Medical Credentials with NPPES/CMS...`;
    }

    try {
        const payload = {
            username: email,
            email: email,
            password: password,
            role: "Clinician",
            full_name: fullname,
            credential_title: credential,
            npi_number: npi,
            license_state: licenseState,
            medical_license: licenseNum,
            specialty: specialty,
            organization: organization
        };

        const res = await fetch("/api/v1/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            showToast(`Medical credentials verified! Logging in as ${fullname}...`);
            // Automatically log in
            await executeLogin(email, password);
        } else {
            const errData = await res.json().catch(() => ({}));
            let errMsg = errData.detail?.message || errData.detail || "Medical professional registration failed.";
            if (errData.detail?.reasons && errData.detail.reasons.length > 0) {
                errMsg += "<br><ul style='margin: 6px 0 0 16px; padding: 0;'>" + errData.detail.reasons.map(r => `<li>${r}</li>`).join("") + "</ul>";
            }
            if (errorBox) {
                errorBox.innerHTML = `<strong>Verification Denied:</strong> ${errMsg}`;
                errorBox.classList.remove("hidden");
            }
            showToast("Medical registration rejected: Please verify credentials.", true);
        }
    } catch (e) {
        showToast("Registration network error: " + e.message, true);
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = `<span class="med-icon icon-sm"><svg viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7.5" r="4"></circle><polyline points="17 11 19 13 23 9"></polyline></svg></span> Verify Credentials &amp; Register Account`;
        }
    }
}



async function handleCustomLogin(event) {
    event.preventDefault();
    const uInput = document.getElementById("login-username-input");
    const pInput = document.getElementById("login-password-input");
    const username = uInput ? uInput.value.trim() : "";
    const password = pInput ? pInput.value : "";

    if (!username || !password) {
        showToast("Please provide both username and password.", true);
        return;
    }

    const submitBtn = document.getElementById("btn-custom-login-submit");
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `Verifying credentials...`;
    }

    try {
        await executeLogin(username, password);
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = `Authenticate Credentials`;
        }
    }
}

async function triggerGoogleSignIn() {
    const btn = document.getElementById("btn-oauth-google");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Connecting...";
    }

    try {
        const cfgRes = await fetch("/api/v1/auth/oauth/config");
        const cfg = cfgRes.ok ? await cfgRes.json() : {};

        let credential = null;
        if (cfg.google_enabled && window.google && window.google.accounts) {
            // Live GIS invocation if client ID configured and library loaded
        } else {
            const promptEmail = prompt(
                "Sign in with Google (Evaluation Sandbox)\nEnter clinician Google Workspace email:",
                "dr.smith@pacificheart.org"
            );
            if (!promptEmail) return;
            credential = `mock_google_${promptEmail.trim()}`;
        }

        const res = await fetch("/api/v1/auth/oauth/google", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ credential })
        });

        const data = await res.json();
        if (res.ok) {
            if (data.status === "MFA_CHALLENGE_REQUIRED") {
                window._mfaSessionToken = data.mfa_session_token;
                window._mfaAvailableMethods = data.available_methods || [data.mfa_method];
                window._selectedMfaMethod = data.mfa_method;

                const signinSection = document.getElementById("login-section-signin");
                const mfaSection = document.getElementById("login-section-mfa");
                if (signinSection) signinSection.classList.add("hidden");
                if (mfaSection) mfaSection.classList.remove("hidden");

                renderMfaFactorSelectionButtons();
                updateMfaChallengeCardUI(data);
                showToast("Google authentication verified. Complete clinical two-factor challenge.");
                return;
            }

            currentToken = data.access_token;
            currentRole = data.role;
            currentUser = data.username;

            sessionStorage.setItem("carepolicyguard_token", currentToken);
            sessionStorage.setItem("carepolicyguard_role", currentRole);
            sessionStorage.setItem("carepolicyguard_user", currentUser);

            updateUserBadge();
            hideLoginGate();
            showToast(`Welcome! Authenticated via Google (${currentUser})`);

            await loadPolicies();
            await loadPresets();
            await loadAuditLogs();
        } else {
            showToast(data.detail || "Google authentication failed.", true);
        }
    } catch (e) {
        showToast("Google SSO connection error: " + e.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/></svg> Google`;
        }
    }
}

async function triggerAppleSignIn() {
    const btn = document.getElementById("btn-oauth-apple");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Connecting...";
    }

    try {
        const promptEmail = prompt(
            "Sign in with Apple (Evaluation Sandbox)\nEnter clinician Apple ID or private relay email:",
            "dr.jones@hospital.org"
        );
        if (!promptEmail) return;
        const id_token = `mock_apple_${promptEmail.trim()}`;

        const res = await fetch("/api/v1/auth/oauth/apple", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id_token })
        });

        const data = await res.json();
        if (res.ok) {
            if (data.status === "MFA_CHALLENGE_REQUIRED") {
                window._mfaSessionToken = data.mfa_session_token;
                window._mfaAvailableMethods = data.available_methods || [data.mfa_method];
                window._selectedMfaMethod = data.mfa_method;

                const signinSection = document.getElementById("login-section-signin");
                const mfaSection = document.getElementById("login-section-mfa");
                if (signinSection) signinSection.classList.add("hidden");
                if (mfaSection) mfaSection.classList.remove("hidden");

                renderMfaFactorSelectionButtons();
                updateMfaChallengeCardUI(data);
                showToast("Apple authentication verified. Complete clinical two-factor challenge.");
                return;
            }

            currentToken = data.access_token;
            currentRole = data.role;
            currentUser = data.username;

            sessionStorage.setItem("carepolicyguard_token", currentToken);
            sessionStorage.setItem("carepolicyguard_role", currentRole);
            sessionStorage.setItem("carepolicyguard_user", currentUser);

            updateUserBadge();
            hideLoginGate();
            showToast(`Welcome! Authenticated via Apple (${currentUser})`);

            await loadPolicies();
            await loadPresets();
            await loadAuditLogs();
        } else {
            showToast(data.detail || "Apple authentication failed.", true);
        }
    } catch (e) {
        showToast("Apple SSO connection error: " + e.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="#ffffff"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M15.97 6.84c.62-.75 1.04-1.79.92-2.84-.89.04-1.98.6-2.61 1.34-.56.64-.99 1.7-1.01 2.76.99.08 2.08-.51 2.7-1.26"/></svg> Apple`;
        }
    }
}

async function executeLogin(username, password) {
    try {
        const res = await fetch("/api/v1/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });

        if (res.ok) {
            const data = await res.json();

            // Check for Two-Factor Authentication challenge
            if (data.status === "MFA_CHALLENGE_REQUIRED") {
                window._mfaSessionToken = data.mfa_session_token;
                window._mfaAvailableMethods = data.available_methods || [data.mfa_method];
                window._selectedMfaMethod = data.mfa_method;

                const signinSection = document.getElementById("login-section-signin");
                const mfaSection = document.getElementById("login-section-mfa");
                if (signinSection) signinSection.classList.add("hidden");
                if (mfaSection) mfaSection.classList.remove("hidden");

                renderMfaFactorSelectionButtons();
                updateMfaChallengeCardUI(data);

                showToast(`Two-factor authentication required for ${username}.`);
                return;
            }

            currentToken = data.access_token;
            currentRole = data.role;
            currentUser = data.username;

            sessionStorage.setItem("carepolicyguard_token", currentToken);
            sessionStorage.setItem("carepolicyguard_role", currentRole);
            sessionStorage.setItem("carepolicyguard_user", currentUser);

            updateUserBadge();
            hideLoginGate();
            showToast(`Welcome! Authenticated as ${currentRole} (${currentUser})`);

            await loadPolicies();
            await loadPresets();
            await loadAuditLogs();
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || "Invalid credentials. Please verify username and password.", true);
        }
    } catch (e) {
        showToast("Authentication connection error: " + e.message, true);
    }
}

function signOutToLoginGate() {
    currentToken = null;
    currentRole = "Not Authenticated";
    currentUser = "--";
    sessionStorage.removeItem("carepolicyguard_token");
    sessionStorage.removeItem("carepolicyguard_role");
    sessionStorage.removeItem("carepolicyguard_user");

    const authModal = document.getElementById("auth-modal");
    if (authModal) authModal.classList.add("hidden");

    showLoginGate();
    showToast("Signed out successfully. Authentication required to continue.");
}

function updateUserBadge() {
    const roleLabel = document.getElementById("user-role-label");
    const nameLabel = document.getElementById("user-name-label");
    if (roleLabel) roleLabel.textContent = currentRole;
    if (nameLabel) nameLabel.textContent = currentUser;

    const modalUser = document.getElementById("modal-profile-user");
    const modalRole = document.getElementById("modal-profile-role");
    const modalAuth = document.getElementById("modal-profile-authority");
    if (modalUser) modalUser.textContent = currentUser;
    if (modalRole) modalRole.textContent = currentRole;
    if (modalAuth) {
        if (currentRole === "Clinician") {
            modalAuth.textContent = "Full Prior-Auth Creation & Signing";
            modalAuth.className = "profile-v text-emerald";
        } else if (currentRole === "Admin") {
            modalAuth.textContent = "Full System & Audit Administration";
            modalAuth.className = "profile-v text-cyan";
        } else {
            modalAuth.textContent = "Read-Only Compliance & Ledger Inspection";
            modalAuth.className = "profile-v text-amber";
        }
    }

    const auditorNotice = document.getElementById("auditor-mode-notice");
    if (auditorNotice) {
        if (currentRole === "Auditor") {
            auditorNotice.classList.remove("hidden");
        } else {
            auditorNotice.classList.add("hidden");
        }
    }
}

function renderMfaFactorSelectionButtons() {
    const container = document.getElementById("mfa-factor-selection-container");
    const row = document.getElementById("mfa-factor-buttons-row");
    if (!container || !row) return;

    if (!window._mfaAvailableMethods || window._mfaAvailableMethods.length <= 1) {
        container.classList.add("hidden");
        return;
    }

    container.classList.remove("hidden");
    row.innerHTML = "";

    const methodLabels = {
        "totp_app": "Authenticator App",
        "email_otp": "Email Code",
        "sms_otp": "SMS Code"
    };

    window._mfaAvailableMethods.forEach(method => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn-side-tutorial";
        const isSelected = method === window._selectedMfaMethod;
        btn.style.cssText = `padding: 4px 10px; font-size: 11px; border-radius: 4px; ${isSelected ? "background: #38bdf8; color: #0f172a; font-weight: 700; border-color: #38bdf8;" : "background: #1e293b; color: #cbd5e1; border-color: #475569;"}`;
        btn.textContent = methodLabels[method] || method;
        btn.onclick = () => switchMfaChallengeMethod(method);
        row.appendChild(btn);
    });
}

async function switchMfaChallengeMethod(method) {
    if (!window._mfaSessionToken) return;
    try {
        const res = await fetch("/api/v1/auth/mfa/challenge-method", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                mfa_session_token: window._mfaSessionToken,
                requested_method: method
            })
        });
        if (res.ok) {
            const data = await res.json();
            window._selectedMfaMethod = method;
            renderMfaFactorSelectionButtons();
            updateMfaChallengeCardUI(data);
            showToast(`Switched factor to ${method === 'totp_app' ? 'Authenticator App' : (method === 'email_otp' ? 'Email OTP' : 'SMS OTP')}.`);
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || "Failed to switch verification method.", true);
        }
    } catch (e) {
        showToast("Connection error switching factor: " + e.message, true);
    }
}

function updateMfaChallengeCardUI(data) {
    const subtitle = document.getElementById("mfa-challenge-subtitle");
    const destText = document.getElementById("mfa-destination-text");
    const codeInput = document.getElementById("mfa-code-input");
    const devHintBox = document.getElementById("mfa-dev-hint-box");
    const autofillBtn = document.getElementById("btn-autofill-mfa-code");

    const method = data.mfa_method || window._selectedMfaMethod;

    if (method === "totp_app") {
        if (subtitle) subtitle.textContent = "Authenticator App Verification";
        if (destText) destText.textContent = "Open Google Authenticator, Microsoft Authenticator, or Duo and enter the 6-digit code.";
    } else if (method === "email_otp") {
        if (subtitle) subtitle.textContent = "Email Verification Code";
        if (destText) destText.textContent = `A 6-digit verification code was emailed to ${data.destination_masked || "your registered address"}.`;
    } else if (method === "sms_otp") {
        if (subtitle) subtitle.textContent = "SMS Security Code";
        if (destText) destText.textContent = `A 6-digit verification code was sent via SMS to ${data.destination_masked || "your mobile device"}.`;
    }

    if (data.dev_preview_code && devHintBox && autofillBtn) {
        devHintBox.classList.remove("hidden");
        autofillBtn.textContent = `Autofill Security Code: ${data.dev_preview_code}`;
        autofillBtn.onclick = () => {
            if (codeInput) {
                codeInput.value = data.dev_preview_code;
                codeInput.focus();
            }
        };
    } else if (devHintBox) {
        devHintBox.classList.add("hidden");
    }

    if (codeInput) {
        codeInput.value = "";
        setTimeout(() => codeInput.focus(), 150);
    }
}

function toggleAuthModal() {
    const modal = document.getElementById("auth-modal");
    if (modal) {
        modal.classList.toggle("hidden");
        if (!modal.classList.contains("hidden")) {
            loadAuthModalSecurityDetails();
        }
    }
}

async function handleMfaChallengeSubmit(event) {
    if (event) event.preventDefault();
    const codeInput = document.getElementById("mfa-code-input");
    const submitBtn = document.getElementById("btn-mfa-submit");
    const code = codeInput ? codeInput.value.trim() : "";

    if (!code || code.length !== 6) {
        showToast("Please enter a valid 6-digit security code.", true);
        return;
    }

    if (!window._mfaSessionToken) {
        showToast("MFA session expired. Please sign in again.", true);
        cancelMfaChallenge();
        return;
    }

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Verifying security code...";
    }

    try {
        const res = await fetch("/api/v1/auth/mfa/verify-login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                mfa_session_token: window._mfaSessionToken,
                verification_code: code,
                mfa_method: window._selectedMfaMethod
            })
        });

        if (res.ok) {
            const data = await res.json();
            window._mfaSessionToken = null;
            currentToken = data.access_token;
            currentRole = data.role;
            currentUser = data.username;

            sessionStorage.setItem("carepolicyguard_token", currentToken);
            sessionStorage.setItem("carepolicyguard_role", currentRole);
            sessionStorage.setItem("carepolicyguard_user", currentUser);

            updateUserBadge();
            hideLoginGate();
            showToast(`Two-factor verification successful. Authenticated as ${currentRole} (${currentUser})`);

            await loadPolicies();
            await loadPresets();
            await loadAuditLogs();
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || "Invalid or expired verification code.", true);
            if (codeInput) {
                codeInput.select();
                codeInput.focus();
            }
        }
    } catch (e) {
        showToast("Verification failed: " + e.message, true);
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = "Verify Code & Access Chart System";
        }
    }
}

function cancelMfaChallenge() {
    window._mfaSessionToken = null;
    const signinSection = document.getElementById("login-section-signin");
    const mfaSection = document.getElementById("login-section-mfa");
    if (mfaSection) mfaSection.classList.add("hidden");
    if (signinSection) signinSection.classList.remove("hidden");
}

async function loadAuthModalSecurityDetails() {
    if (!currentToken) return;

    try {
        const res = await fetch("/api/v1/auth/mfa/status", {
            headers: { "Authorization": `Bearer ${currentToken}` }
        });
        if (res.ok) {
            const data = await res.json();
            const badge = document.getElementById("modal-profile-mfa-badge");
            const tag = document.getElementById("mfa-current-status-tag");
            const disableBtn = document.getElementById("btn-disable-mfa");

            const enabledMethods = data.enabled_methods || [data.mfa_method || "email_otp"];
            const methodCount = enabledMethods.length;
            const primaryLabel = data.primary_method === "totp_app" ? "Authenticator App" : (data.primary_method === "email_otp" ? "Email OTP" : "SMS OTP");
            
            if (badge) {
                badge.innerHTML = `<span class="text-emerald">Active (${methodCount} Configured - Primary: ${primaryLabel})</span>`;
            }
            if (tag) {
                tag.textContent = `${methodCount} Factor${methodCount > 1 ? "s" : ""} Active`;
                tag.style.background = "rgba(16, 185, 129, 0.2)";
                tag.style.color = "#34d399";
            }

            const listContainer = document.getElementById("mfa-factors-list-container");
            if (listContainer) {
                listContainer.innerHTML = "";
                const allFactors = [
                    { id: "email_otp", name: "Email One-Time Password", desc: data.email || "Registered Clinical Email" },
                    { id: "totp_app", name: "Authenticator App (TOTP RFC 6238)", desc: data.totp_configured ? "Google / Microsoft Authenticator Configured" : "Not configured" },
                    { id: "sms_otp", name: "SMS Mobile Number OTP", desc: data.phone_number || "No mobile phone configured" }
                ];

                allFactors.forEach(factor => {
                    const isEnabled = enabledMethods.includes(factor.id);
                    const row = document.createElement("div");
                    row.style.cssText = "display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #0f172a; border: 1px solid #334155; border-radius: 4px; font-size: 11px;";

                    const info = document.createElement("div");
                    info.innerHTML = `<div><strong>${factor.name}</strong> <span style="color: ${isEnabled ? "#34d399" : "#94a3b8"}; margin-left: 4px; font-weight: 600;">[${isEnabled ? "Active" : "Inactive"}]</span></div><div style="font-size: 10px; color: #94a3b8;">${factor.desc}</div>`;
                    row.appendChild(info);

                    if (isEnabled && enabledMethods.length > 1) {
                        const rmBtn = document.createElement("button");
                        rmBtn.type = "button";
                        rmBtn.className = "btn-side-tutorial";
                        rmBtn.style.cssText = "padding: 3px 8px; font-size: 10px; color: #f87171; border-color: #7f1d1d;";
                        rmBtn.textContent = "Remove";
                        rmBtn.onclick = () => removeMfaMethod(factor.id);
                        row.appendChild(rmBtn);
                    } else if (isEnabled) {
                        const reqSpan = document.createElement("span");
                        reqSpan.style.cssText = "font-size: 10px; color: #64748b; font-style: italic;";
                        reqSpan.textContent = "(Required Factor)";
                        row.appendChild(reqSpan);
                    }
                    listContainer.appendChild(row);
                });
            }
        }
    } catch (e) {
        console.error("Failed to load MFA status:", e);
    }

    await loadUserSessionsList();
}

async function loadUserSessionsList() {
    if (!currentToken) return;
    const container = document.getElementById("active-sessions-list-container");
    if (!container) return;

    try {
        const res = await fetch("/api/v1/auth/sessions", {
            headers: { "Authorization": `Bearer ${currentToken}` }
        });
        if (res.ok) {
            const sessions = await res.json();
            if (!sessions || sessions.length === 0) {
                container.innerHTML = '<div style="font-size: 11px; color: #94a3b8;">No active sessions found.</div>';
                return;
            }

            container.innerHTML = "";
            sessions.forEach(s => {
                const row = document.createElement("div");
                row.style.cssText = "display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #0f172a; border: 1px solid #334155; border-radius: 4px; font-size: 11px;";

                const info = document.createElement("div");
                const currentBadge = s.is_current ? '<span style="color: #38bdf8; font-weight: 700; margin-left: 4px;">[Current Session]</span>' : '';
                info.innerHTML = `<div><strong>${s.device_name || "Web Client"}</strong> ${currentBadge}</div><div style="color: #94a3b8; font-size: 10px;">IP: ${s.ip_address || "Unknown"} &bull; Last active: ${new Date(s.last_active_at).toLocaleTimeString()}</div>`;

                row.appendChild(info);

                if (!s.is_current && !s.is_revoked) {
                    const revokeBtn = document.createElement("button");
                    revokeBtn.type = "button";
                    revokeBtn.className = "btn-side-tutorial";
                    revokeBtn.style.cssText = "padding: 3px 8px; font-size: 10px; color: #f87171; border-color: #7f1d1d;";
                    revokeBtn.textContent = "Sign Out Device";
                    revokeBtn.onclick = () => revokeRemoteSession(s.session_id);
                    row.appendChild(revokeBtn);
                }

                container.appendChild(row);
            });
        }
    } catch (e) {
        console.error("Failed to fetch sessions:", e);
    }
}

async function revokeRemoteSession(sessionId) {
    if (!confirm("Are you sure you want to sign out this remote device session?")) return;
    try {
        const res = await fetch(`/api/v1/auth/sessions/${sessionId}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${currentToken}` }
        });
        if (res.ok) {
            showToast("Remote device session revoked immediately.");
            await loadUserSessionsList();
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || "Failed to revoke session.", true);
        }
    } catch (e) {
        showToast("Session revocation error: " + e.message, true);
    }
}

async function openTotpSetup() {
    if (!currentToken) return;
    const box = document.getElementById("totp-setup-box");
    const emailBox = document.getElementById("email-setup-box");
    if (emailBox) emailBox.classList.add("hidden");

    try {
        const res = await fetch("/api/v1/auth/mfa/setup?method=totp_app", {
            method: "POST",
            headers: { "Authorization": `Bearer ${currentToken}` }
        });
        if (res.ok) {
            const data = await res.json();
            const qrImg = document.getElementById("totp-qr-img");
            const secretCode = document.getElementById("totp-manual-secret");
            if (qrImg) qrImg.src = data.channel_destination;
            if (secretCode) secretCode.textContent = data.totp_secret;
            if (box) box.classList.remove("hidden");
            const input = document.getElementById("totp-verify-code-input");
            if (input) {
                input.value = "";
                input.focus();
            }
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || "Failed to initiate Authenticator setup.", true);
        }
    } catch (e) {
        showToast("Setup connection error: " + e.message, true);
    }
}

async function confirmTotpActivation() {
    const input = document.getElementById("totp-verify-code-input");
    const code = input ? input.value.trim() : "";
    if (!code || code.length !== 6) {
        showToast("Please enter the 6-digit code from your Authenticator app.", true);
        return;
    }

    try {
        const res = await fetch("/api/v1/auth/mfa/enable", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${currentToken}`
            },
            body: JSON.stringify({
                mfa_method: "totp_app",
                verification_code: code
            })
        });

        if (res.ok) {
            showToast("Authenticator App MFA activated successfully.");
            const box = document.getElementById("totp-setup-box");
            if (box) box.classList.add("hidden");
            await loadAuthModalSecurityDetails();
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || "Invalid Authenticator code. Check device clock sync.", true);
        }
    } catch (e) {
        showToast("Activation error: " + e.message, true);
    }
}

async function enableEmailOtpMfa() {
    if (!currentToken) return;
    const box = document.getElementById("email-setup-box");
    const totpBox = document.getElementById("totp-setup-box");
    if (totpBox) totpBox.classList.add("hidden");

    try {
        const res = await fetch("/api/v1/auth/mfa/setup?method=email_otp", {
            method: "POST",
            headers: { "Authorization": `Bearer ${currentToken}` }
        });
        if (res.ok) {
            const data = await res.json();
            const hint = document.getElementById("email-otp-target-hint");
            let msg = `Verification code dispatched to ${data.channel_destination || "your email"}.`;
            if (data.dev_preview_code) {
                msg += ` (Evaluation Code: ${data.dev_preview_code})`;
            }
            if (hint) hint.textContent = msg;
            if (box) box.classList.remove("hidden");
            const input = document.getElementById("email-verify-code-input");
            if (input) {
                input.value = data.dev_preview_code || "";
                input.focus();
            }
            showToast("Verification code sent to your registered clinical email.");
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || "Failed to initiate email verification.", true);
        }
    } catch (e) {
        showToast("Email setup error: " + e.message, true);
    }
}

async function confirmEmailMfaActivation() {
    const input = document.getElementById("email-verify-code-input");
    const code = input ? input.value.trim() : "";
    if (!code || code.length !== 6) {
        showToast("Please enter the 6-digit verification code from your email.", true);
        return;
    }

    try {
        const res = await fetch("/api/v1/auth/mfa/enable", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${currentToken}`
            },
            body: JSON.stringify({
                mfa_method: "email_otp",
                verification_code: code
            })
        });

        if (res.ok) {
            showToast("Email One-Time Passcode MFA activated successfully.");
            const box = document.getElementById("email-setup-box");
            if (box) box.classList.add("hidden");
            await loadAuthModalSecurityDetails();
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || "Invalid or expired verification code.", true);
        }
    } catch (e) {
        showToast("Activation error: " + e.message, true);
    }
}

function openSmsSetup() {
    if (!currentToken) return;
    const box = document.getElementById("sms-setup-box");
    const totpBox = document.getElementById("totp-setup-box");
    const emailBox = document.getElementById("email-setup-box");
    if (totpBox) totpBox.classList.add("hidden");
    if (emailBox) emailBox.classList.add("hidden");
    if (box) box.classList.remove("hidden");
    const phoneInput = document.getElementById("sms-phone-input");
    if (phoneInput) phoneInput.focus();
}

async function requestSmsOtpCode() {
    if (!currentToken) return;
    const phoneInput = document.getElementById("sms-phone-input");
    const phone = phoneInput ? phoneInput.value.trim() : "";
    if (!phone) {
        showToast("Please enter a valid mobile phone number.", true);
        return;
    }

    try {
        const res = await fetch(`/api/v1/auth/mfa/setup?method=sms_otp&phone=${encodeURIComponent(phone)}`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${currentToken}` }
        });
        if (res.ok) {
            const data = await res.json();
            const hint = document.getElementById("sms-otp-target-hint");
            let msg = `Verification code sent to ${data.channel_destination}.`;
            if (data.dev_preview_code) {
                msg += ` (Evaluation Code: ${data.dev_preview_code})`;
            }
            if (hint) hint.textContent = msg;
            const verifyInput = document.getElementById("sms-verify-code-input");
            if (verifyInput) {
                verifyInput.value = data.dev_preview_code || "";
                verifyInput.focus();
            }
            showToast("SMS verification code sent.");
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || "Failed to send SMS code.", true);
        }
    } catch (e) {
        showToast("SMS request error: " + e.message, true);
    }
}

async function confirmSmsMfaActivation() {
    const input = document.getElementById("sms-verify-code-input");
    const phoneInput = document.getElementById("sms-phone-input");
    const code = input ? input.value.trim() : "";
    const phone = phoneInput ? phoneInput.value.trim() : null;

    if (!code || code.length !== 6) {
        showToast("Please enter the 6-digit verification code from your SMS.", true);
        return;
    }

    try {
        const res = await fetch("/api/v1/auth/mfa/enable", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${currentToken}`
            },
            body: JSON.stringify({
                mfa_method: "sms_otp",
                verification_code: code,
                phone_number: phone
            })
        });

        if (res.ok) {
            showToast("SMS Two-Factor Authentication activated.");
            const box = document.getElementById("sms-setup-box");
            if (box) box.classList.add("hidden");
            await loadAuthModalSecurityDetails();
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || "Invalid or expired SMS code.", true);
        }
    } catch (e) {
        showToast("SMS activation error: " + e.message, true);
    }
}

async function removeMfaMethod(method) {
    const methodNames = {
        "totp_app": "Authenticator App",
        "email_otp": "Email OTP",
        "sms_otp": "SMS OTP"
    };
    const displayName = methodNames[method] || method;
    if (!confirm(`Are you sure you want to remove ${displayName}?`)) return;

    try {
        const res = await fetch(`/api/v1/auth/mfa/remove-method?method=${encodeURIComponent(method)}`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${currentToken}` }
        });
        if (res.ok) {
            showToast(`${displayName} removed successfully.`);
            await loadAuthModalSecurityDetails();
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || "Failed to remove verification factor.", true);
        }
    } catch (e) {
        showToast("Error removing factor: " + e.message, true);
    }
}

async function handleDisableMfa() {
    if (!confirm("Are you sure you want to disable Multi-Factor Authentication? Your account will revert to single-factor password protection.")) return;

    try {
        const res = await fetch("/api/v1/auth/mfa/disable", {
            method: "POST",
            headers: { "Authorization": `Bearer ${currentToken}` }
        });
        if (res.ok) {
            showToast("Multi-Factor Authentication disabled.");
            await loadAuthModalSecurityDetails();
        } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || "Failed to disable MFA.", true);
        }
    } catch (e) {
        showToast("Disable MFA error: " + e.message, true);
    }
}

// =============================================================================
// POLICIES & PRESETS INGESTION & CMS SYNC
// =============================================================================
async function loadPolicies() {
    try {
        const res = await fetch("/api/v1/policies");
        if (res.ok) {
            const policies = await res.json();
            cachedPoliciesList = policies;
            const select = document.getElementById("policy-select");
            const previousVal = select.value;
            select.innerHTML = "";
            policies.forEach(p => {
                const opt = document.createElement("option");
                opt.value = p.policy_id;
                opt.textContent = `${p.policy_id} - ${p.title} (${p.category})`;
                select.appendChild(opt);
            });
            if (previousVal && Array.from(select.options).some(o => o.value === previousVal)) {
                select.value = previousVal;
            }
        }
        await checkCmsSyncStatus();
    } catch (e) {
        console.error("Failed to load policies:", e);
    }
}

async function checkCmsSyncStatus() {
    try {
        const res = await fetch("/api/v1/policies/sync-status");
        if (res.ok) {
            const data = await res.json();
            const statusElem = document.getElementById("cms-sync-status-text");
            if (statusElem) {
                const count = data.policies_in_database || 0;
                let lastSyncStr = "Just now";
                if (data.last_sync) {
                    try {
                        const date = new Date(data.last_sync);
                        lastSyncStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                    } catch (_) {}
                }
                statusElem.textContent = `CMS Live Feed: Connected (${count} Policies Active · Synced: ${lastSyncStr})`;
            }
        }
    } catch (e) {
        console.warn("Could not retrieve CMS sync status:", e);
    }
}

async function triggerUiCmsSync() {
    const statusElem = document.getElementById("cms-sync-status-text");
    const origText = statusElem ? statusElem.textContent : "";
    if (statusElem) {
        statusElem.textContent = "Connecting to CMS Medicare Coverage Database (MCD)...";
    }
    showToast("Connecting to CMS Medicare Coverage Database (MCD) transmittal feeds...", "info");

    try {
        const res = await fetch("/api/v1/policies/sync-cms", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(currentToken ? { "Authorization": `Bearer ${currentToken}` } : {})
            }
        });

        if (res.ok) {
            const result = await res.json();
            await loadPolicies();
            await checkCmsSyncStatus();
            const totalChanges = (result.total_updated || 0) + (result.total_inserted || 0);
            if (totalChanges > 0) {
                showToast(`CMS Sync Complete: ${result.total_updated} updated, ${result.total_inserted} new policies added!`, "success");
            } else {
                showToast("CMS Sync Verified: All local coverage rules match latest CMS transmittals.", "success");
            }
        } else {
            const err = await res.json().catch(() => ({ detail: "Sync request failed" }));
            showToast(`Sync alert: ${err.detail || "Unable to sync with CMS"}`, "warning");
            if (statusElem) statusElem.textContent = origText;
        }
    } catch (e) {
        console.error("CMS Sync Error:", e);
        showToast("Error connecting to CMS synchronization service", "danger");
        if (statusElem) statusElem.textContent = origText;
    }
}

async function loadPresets() {
    try {
        const res = await fetch("/api/v1/presets");
        if (res.ok) {
            const data = await res.json();
            clinicalPresets = data.presets;
            renderPresetButtons();
            // In tutorial/sample modal, default selection is the first preset
            selectedModalPresetId = (clinicalPresets.length > 0) ? clinicalPresets[0].id : "preset-icd-qualifying";
        }
    } catch (e) {
        console.error("Failed to load presets:", e);
    }
}

function renderPresetButtons() {
    const bar = document.getElementById("presets-button-bar");
    if (!bar) return;
    bar.innerHTML = "";
    clinicalPresets.forEach((p, idx) => {
        const btn = document.createElement("button");
        btn.className = `preset-pill ${idx === 0 ? "active" : ""}`;
        btn.textContent = p.label;
        btn.onclick = () => {
            document.querySelectorAll(".preset-pill").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            loadPreset(p.id);
        };
        bar.appendChild(btn);
    });
}

function loadPreset(presetId) {
    const p = clinicalPresets.find(x => x.id === presetId);
    if (!p) return;

    const policyElem = document.getElementById("policy-select");
    const patElem = document.getElementById("patient-id-input");
    const ehrElem = document.getElementById("ehr-input");

    if (policyElem) policyElem.value = p.policy_id;
    if (patElem) patElem.value = p.patient_id;
    if (ehrElem) ehrElem.value = p.ehr_text;

    // Clear previous evaluation results so fresh check runs on new sample
    lastAdjudicationResult = null;
    currentCoveragePacket = null;
    maxUnlockedStep = 2; // Step 1 is filled, Step 2 is unlocked

    // Update Screen 2 policy details
    updatePolicyStep2Preview();
}

function onPolicyChange() {
    updatePolicyStep2Preview();
    resetAdjudicationDisplay();
}

function clearEHR() {
    document.getElementById("ehr-input").value = "";
    resetAdjudicationDisplay();
}

function toggleStepperDetails() {
    const grid = document.getElementById("collapsible-stepper-grid");
    const icon = document.getElementById("stepper-toggle-icon");
    if (!grid) return;
    grid.classList.toggle("collapsed");
    if (icon) {
        icon.classList.toggle("rotated");
    }
}

let maxUnlockedStep = 1;
let currentActiveStep = 1;

function isStepCompleted(stepNumber) {
    if (stepNumber === 1) {
        const ehr = document.getElementById("ehr-input");
        const pasted = document.getElementById("actual-paste-textarea");
        const val = (ehr && ehr.value.trim()) || (pasted && pasted.value.trim()) || "";
        return val.length >= 20;
    }
    if (stepNumber === 2) {
        return lastAdjudicationResult !== null;
    }
    if (stepNumber === 3) {
        return lastAdjudicationResult !== null && lastAdjudicationResult.adjudication_decision !== "DENIED";
    }
    if (stepNumber === 4) {
        return currentCoveragePacket !== null && currentCoveragePacket.submission_status === "SUBMITTED_TO_PAYER";
    }
    return false;
}

function calculateMaxUnlockedStep() {
    let unlocked = 1;
    if (isStepCompleted(1)) {
        unlocked = 2;
        if (isStepCompleted(2)) {
            // Once policy check is evaluated, Step 3 is completed and Step 4 (Review & Sign) is unlocked
            unlocked = 4;
            if (isStepCompleted(4)) {
                // Once signed & submitted, Step 5 is unlocked
                unlocked = 5;
            }
        }
    }
    if (unlocked > maxUnlockedStep) {
        maxUnlockedStep = unlocked;
    }
    return maxUnlockedStep;
}

function canAccessStep(targetStep) {
    calculateMaxUnlockedStep();
    return targetStep <= maxUnlockedStep;
}

function updateWorkflowRibbon(stepNumber) {
    currentActiveStep = stepNumber;
    calculateMaxUnlockedStep();

    for (let i = 1; i <= 4; i++) {
        const step = document.getElementById(`wf-step-${i}`);
        if (!step) continue;
        step.classList.remove("active", "completed", "accessible", "locked");

        const completed = isStepCompleted(i);
        const accessible = i <= maxUnlockedStep;

        if (i === stepNumber) {
            step.classList.add("active");
            if (completed) step.classList.add("completed");
        } else if (completed) {
            step.classList.add("completed");
            step.classList.add("accessible");
        } else if (accessible) {
            step.classList.add("accessible");
        } else {
            step.classList.add("locked");
        }
    }
}

let currentNoteMode = "actual"; // default is actual note mode
let selectedModalPresetId = "preset-icd-qualifying";

// =============================================================================
// SAMPLE TUTORIAL MODAL HANDLERS
// =============================================================================
function openSampleTutorialModal() {
    const modal = document.getElementById("sample-tutorial-modal");
    if (modal) modal.classList.remove("hidden");
}

function closeSampleTutorialModal() {
    const modal = document.getElementById("sample-tutorial-modal");
    if (modal) modal.classList.add("hidden");
}

// =============================================================================
// TERMS & PRIVACY COMPLIANCE MODAL HANDLERS
// =============================================================================
function openTermsModal(sectionId) {
    const modal = document.getElementById("terms-modal");
    if (!modal) return;
    modal.classList.remove("hidden");
    if (sectionId) {
        setTimeout(() => {
            const sec = document.getElementById(sectionId);
            if (sec) {
                sec.scrollIntoView({ behavior: "smooth", block: "start" });
                sec.style.outline = "2px solid var(--accent-cyan)";
                setTimeout(() => { sec.style.outline = "none"; }, 2500);
            }
        }, 150);
    }
}

function closeTermsModal() {
    const modal = document.getElementById("terms-modal");
    if (modal) modal.classList.add("hidden");
}

function selectModalSample(tileElem, presetId) {
    document.querySelectorAll(".modal-cases-grid .patient-tile").forEach(t => t.classList.remove("active"));
    if (tileElem) tileElem.classList.add("active");
    selectedModalPresetId = presetId;
}

function confirmLoadSampleAndProceed() {
    currentNoteMode = "sample";

    // Fallback if selectedModalPresetId wasn't set
    if (!selectedModalPresetId && clinicalPresets && clinicalPresets.length > 0) {
        selectedModalPresetId = clinicalPresets[0].id;
    }

    loadPreset(selectedModalPresetId);

    const p = clinicalPresets.find(x => x.id === selectedModalPresetId);
    const sampleText = p ? p.ehr_text : (document.getElementById("ehr-input")?.value || "");

    // Populate both inputs
    const ehrElem = document.getElementById("ehr-input");
    const pasteBox = document.getElementById("actual-paste-textarea");
    if (ehrElem && sampleText) ehrElem.value = sampleText;
    if (pasteBox && sampleText) pasteBox.value = sampleText;

    // Update banner UI
    const banner = document.getElementById("active-note-badge-banner");
    const descText = document.getElementById("active-note-description-text");
    if (banner && descText) {
        const patientName = p ? (p.patient_name || p.label) : "Eleanor Vance";
        descText.textContent = `Loaded Sample Note: ${patientName} — Click "Clear" anytime to use your own note`;
        banner.classList.remove("hidden");
    }

    maxUnlockedStep = Math.max(maxUnlockedStep, 2);
    closeSampleTutorialModal();
    showToast(`Loaded sample case: ${p ? p.label : selectedModalPresetId}`);
    proceedToStep2();
}

function clearLoadedSample() {
    currentNoteMode = "actual";
    const ehrElem = document.getElementById("ehr-input");
    const pasteBox = document.getElementById("actual-paste-textarea");
    const banner = document.getElementById("active-note-badge-banner");
    const patElem = document.getElementById("patient-id-input");
    const authCard = document.getElementById("note-authenticity-card");

    if (ehrElem) ehrElem.value = "";
    if (pasteBox) pasteBox.value = "";
    if (banner) banner.classList.add("hidden");
    if (authCard) authCard.classList.add("hidden");
    if (patElem) patElem.value = "PT-ACTUAL-" + Math.floor(1000 + Math.random() * 9000);

    maxUnlockedStep = 1;
    resetAdjudicationDisplay();
    showToast("Sample cleared. You can now upload or paste your own clinical note.");
}

function switchNoteInputMode(mode) {
    // Kept for backward compatibility if called
    if (mode === "sample") {
        openSampleTutorialModal();
    } else {
        clearLoadedSample();
    }
}

function syncPastedNoteToInput() {
    const pasted = document.getElementById("actual-paste-textarea");
    const ehrElem = document.getElementById("ehr-input");
    const patElem = document.getElementById("patient-id-input");
    const banner = document.getElementById("active-note-badge-banner");

    if (pasted && ehrElem) {
        ehrElem.value = pasted.value;
        if (currentNoteMode === "sample" && pasted.value.trim() !== (clinicalPresets.find(p => p.id === selectedModalPresetId)?.ehr_text || "").trim()) {
            // User modified the text or typed their own
            currentNoteMode = "actual";
            if (banner) banner.classList.add("hidden");
        }
        if (patElem && (!patElem.value || patElem.value.startsWith("PT-CARD-8821"))) {
            patElem.value = "PT-ACTUAL-" + Math.floor(1000 + Math.random() * 9000);
        }
        updateWorkflowRibbon(currentActiveStep);
        verifyCurrentNoteAuthenticity();
    }
}

async function handleActualFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    currentNoteMode = "actual";
    const banner = document.getElementById("active-note-badge-banner");
    const descText = document.getElementById("active-note-description-text");
    const titleElem = document.getElementById("actual-upload-title");
    const subElem = document.getElementById("actual-upload-subtitle");

    if (titleElem) titleElem.textContent = `Reading: ${file.name} (${(file.size / 1024).toFixed(1)} KB)...`;
    if (subElem) subElem.textContent = "Extracting text and running OCR on document...";

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch("/api/v1/extract-text", {
            method: "POST",
            body: formData
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || `Server error ${res.status}`);
        }

        const data = await res.json();
        const extractedText = data.extracted_text;

        // Fill the text into the inputs for user review and confirmation
        const ehrElem = document.getElementById("ehr-input");
        const pasteBox = document.getElementById("actual-paste-textarea");
        if (ehrElem) ehrElem.value = extractedText;
        if (pasteBox) {
            pasteBox.value = extractedText;
            pasteBox.scrollIntoView({ behavior: "smooth", block: "center" });
        }

        // Auto-match suggested policy
        if (data.suggested_policy_id) {
            const policySelect = document.getElementById("policy-select");
            if (policySelect) policySelect.value = data.suggested_policy_id;
        }

        // Show confirmation badge banner on Screen 1
        if (banner && descText) {
            descText.textContent = `Extracted from "${file.name}" (${data.character_count} chars). Please review, edit if needed, and confirm below:`;
            banner.classList.remove("hidden");
        }

        if (titleElem) titleElem.textContent = `Uploaded: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        if (subElem) subElem.textContent = `Text extracted successfully! Please review the text below and click "Continue to Policy Match" when ready.`;

        // Render Doctor Name & Signature Authenticity
        if (data.authenticity) {
            renderAuthenticityCard(data.authenticity);
        } else {
            verifyCurrentNoteAuthenticity();
        }

        // Update workflow ribbon now that Step 1 is filled
        updateWorkflowRibbon(1);
        showToast(`Extracted ${data.character_count} characters. Review the text below and confirm.`);
    } catch (e) {
        console.error("Text extraction failed:", e);
        showToast("Text extraction failed: " + e.message, true);
        if (titleElem) titleElem.textContent = "Drop Doctor's Note or Medical Image Here, or Click to Browse";
        if (subElem) subElem.textContent = "Accepts PDF, Word (.docx), Plain Text (.txt), or Scanned Images & Photos (.png, .jpg, .jpeg).";
    }
}

function checkNoteAuthenticity(text) {
    if (!text || text.trim().length < 20) {
        return {
            is_authentic_clinical_note: false,
            has_doctor_name: false,
            has_doctor_signature: false,
            doctor_name: null,
            signature_text: null,
            reasons: ["Clinical text is too short."]
        };
    }

    const raw = text.trim();

    // Doctor name regexes
    let doctorName = null;
    let hasDoctorName = false;
    const docPatterns = [
        /\b(?:Dr\.|Doctor)\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)(?:,\s*(?:MD|DO|NP|PA-C|PA|FACC|FACP|MBBS))?\b/,
        /(?:attending|provider|physician|clinician|consultant|prescriber|cardiologist|pulmonologist)\s*(?:name)?\s*:\s*(?:Dr\.\s*)?([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)(?:,\s*(?:MD|DO|NP|PA-C|PA|FACC|FACP|MBBS))?/i,
        /\b([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+),\s*(?:MD|DO|NP|PA-C|MBBS)(?:\s*,\s*(?:FACC|FACP|FACS))?\b/,
        /(?:electronically\s+signed\s+by|signed\s+by|attested\s+by)\s*:?\s*(?:Dr\.\s*)?([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)/i
    ];
    for (const pat of docPatterns) {
        const m = raw.match(pat);
        if (m) {
            doctorName = m[1].trim();
            if (!doctorName.startsWith("Dr.") && !doctorName.toLowerCase().startsWith("doctor")) {
                doctorName = "Dr. " + doctorName;
            }
            hasDoctorName = true;
            break;
        }
    }

    // Signature regexes
    let signatureText = null;
    let hasSignature = false;
    const sigPatterns = [
        /(?:electronically\s+signed\s+by|e-signed\s+by|signed\s+by)\s*:?\s*([^\n\r]+)/i,
        /(?:physician\s+signature|doctor\s+signature|provider\s+signature|attending\s+signature|signature)\s*:\s*([^\n\r]+)/i,
        /(?:attested\s+by|authenticated\s+by)\s*:?\s*([^\n\r]+)/i,
        /(\/s\/\s*[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)/i,
        /(?:i\s+certify\s+that\s+i\s+examined|i\s+personally\s+examined|i\s+attest\s+to\s+the\s+above)/i
    ];
    for (const spat of sigPatterns) {
        const sm = raw.match(spat);
        if (sm) {
            signatureText = sm[0].trim();
            hasSignature = true;
            if (!hasDoctorName && sm[1]) {
                const cand = sm[1].replace(/^\/s\/\s*/i, '').replace(/\s+on\s+.*$/i, '');
                const candMatch = cand.match(/\b(?:Dr\.\s*)?([A-Z][a-z]+\s+[A-Z][a-z]+)/);
                if (candMatch) {
                    doctorName = "Dr. " + candMatch[1].trim();
                    hasDoctorName = true;
                }
            }
            break;
        }
    }

    const reasons = [];
    if (!hasDoctorName) reasons.append ? reasons.append("Missing doctor name") : reasons.push("Missing doctor/physician name (e.g., Dr. Name, MD).");
    if (!hasSignature) reasons.push("Missing doctor signature or attestation line.");

    return {
        is_authentic_clinical_note: hasDoctorName && hasSignature,
        has_doctor_name: hasDoctorName,
        has_doctor_signature: hasSignature,
        doctor_name: doctorName,
        signature_text: signatureText,
        reasons: reasons
    };
}

function verifyCurrentNoteAuthenticity() {
    const text = document.getElementById("ehr-input")?.value || document.getElementById("actual-paste-textarea")?.value || "";
    if (!text || text.trim().length < 20) {
        const card = document.getElementById("note-authenticity-card");
        if (card) card.classList.add("hidden");
        return;
    }
    const res = checkNoteAuthenticity(text);
    renderAuthenticityCard(res);
}

function renderAuthenticityCard(auth) {
    const card = document.getElementById("note-authenticity-card");
    if (!card) return;

    const iconBadge = document.getElementById("auth-status-icon");
    const title = document.getElementById("auth-status-title");
    const desc = document.getElementById("auth-status-desc");
    const nameVal = document.getElementById("auth-doc-name-val");
    const nameIcon = document.getElementById("auth-doc-name-icon");
    const sigVal = document.getElementById("auth-doc-sig-val");
    const sigIcon = document.getElementById("auth-doc-sig-icon");

    card.classList.remove("hidden", "auth-invalid", "auth-warning");

    if (auth.has_doctor_name && auth.has_doctor_signature) {
        // Fully Verified
        title.textContent = "Doctor's Note Authenticated";
        desc.textContent = "Verified licensed physician credentials and valid signature block.";
        iconBadge.innerHTML = `<span class="med-icon icon-sm icon-green"><svg viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg></span>`;
    } else if (auth.has_doctor_name || auth.has_doctor_signature) {
        card.classList.add("auth-warning");
        title.textContent = "Incomplete Provider Documentation";
        desc.textContent = "Doctor's name or signature line is missing. Medicare requires attesting provider details.";
        iconBadge.innerHTML = `<span class="med-icon icon-sm icon-amber"><svg viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg></span>`;
    } else {
        card.classList.add("auth-invalid");
        title.textContent = "Unverified Clinical Note (Missing Doctor Credentials)";
        desc.textContent = "No physician name or signature detected. Please ensure the note includes the treating doctor's name and signature.";
        iconBadge.innerHTML = `<span class="med-icon icon-sm icon-red"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg></span>`;
    }

    if (nameVal && nameIcon) {
        if (auth.has_doctor_name) {
            nameVal.textContent = auth.doctor_name || "Doctor Identified";
            nameVal.style.color = "#166534";
            nameIcon.textContent = "";
            nameIcon.className = "auth-check-icon";
        } else {
            nameVal.textContent = "Not Documented";
            nameVal.style.color = "#B91C1C";
            nameIcon.textContent = "";
            nameIcon.className = "auth-check-icon icon-missing";
        }
    }

    if (sigVal && sigIcon) {
        if (auth.has_doctor_signature) {
            sigVal.textContent = "Verified Signature Block";
            sigVal.style.color = "#166534";
            sigIcon.textContent = "";
            sigIcon.className = "auth-check-icon";
        } else {
            sigVal.textContent = "Missing Signature";
            sigVal.style.color = "#B91C1C";
            sigIcon.textContent = "";
            sigIcon.className = "auth-check-icon icon-missing";
        }
    }
}

function selectPatientTile(tileElem, presetId) {
    selectModalSample(tileElem, presetId);
}

function proceedToStep2() {
    const ehrText = document.getElementById("ehr-input").value.trim();
    if (!ehrText || ehrText.length < 20) {
        showToast("Please upload a file or paste your patient note text (at least 20 characters), or click 'Try a Sample' above.", true);
        return;
    }

    // Verify Doctor Name & Signature
    const auth = checkNoteAuthenticity(ehrText);
    renderAuthenticityCard(auth);

    if (!auth.has_doctor_name || !auth.has_doctor_signature) {
        const missingParts = [];
        if (!auth.has_doctor_name) missingParts.push("doctor/physician name (e.g. Dr. Name, MD)");
        if (!auth.has_doctor_signature) missingParts.push("electronic signature or attestation line");
        showToast(`Document requires: ${missingParts.join(" and ")}. Please append below or certify.`, true);
        
        // If user wants to proceed anyway, allow them after warning or let them edit
        const proceedConfirmed = confirm(`Clinical Document Verification Warning:\n\nThis note is missing ${missingParts.join(" and ")}.\n\nMedicare Part B prior authorization requires treating physician identification and signature.\n\nDo you want to proceed to Step 2 anyway and supply attestation on the official form?`);
        if (!proceedConfirmed) {
            return;
        }
    }

    updatePolicyStep2Preview();
    triggerMultiPolicyAutoScan();
    goToWizardScreen(2);
}

let lastMultiPolicyScanResult = null;

async function triggerMultiPolicyAutoScan() {
    const ehrText = document.getElementById("ehr-input").value.trim();
    const patId = document.getElementById("patient-id-input").value.trim() || "PT-CLINICAL";
    const counterElem = document.getElementById("scan-summary-counter");
    const gridElem = document.getElementById("policy-match-grid");

    if (!ehrText || ehrText.length < 20) return;

    if (counterElem) counterElem.textContent = "Scanning clinical documentation across all CMS policies in database...";

    try {
        const res = await fetch("/api/v1/adjudicate/scan-all", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(currentToken ? { "Authorization": `Bearer ${currentToken}` } : {})
            },
            body: JSON.stringify({
                patient_id: patId,
                ehr_narrative: ehrText
            })
        });

        if (res.ok) {
            const data = await res.json();
            lastMultiPolicyScanResult = data;
            renderMultiPolicyScanResults(data);
        } else {
            if (counterElem) counterElem.textContent = "Multi-policy scan ready.";
        }
    } catch (e) {
        console.error("Multi-policy auto-scan failed:", e);
        if (counterElem) counterElem.textContent = "Multi-policy scan offline.";
    }
}

function renderMultiPolicyScanResults(data) {
    const featuredSlot = document.getElementById("featured-policy-slot");
    const gridElem = document.getElementById("policy-match-grid");
    const policySelect = document.getElementById("policy-select");

    // Auto-select best match if none chosen or on initial scan
    if (data.best_match_policy_id && (!policySelect.value || policySelect.value === "NCD-20.4")) {
        policySelect.value = data.best_match_policy_id;
    }

    const currentId = policySelect.value || data.best_match_policy_id || "NCD-20.4";
    const featuredMatch = (data.all_matches && data.all_matches.length > 0)
        ? (data.all_matches.find(m => m.policy_id === currentId) || data.all_matches[0])
        : null;
    const otherMatches = (data.all_matches && featuredMatch)
        ? data.all_matches.filter(m => m.policy_id !== featuredMatch.policy_id)
        : [];

    // 1. Render Featured (Bigger Hero Card)
    if (featuredSlot && featuredMatch) {
        const pct = Math.round(featuredMatch.calibrated_confidence * 100);
        let statusBadge = "";
        if (featuredMatch.decision === "APPROVED") {
            statusBadge = `<span class="badge-featured-status approved"><span class="badge-dot" style="background:#10b981;"></span>QUALIFIED (${pct}%)</span>`;
        } else if (featuredMatch.decision === "DEFERRED_TO_HUMAN") {
            statusBadge = `<span class="badge-featured-status deferred"><span class="badge-dot" style="background:#f59e0b;"></span>AUDITOR REVIEW (${pct}%)</span>`;
        } else {
            statusBadge = `<span class="badge-featured-status unmet"><span class="badge-dot" style="background:#64748b;"></span>CRITERIA UNMET (${pct}%)</span>`;
        }

        const bestBadge = featuredMatch.is_best_match 
            ? `<span class="badge-best-featured"><svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg> BEST MATCH</span>` 
            : "";

        featuredSlot.innerHTML = `
            <div class="featured-hero-card ${featuredMatch.decision.toLowerCase()}">
                <div class="featured-top-row">
                    <div class="featured-meta-group">
                        <span class="featured-code">${featuredMatch.policy_id}</span>
                        <span class="featured-dot">&bull;</span>
                        <span class="featured-category">${featuredMatch.category}</span>
                    </div>
                    <div class="featured-badges">
                        ${bestBadge}
                        ${statusBadge}
                    </div>
                </div>
                <div class="featured-title">${featuredMatch.policy_title}</div>
                <div class="featured-bottom-row">
                    <div class="featured-criteria-count">
                        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
                        <span>${featuredMatch.met_criteria}/${featuredMatch.total_criteria} Criteria Satisfied</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <button type="button" class="btn-subtle-doc" onclick="openPolicyDocumentModal('${featuredMatch.policy_id}')" title="Read complete Medicare statutory guidelines and criteria document">
                            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
                            Read Policy Document
                        </button>
                        <span class="featured-active-pill">
                            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
                            Selected Directive
                        </span>
                    </div>
                </div>
            </div>
        `;
    }

    // 2. Render Other Candidates (Smaller Cards)
    if (gridElem) {
        gridElem.innerHTML = "";
        otherMatches.forEach(m => {
            const card = document.createElement("div");
            card.className = `mini-policy-card ${m.decision.toLowerCase()}`;
            card.onclick = () => selectPolicyFromScan(m.policy_id, true);

            let statusPill = "";
            const pct = Math.round(m.calibrated_confidence * 100);
            if (m.decision === "APPROVED") {
                statusPill = `<span class="mini-status approved">Qualified ${pct}%</span>`;
            } else if (m.decision === "DEFERRED_TO_HUMAN") {
                statusPill = `<span class="mini-status deferred">Review ${pct}%</span>`;
            } else {
                statusPill = `<span class="mini-status unmet">Unmet</span>`;
            }

            card.innerHTML = `
                <div class="mini-top-row">
                    <span class="mini-code">${m.policy_id}</span>
                    ${statusPill}
                </div>
                <div class="mini-title" title="${m.policy_title}">${m.policy_title}</div>
                <div class="mini-footer">
                    <span class="mini-crit-count">${m.met_criteria}/${m.total_criteria} Met</span>
                    <span class="mini-select-btn">Select &rarr;</span>
                </div>
            `;
            gridElem.appendChild(card);
        });
    }

    updatePolicyStep2Preview();
}

function selectPolicyFromScan(policyId, triggerToast = true) {
    const policySelect = document.getElementById("policy-select");
    if (policySelect) policySelect.value = policyId;

    if (lastMultiPolicyScanResult) {
        renderMultiPolicyScanResults(lastMultiPolicyScanResult);
    }
    updatePolicyStep2Preview();
    if (triggerToast) {
        showToast(`Selected ${policyId} for coverage determination`);
    }
}

function updatePolicyStep2Preview() {
    const policyId = document.getElementById("policy-select").value || "NCD-20.4";
    const patientId = document.getElementById("patient-id-input").value || (currentNoteMode === "actual" ? "PT-ACTUAL-CLINICAL" : "PT-CARD-8821");

    const badgeIcon = document.getElementById("policy-badge-icon");
    const titleElem = document.getElementById("step2-policy-title");
    const idElem = document.getElementById("step2-policy-id");
    const patElem = document.getElementById("step2-patient-id");
    const listElem = document.getElementById("step2-requirements-list");

    if (idElem) idElem.textContent = policyId;
    if (patElem) {
        if (currentNoteMode === "actual") {
            patElem.textContent = `Patient Identifier: ${patientId} (Actual Clinical Consultation Note)`;
        } else {
            const patName = patientId === "PT-CARD-8821" ? "Eleanor Vance" : (patientId === "PT-RESP-4402" ? "Arthur Miller" : (patientId === "PT-CARD-9014" ? "Robert Thornton" : "Harold Hayes"));
            patElem.textContent = `Sample Patient: ${patName} (${patientId})`;
        }
    }

    if (policyId === "NCD-20.4") {
        if (badgeIcon) badgeIcon.innerHTML = `<span class="med-icon icon-lg icon-blue"><svg viewBox="0 0 24 24"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path><path d="M3.5 12h3l2-4 3 8 2-5 2 2h4"></path></svg></span>`;
        if (titleElem) titleElem.textContent = "Implantable Automatic Defibrillators";
        if (listElem) listElem.innerHTML = `
            <span class="rule-chip">LVEF &le; 35%</span>
            <span class="rule-chip">NYHA Class II or III</span>
            <span class="rule-chip">GDMT &ge; 90 days</span>
            <span class="rule-chip">No MI within 40 days</span>
        `;
    } else if (policyId === "LCD-L33829") {
        if (badgeIcon) badgeIcon.innerHTML = `<span class="med-icon icon-lg icon-cyan"><svg viewBox="0 0 24 24"><path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2"></path></svg></span>`;
        if (titleElem) titleElem.textContent = "PAP Devices for Sleep Apnea";
        if (listElem) listElem.innerHTML = `
            <span class="rule-chip">Diagnostic Polysomnogram</span>
            <span class="rule-chip">AHI &ge; 15/hr (or &ge; 5 with symptoms)</span>
            <span class="rule-chip">Face-to-face evaluation</span>
        `;
    } else if (policyId === "NCD-20.29") {
        if (badgeIcon) badgeIcon.innerHTML = `<span class="med-icon icon-lg icon-amber"><svg viewBox="0 0 24 24"><path d="M22 12h-4l-3 9L9 3l-3 9H2"></path></svg></span>`;
        if (titleElem) titleElem.textContent = "Hyperbaric Oxygen for Diabetic Wounds";
        if (listElem) listElem.innerHTML = `
            <span class="rule-chip">Diabetic lower extremity wound</span>
            <span class="rule-chip">Wagner Grade III or higher</span>
            <span class="rule-chip">Failed 30-day conventional care</span>
        `;
    } else {
        if (badgeIcon) badgeIcon.innerHTML = `<span class="med-icon icon-lg icon-blue"><svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg></span>`;
        if (titleElem) titleElem.textContent = "Medicare Coverage Determination";
        if (listElem) listElem.innerHTML = `
            <span class="rule-chip">Documented clinical necessity</span>
            <span class="rule-chip">Prior conservative therapy</span>
        `;
    }
}

function goToWizardScreen(stepNumber) {
    if (stepNumber < 1) stepNumber = 1;
    if (stepNumber > 5) stepNumber = 5;

    // Check prerequisites sequentially
    if (stepNumber >= 2 && !isStepCompleted(1)) {
        showToast("Please upload or paste a patient note (at least 20 characters) first.", true);
        return;
    }

    if (stepNumber >= 3 && !lastAdjudicationResult) {
        showToast("Please click 'Check If Note Meets These Rules' on Step 2 to evaluate Medicare coverage first.", true);
        return;
    }

    if (stepNumber >= 4) {
        if (!currentCoveragePacket && lastAdjudicationResult) {
            loadAndShowCoveragePacket(lastAdjudicationResult.case_id);
        }
        if (!currentCoveragePacket && !lastAdjudicationResult) {
            showToast("Please complete the Medicare policy check first.", true);
            return;
        }
        populatePacketDocument();
    }

    if (stepNumber === 5) {
        if (!currentCoveragePacket || currentCoveragePacket.submission_status !== "SUBMITTED_TO_PAYER") {
            showToast("Please review and sign the prior authorization form on Step 4 before submitting.", true);
            return;
        }
    }

    document.querySelectorAll(".wizard-screen").forEach(s => s.classList.remove("active"));
    const targetScreen = document.getElementById(`screen-step-${stepNumber}`);
    if (targetScreen) {
        targetScreen.classList.add("active");
    }

    updateWorkflowRibbon(stepNumber);
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function startNewPatientNote() {
    clearLoadedSample();
    goToWizardScreen(1);
    showToast("Ready for a new patient note.");
}

function resetAdjudicationDisplay() {
    // Reset Big Verdict Card
    const verdictCard = document.getElementById("big-verdict-card");
    if (verdictCard) {
        verdictCard.className = "big-verdict-card verdict-pending";
        document.getElementById("verdict-bubble").innerHTML = `<span class="med-icon icon-md"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg></span>`;
        document.getElementById("verdict-title").textContent = "Ready to Evaluate";
        document.getElementById("verdict-subtitle").textContent = "Upload a medical note or pick a sample on the left to check Medicare coverage.";
        const badge = document.getElementById("abstention-badge");
        if (badge) badge.textContent = "Coverage Ready";
    }

    // Reset Summary Cards
    const resCritCount = document.getElementById("res-criteria-count");
    if (resCritCount) resCritCount.textContent = "-- Met";
    const resCritTotal = document.getElementById("res-criteria-total");
    if (resCritTotal) {
        resCritTotal.textContent = "Evaluating rules...";
        resCritTotal.style.color = "";
    }
    const resNextTitle = document.getElementById("res-next-step-title");
    if (resNextTitle) resNextTitle.textContent = "Review & Sign Form";
    const resNextSub = document.getElementById("res-next-step-sub");
    if (resNextSub) resNextSub.textContent = "Proceed to Step 4";
    const resGrounding = document.getElementById("res-grounding-stat");
    if (resGrounding) resGrounding.textContent = "100% Exact Quotes";
    const resConf = document.getElementById("res-conf-stat");
    if (resConf) resConf.textContent = "--";

    // Reset Hero Action Container
    const actionContainer = document.getElementById("primary-action-container");
    if (actionContainer) actionContainer.classList.add("hidden");

    // Metrics ribbon
    const metricCal = document.getElementById("metric-calibrated-conf");
    if (metricCal) metricCal.textContent = "--";
    const metricGrd = document.getElementById("metric-grounding");
    if (metricGrd) {
        metricGrd.textContent = "--";
        metricGrd.className = "ribbon-val text-green";
    }
    const metricPol = document.getElementById("metric-policy-name");
    if (metricPol) metricPol.textContent = "--";
    const metricLat = document.getElementById("metric-latency");
    if (metricLat) metricLat.textContent = "--";

    const clinicianBox = document.getElementById("clinician-action-box");
    if (clinicianBox) clinicianBox.classList.add("hidden");
    const ehrHigh = document.getElementById("ehr-highlight-display");
    if (ehrHigh) ehrHigh.innerHTML = `<p class="placeholder-text">Extracted sentences anchoring each requirement will appear highlighted here.</p>`;
    const critList = document.getElementById("criteria-cards-list");
    if (critList) critList.innerHTML = `<div class="empty-state-notice">Criteria breakdown will appear here after evaluation.</div>`;
    
    const hashDisp = document.getElementById("audit-hash-display");
    if (hashDisp) hashDisp.textContent = "Awaiting Adjudication Run";

    // Clear active adjudication & packet state
    lastAdjudicationResult = null;
    currentCoveragePacket = null;
    maxUnlockedStep = 1;

    // Reset Workflow Ribbon to Step 1
    updateWorkflowRibbon(1);

    // Reset Stepper
    resetStepper();
}

function resetStepper() {
    ["retrieval", "evaluator", "verifier", "abstention"].forEach(s => {
        const card = document.getElementById(`step-${s}`);
        if (card) {
            card.className = "step-card";
            const stat = document.getElementById(`step-${s}-status`);
            if (stat) stat.textContent = "IDLE";
        }
    });
    const lat = document.getElementById("stepper-latency");
    if (lat) lat.textContent = "Status: Ready";
}

// =============================================================================
// ADJUDICATION EXECUTION
// =============================================================================
async function executeAdjudication() {
    const policyId = document.getElementById("policy-select").value;
    const patientId = document.getElementById("patient-id-input").value.trim() || "PT-1000";
    const ehrText = document.getElementById("ehr-input").value.trim();
    const tau = parseFloat(document.getElementById("tau-input").value) || 0.85;

    if (!ehrText || ehrText.length < 20) {
        showToast("Please input clinical EHR notes (min 20 characters).", true);
        return;
    }

    const runBtn = document.getElementById("run-adjudicate-btn");
    runBtn.disabled = true;
    runBtn.innerHTML = `<span class="btn-icon">&#8987;</span> Evaluating Multi-Agent Pipeline...`;

    // Step 2 in progress on ribbon
    updateWorkflowRibbon(2);

    // Step 1: Retrieval Animation
    animateStep("retrieval", "RUNNING", "active");
    await sleep(150);

    try {
        animateStep("retrieval", "RETRIEVED", "completed");
        animateStep("evaluator", "EXTRACTING", "active");
        await sleep(150);

        animateStep("evaluator", "PARSED", "completed");
        animateStep("verifier", "VERIFYING", "active");
        await sleep(150);

        const res = await fetch("/api/v1/adjudicate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(currentToken ? { "Authorization": `Bearer ${currentToken}` } : {})
            },
            body: JSON.stringify({
                patient_id: patientId,
                policy_id: policyId,
                ehr_narrative: ehrText,
                options: { tau: tau }
            })
        });

        if (!res.ok) {
            throw new Error(`Server returned HTTP ${res.status}`);
        }

        const data = await res.json();
        lastAdjudicationResult = data;

        animateStep("verifier", "AUDITED", "completed");
        animateStep("abstention", data.abstention_status ? "ABSTAINED" : "DECIDED", "completed");

        renderAdjudicationResults(data);
        showToast(`Adjudication completed: ${data.adjudication_decision}`);
        goToWizardScreen(3);
    } catch (e) {
        console.error("Adjudication failed:", e);
        showToast("Adjudication failed: " + e.message, true);
        resetStepper();
    } finally {
        runBtn.disabled = false;
        runBtn.innerHTML = `<span class="btn-icon">&#9654;</span> Run Automated Policy Check`;
    }
}

function animateStep(stepName, statusText, className) {
    const card = document.getElementById(`step-${stepName}`);
    if (card) {
        card.className = `step-card ${className}`;
        const st = document.getElementById(`step-${stepName}-status`);
        if (st) st.textContent = statusText;
    }
}

// =============================================================================
// RENDERING ADJUDICATION & SYNCHRONIZED EVIDENCE
// =============================================================================
function renderAdjudicationResults(data) {
    const stepperLat = document.getElementById("stepper-latency");
    if (stepperLat) stepperLat.textContent = `Pipeline Latency: ${data.execution_time_ms} ms`;

    // 1. Big Verdict Card & Ribbon Updates
    const verdictCard = document.getElementById("big-verdict-card");
    const verdictBubble = document.getElementById("verdict-bubble");
    const verdictTitle = document.getElementById("verdict-title");
    const verdictSubtitle = document.getElementById("verdict-subtitle");
    const abstentionBadge = document.getElementById("abstention-badge");
    const heroBtn = document.getElementById("btn-hero-review");
    const heroContainer = document.getElementById("primary-action-container");

    if (data.adjudication_decision === "APPROVED") {
        if (verdictCard) verdictCard.className = "big-verdict-card verdict-approved";
        if (verdictBubble) verdictBubble.innerHTML = `<span class="med-icon icon-lg icon-green"><svg viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg></span>`;
        if (verdictTitle) verdictTitle.textContent = "Medicare Coverage Approved";
        if (verdictSubtitle) verdictSubtitle.textContent = "All criteria satisfied in clinical record. Ready to review and sign packet.";
        if (abstentionBadge) abstentionBadge.textContent = "Coverage Approved";

        if (heroContainer) heroContainer.classList.remove("hidden");
        if (heroBtn) {
            heroBtn.className = "btn-hero-review";
            heroBtn.innerHTML = `
                <span class="med-icon icon-md icon-blue"><svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg></span>
                <div class="hero-text-block">
                    <strong>Review Pre-Filled Prior Authorization Form</strong>
                    <span>All criteria met (${(data.calibrated_aggregate_confidence * 100).toFixed(0)}% match). Click to inspect, sign, and send to Medicare.</span>
                </div>
                <span class="med-icon icon-sm"><svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg></span>
            `;
        }
    } else if (data.adjudication_decision === "DENIED") {
        if (verdictCard) verdictCard.className = "big-verdict-card verdict-denied";
        if (verdictBubble) verdictBubble.innerHTML = `<span class="med-icon icon-lg icon-red"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg></span>`;
        if (verdictTitle) verdictTitle.textContent = "Medicare Coverage Excluded";
        if (verdictSubtitle) verdictSubtitle.textContent = "Disqualifying policy exclusion rule prevents approval. Available for internal review.";
        if (abstentionBadge) abstentionBadge.textContent = "Coverage Excluded";

        if (heroContainer) heroContainer.classList.remove("hidden");
        if (heroBtn) {
            heroBtn.className = "btn-hero-review hero-amber";
            heroBtn.innerHTML = `
                <span class="med-icon icon-md icon-amber"><svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg></span>
                <div class="hero-text-block">
                    <strong>See Why This Case Was Excluded</strong>
                    <span>Inspect the specific rule that was not met and download a formal explanation for your records.</span>
                </div>
                <span class="med-icon icon-sm"><svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg></span>
            `;
        }
    } else {
        // DEFERRED_TO_HUMAN
        if (verdictCard) verdictCard.className = "big-verdict-card verdict-deferred";
        if (verdictBubble) verdictBubble.innerHTML = `<span class="med-icon icon-lg icon-amber"><svg viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg></span>`;
        if (verdictTitle) verdictTitle.textContent = "Physician Review Needed";
        if (verdictSubtitle) verdictSubtitle.textContent = "One or more criteria require clinician confirmation before submission.";
        if (abstentionBadge) abstentionBadge.textContent = "Review Needed";

        if (heroContainer) heroContainer.classList.remove("hidden");
        if (heroBtn) {
            heroBtn.className = "btn-hero-review hero-amber";
            heroBtn.innerHTML = `
                <span class="med-icon icon-md icon-amber"><svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg></span>
                <div class="hero-text-block">
                    <strong>Review Items Needing Clarification</strong>
                    <span>Check the flagged items below, add your physician attestation notes, and certify the form.</span>
                </div>
                <span class="med-icon icon-sm"><svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg></span>
            `;
        }
    }

    // Step 3 Ribbon Active
    updateWorkflowRibbon(3);

    // 2. Metrics Ribbon
    const metricCal = document.getElementById("metric-calibrated-conf");
    if (metricCal) metricCal.textContent = `${(data.calibrated_aggregate_confidence * 100).toFixed(1)}%`;
    
    // Check if any grounding failure
    const allGrounded = data.verification_audits.every(v => v.grounding_status);
    const groundingElem = document.getElementById("metric-grounding");
    if (groundingElem) {
        if (allGrounded) {
            groundingElem.textContent = "100% Exact";
            groundingElem.className = "ribbon-val text-green";
        } else {
            groundingElem.textContent = "Mismatch / Drift";
            groundingElem.className = "ribbon-val text-red";
        }
    }

    // Policy name and summary cards
    const policyNameElem = document.getElementById("metric-policy-name");
    if (policyNameElem) {
        policyNameElem.textContent = data.policy_id || "Active Policy";
    }

    const resPolicyCode = document.getElementById("res-policy-code");
    const resPolicyCat = document.getElementById("res-policy-category");
    const policyTitle = data.policy_title || (data.policy_id === "NCD-20.4" ? "Implantable Automatic Defibrillators" : (data.policy_id === "LCD-L33829" ? "PAP Devices for Sleep Apnea" : (data.policy_id === "NCD-20.29" ? "Hyperbaric Oxygen Therapy" : "Medicare Part B Coverage")));
    if (resPolicyCode) resPolicyCode.textContent = `${data.policy_id} – ${policyTitle}`;
    if (resPolicyCat) {
        if (data.policy_id === "NCD-20.4") resPolicyCat.textContent = "Defibrillators (Cardiology)";
        else if (data.policy_id === "LCD-L33829") resPolicyCat.textContent = "CPAP Therapy (Pulmonology)";
        else if (data.policy_id === "NCD-20.29") resPolicyCat.textContent = "Hyperbaric Oxygen (Wound Care)";
        else resPolicyCat.textContent = "Medicare Part B";
    }

    // Criteria Status Card
    const totalCriteria = data.criterion_assessments ? data.criterion_assessments.length : 0;
    const passedCriteria = data.criterion_assessments ? data.criterion_assessments.filter(c => {
        if (c.is_exclusion) {
            return c.status === "NOT_MET"; // Exclusion absent means passed!
        }
        return c.status === "MET"; // Mandatory inclusion met
    }).length : 0;
    const resCritCount = document.getElementById("res-criteria-count");
    const resCritTotal = document.getElementById("res-criteria-total");
    if (resCritCount) resCritCount.textContent = `${passedCriteria} of ${totalCriteria} Passed`;
    if (resCritTotal) {
        if (passedCriteria === totalCriteria) {
            resCritTotal.textContent = "All requirements confirmed in note";
            resCritTotal.style.color = "var(--accent-green)";
        } else {
            const unmet = totalCriteria - passedCriteria;
            resCritTotal.textContent = `${unmet} item(s) require doctor review`;
            resCritTotal.style.color = "var(--accent-amber)";
        }
    }

    // Next Step Card & Step 3 Button text
    const resNextTitle = document.getElementById("res-next-step-title");
    const resNextSub = document.getElementById("res-next-step-sub");
    const btnStep3 = document.getElementById("btn-step3-continue");

    const step3ActionGroup = document.getElementById("step3-action-buttons");
    if (data.adjudication_decision === "DENIED") {
        if (resNextTitle) resNextTitle.textContent = "Coverage Excluded by Rule";
        if (resNextSub) resNextSub.textContent = "Submission blocked. Update chart or review advisory.";
        if (step3ActionGroup) {
            step3ActionGroup.innerHTML = `
                <button type="button" class="btn-primary btn-wizard-hero" onclick="goToWizardScreen(1)">
                    <span class="med-icon icon-sm"><svg viewBox="0 0 24 24"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg></span>
                    Revise Clinical Note / Add Evidence
                </button>
                <button type="button" class="btn-secondary" onclick="goToWizardScreen(4)">
                    <span class="med-icon icon-sm"><svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg></span>
                    Inspect Denial Notice (Internal Only)
                </button>
            `;
        }
    } else if (data.adjudication_decision === "DEFERRED_TO_HUMAN") {
        if (resNextTitle) resNextTitle.textContent = "Doctor Attestation Needed";
        if (resNextSub) resNextSub.textContent = "Missing mandatory item requires clinician sign-off";
        if (step3ActionGroup) {
            step3ActionGroup.innerHTML = `
                <button type="button" class="btn-primary btn-wizard-hero" onclick="goToWizardScreen(4)">
                    Review & Complete Attestation
                    <span class="med-icon icon-sm"><svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg></span>
                </button>
            `;
        }
    } else {
        if (resNextTitle) resNextTitle.textContent = "Ready for Sign & Submit";
        if (resNextSub) resNextSub.textContent = "All criteria met with verified citations";
        if (step3ActionGroup) {
            step3ActionGroup.innerHTML = `
                <button type="button" class="btn-primary btn-wizard-hero" onclick="goToWizardScreen(4)">
                    Review Form &amp; Sign
                    <span class="med-icon icon-sm"><svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg></span>
                </button>
            `;
        }
    }

    // Grounding & Confidence
    const resGrounding = document.getElementById("res-grounding-stat");
    if (resGrounding) resGrounding.textContent = allGrounded ? "100% Exact Quotes" : "Flagged Mismatch";

    const resConf = document.getElementById("res-conf-stat");
    if (resConf) resConf.textContent = `${(data.calibrated_aggregate_confidence * 100).toFixed(0)}% Match`;

    const metricLat = document.getElementById("metric-latency");
    if (metricLat) metricLat.textContent = `${data.execution_time_ms} ms`;

    // 3. Clinician Action Box
    const actionBox = document.getElementById("clinician-action-box");
    const actionContent = document.getElementById("clinician-action-text");
    if (actionBox && actionContent) {
        if (data.abstention_status || data.required_clinician_action_notes) {
            actionBox.classList.remove("hidden");
            let htmlNotes = `<strong>Action Required:</strong> ${data.abstention_reason || "Criteria clarification required."}<br><br>`;
            htmlNotes += `${data.required_clinician_action_notes || ""}`;
            actionContent.innerHTML = htmlNotes;
        } else {
            actionBox.classList.add("hidden");
        }
    }

    // 4. Cryptographic Hash
    const hashDisp = document.getElementById("audit-hash-display");
    if (hashDisp) hashDisp.textContent = data.audit_hash;

    // 4b. CMS Billing & Medical Coding Verification Panel
    renderBillingCompliancePanel(data);

    // 4c. Longitudinal Clinical Timeline & Waiting Period Panel
    renderTimelineAnalysisPanel(data);

    // 5. Synchronized Evidence Highlight Rendering
    renderSynchronizedEHRViewer(data);

    // 6. Criteria Breakdown Cards
    renderCriteriaCards(data);

    // 7. Load & Activate Filled Coverage Packet for Review
    loadAndShowCoveragePacket(data.case_id);
}

async function loadAndShowCoveragePacket(caseId) {
    try {
        const res = await fetch(`/api/v1/packet/${caseId}`);
        if (res.ok) {
            currentCoveragePacket = await res.json();
            const banner = document.getElementById("packet-action-banner");
            if (banner) {
                banner.classList.remove("hidden");
                const title = document.getElementById("packet-banner-title");
                if (title) title.textContent = `CMS Coverage Document Auto-Filled [${currentCoveragePacket.policy_id}]`;
            }
        }
    } catch (e) {
        console.warn("Could not load coverage packet:", e);
    }
}

function renderSynchronizedEHRViewer(data) {
    const container = document.getElementById("ehr-highlight-display");
    if (!container) return;
    const rawText = data.sanitized_ehr_text;
    if (!rawText) return;

    // Collect all valid spans across criteria
    let spansToHighlight = [];
    data.criterion_assessments.forEach((crit, critIdx) => {
        crit.verified_spans.forEach((span, spanIdx) => {
            if (span.start_char >= 0 && span.end_char <= rawText.length && span.start_char < span.end_char) {
                spansToHighlight.push({
                    start: span.start_char,
                    end: span.end_char,
                    text: span.source_text,
                    criterion_code: crit.criterion_code,
                    critIdx: critIdx,
                    spanIdx: spanIdx
                });
            }
        });
    });

    if (spansToHighlight.length === 0) {
        container.textContent = rawText;
        return;
    }

    // Sort spans by start_char ascending
    spansToHighlight.sort((a, b) => a.start - b.start);

    // Build non-overlapping HTML chunks
    let html = "";
    let currentPos = 0;

    for (let s of spansToHighlight) {
        if (s.start < currentPos) continue; // skip overlap for display safety

        // Text before span
        html += escapeHtml(rawText.slice(currentPos, s.start));

        // Highlighted span
        const spanText = escapeHtml(rawText.slice(s.start, s.end));
        html += `<mark class="highlighted-span" id="span-hl-${s.critIdx}-${s.spanIdx}" data-crit-code="${s.criterion_code}" title="Evidence for ${s.criterion_code} [${s.start}:${s.end}]">${spanText}</mark>`;

        currentPos = s.end;
    }

    // Trailing text
    if (currentPos < rawText.length) {
        html += escapeHtml(rawText.slice(currentPos));
    }

    container.innerHTML = html;
}

function renderCriteriaCards(data) {
    const container = document.getElementById("criteria-cards-list");
    if (!container) return;
    container.innerHTML = "";

    data.criterion_assessments.forEach((crit, idx) => {
        const card = document.createElement("div");

        let statusClass = "insufficient";
        let statusBadgeClass = "badge-status insufficient";
        let statusText = "Needs Review";
        let statusHint = "Missing or unconfirmed in note";

        if (crit.is_exclusion) {
            // EXCLUSION CRITERIA:
            // If the exclusion is NOT present (status == "NOT_MET"), patient is NOT excluded -> Qualifies (Green PASS)
            // If the exclusion IS present (status == "MET"), patient IS excluded -> Disqualified (Red EXCLUDED)
            if (crit.status === "NOT_MET") {
                statusClass = "met";
                statusBadgeClass = "badge-status met";
                statusText = "Passed (No Exclusion)";
                statusHint = "No disqualifying conditions found";
            } else if (crit.status === "MET") {
                statusClass = "not-met";
                statusBadgeClass = "badge-status not-met";
                statusText = "Disqualified (Exclusion Met)";
                statusHint = "Disqualifying condition is present in note";
            } else {
                statusClass = "insufficient";
                statusBadgeClass = "badge-status insufficient";
                statusText = "Needs Review";
                statusHint = "Exclusion status unclear";
            }
        } else {
            // MANDATORY INCLUSION CRITERIA:
            // Must be MET to qualify
            if (crit.status === "MET") {
                statusClass = "met";
                statusBadgeClass = "badge-status met";
                statusText = "Met";
                statusHint = "Verified in note";
            } else if (crit.status === "NOT_MET") {
                statusClass = "not-met";
                statusBadgeClass = "badge-status not-met";
                statusText = "Not Met";
                statusHint = "Requirement not fulfilled";
            } else {
                statusClass = "insufficient";
                statusBadgeClass = "badge-status insufficient";
                statusText = "Needs Review";
                statusHint = "Missing or unconfirmed in note";
            }
        }

        card.className = `criterion-card compact status-${statusClass}`;
        card.id = `crit-card-${idx}`;

        const displayName = crit.name ? `${idx + 1}. ${crit.name}` : `${idx + 1}. ${crit.criterion_code}`;

        let summaryEvidence = "";
        let verifiedQuotesList = "";
        if (crit.verified_spans && crit.verified_spans.length > 0) {
            summaryEvidence = `<span class="crit-evidence-quote">“${escapeHtml(crit.verified_spans[0].source_text)}”</span>`;
            verifiedQuotesList = crit.verified_spans.map(s => `
                <div class="evidence-quote-box">
                    <div class="quote-text">“${escapeHtml(s.source_text)}”</div>
                    <div class="quote-meta">Section: <strong>${escapeHtml(s.clinical_section || 'Clinical Note')}</strong> (Characters ${s.start_char}&ndash;${s.end_char})</div>
                </div>
            `).join("");
        } else {
            summaryEvidence = `<span class="crit-evidence-missing">Not documented in note</span>`;
            verifiedQuotesList = `
                <div class="missing-alert-box">
                    <strong>Missing Documentation:</strong> No supporting statement or diagnostic finding was identified for this requirement in the patient's note.
                </div>
            `;
        }

        // If not met or insufficient, explain what is needed or missing
        let missingNotice = "";
        if (crit.is_exclusion) {
            if (crit.status === "MET") {
                missingNotice = `
                    <div class="missing-guidance-box">
                        <div class="missing-guidance-header">
                            <span class="med-icon icon-xs icon-amber">
                                <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                            </span>
                            <strong>Disqualification Warning:</strong>
                        </div>
                        <p>${escapeHtml(crit.description || 'This is a disqualifying exclusion criterion.')}</p>
                    </div>
                `;
            } else if (crit.status === "NOT_MET") {
                missingNotice = `
                    <div class="missing-guidance-box" style="background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.25);">
                        <div class="missing-guidance-header" style="color: #6EE7B7;">
                            <span class="med-icon icon-xs icon-green">
                                <svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>
                            </span>
                            <strong>Exclusion Condition Absent:</strong>
                        </div>
                        <p style="color: var(--text-secondary);">Patient has no documented terminal illness or active cardiogenic shock. This absence qualifies the patient under Medicare guidelines.</p>
                    </div>
                `;
            }
        } else if (crit.status !== "MET") {
            missingNotice = `
                <div class="missing-guidance-box">
                    <div class="missing-guidance-header">
                        <span class="med-icon icon-xs icon-amber">
                            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                        </span>
                        <strong>What is needed for approval:</strong>
                    </div>
                    <p>${escapeHtml(crit.description || 'Detailed clinical justification matching policy terms.')}</p>
                </div>
            `;
        }

        card.onclick = () => openCriterionModal(idx);

        let actionButtonsHtml = "";
        if (crit.verified_spans && crit.verified_spans.length > 0) {
            const firstSpan = crit.verified_spans[0];
            actionButtonsHtml += `
                <button type="button" class="btn-crit-pill btn-quote-pill" title="Jump to exact quote in patient chart" onclick="event.stopPropagation(); highlightQuoteInEHR(${firstSpan.start_char}, ${firstSpan.end_char}, '${escapeHtml(crit.criterion_code)}')">
                    <span class="med-icon icon-xxs"><svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg></span>
                    Quote
                </button>
            `;
        }
        if (statusClass !== "met" && !crit.is_exclusion) {
            actionButtonsHtml += `
                <button type="button" class="btn-crit-pill btn-resolve-pill" title="Supply missing clinical fact to satisfy this criterion" onclick="event.stopPropagation(); openAddendumModalForCriterion('${escapeHtml(crit.criterion_code)}', '${escapeHtml(crit.name || crit.criterion_code)}', '${escapeHtml(crit.description || '')}')">
                    <span class="med-icon icon-xxs"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg></span>
                    Resolve
                </button>
            `;
        }

        card.innerHTML = `
            <div class="criterion-header-compact">
                <div class="criterion-title-wrap">
                    <span class="${statusBadgeClass}">${statusText}</span>
                    <span class="criterion-name-text">${escapeHtml(displayName)}</span>
                </div>
                <div class="criterion-header-right">
                    ${actionButtonsHtml}
                    <span class="criterion-click-hint">Inspect</span>
                    <span class="toggle-indicator">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>
                    </span>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

function openCriterionModal(idx) {
    if (!lastAdjudicationResult || !lastAdjudicationResult.criterion_assessments) return;
    const crit = lastAdjudicationResult.criterion_assessments[idx];
    if (!crit) return;

    const modal = document.getElementById("criterion-detail-modal");
    if (!modal) return;

    // Status badge
    const badge = document.getElementById("modal-crit-status-badge");
    const codeElem = document.getElementById("modal-crit-code");
    const titleElem = document.getElementById("modal-crit-title");
    const condElem = document.getElementById("modal-crit-condition");
    const timingRow = document.getElementById("modal-crit-timing-row");
    const timingVal = document.getElementById("modal-crit-timing");
    const ratElem = document.getElementById("modal-crit-rationale");
    const missingElem = document.getElementById("modal-crit-missing-notice");
    const evidenceElem = document.getElementById("modal-crit-evidence-container");

    const displayName = crit.name ? `${idx + 1}. ${crit.name}` : `${idx + 1}. ${crit.criterion_code}`;
    if (titleElem) titleElem.textContent = displayName;
    if (codeElem) codeElem.textContent = crit.criterion_code;

    // Badge styling & text
    let statusBadgeClass = "badge-status insufficient";
    let statusText = "Needs Review";

    if (crit.is_exclusion) {
        if (crit.status === "NOT_MET") {
            statusBadgeClass = "badge-status met";
            statusText = "Passed (No Exclusion)";
        } else if (crit.status === "MET") {
            statusBadgeClass = "badge-status not-met";
            statusText = "Disqualified (Exclusion Met)";
        }
    } else {
        if (crit.status === "MET") {
            statusBadgeClass = "badge-status met";
            statusText = "Met";
        } else if (crit.status === "NOT_MET") {
            statusBadgeClass = "badge-status not-met";
            statusText = "Not Met";
        }
    }

    if (badge) {
        badge.className = statusBadgeClass;
        badge.textContent = statusText;
    }

    // Condition
    if (condElem) condElem.textContent = crit.description || crit.name;

    // Timing
    if (timingRow && timingVal) {
        if (crit.required_temporal_window && crit.required_temporal_window !== "Not specified") {
            timingRow.classList.remove("hidden");
            timingVal.textContent = crit.required_temporal_window;
        } else {
            timingRow.classList.add("hidden");
        }
    }

    // Rationale
    if (ratElem) ratElem.textContent = crit.clinical_rationale || "Evaluation verified against patient documentation.";

    // Missing guidance / Warning
    if (missingElem) {
        missingElem.innerHTML = "";
        if (crit.is_exclusion) {
            if (crit.status === "MET") {
                missingElem.innerHTML = `
                    <div class="missing-guidance-box">
                        <div class="missing-guidance-header">
                            <span class="med-icon icon-xs icon-amber">
                                <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                            </span>
                            <strong>Disqualification Warning:</strong>
                        </div>
                        <p>${escapeHtml(crit.description || 'This is a disqualifying exclusion condition.')}</p>
                    </div>
                `;
            } else if (crit.status === "NOT_MET") {
                missingElem.innerHTML = `
                    <div class="missing-guidance-box" style="background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.25);">
                        <div class="missing-guidance-header" style="color: #6EE7B7;">
                            <span class="med-icon icon-xs icon-green">
                                <svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>
                            </span>
                            <strong>Exclusion Condition Absent:</strong>
                        </div>
                        <p style="color: var(--text-secondary);">Patient has no documented terminal illness or active cardiogenic shock. This qualifies the patient under Medicare guidelines.</p>
                    </div>
                `;
            }
        } else if (crit.status !== "MET") {
            missingElem.innerHTML = `
                <div class="missing-guidance-box">
                    <div class="missing-guidance-header">
                        <span class="med-icon icon-xs icon-amber">
                            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                        </span>
                        <strong>What is needed for approval:</strong>
                    </div>
                    <p>${escapeHtml(crit.description || 'Detailed clinical justification matching policy terms.')}</p>
                </div>
            `;
        }
    }

    // Person's Record Evidence
    if (evidenceElem) {
        if (crit.verified_spans && crit.verified_spans.length > 0) {
            evidenceElem.innerHTML = crit.verified_spans.map(s => `
                <div class="evidence-quote-box modal-quote-box">
                    <div class="quote-text">“${escapeHtml(s.source_text)}”</div>
                    <div class="quote-meta">
                        <span>EHR Section: <strong>${escapeHtml(s.clinical_section || 'Clinical Note')}</strong></span>
                        <span class="meta-sep">&bull;</span>
                        <span>Character Range: <strong>${s.start_char}&ndash;${s.end_char}</strong></span>
                        <span class="meta-sep">&bull;</span>
                        <span>Exact Citation Grounding: <strong style="color: var(--accent-green);">100%</strong></span>
                    </div>
                </div>
            `).join("");
        } else {
            evidenceElem.innerHTML = `
                <div class="missing-alert-box">
                    <strong>No Documentation Found in Record:</strong> No matching diagnostic measurements, medications, or clinical statements were found in the patient's note for this criterion.
                </div>
            `;
        }
    }

    modal.classList.remove("hidden");
}

function closeCriterionModal() {
    const modal = document.getElementById("criterion-detail-modal");
    if (modal) modal.classList.add("hidden");
}

function highlightCriterionSpans(critIdx, critCode) {
    // Highlight card
    document.querySelectorAll(".criterion-card").forEach(c => c.classList.remove("active-crit"));
    const card = document.getElementById(`crit-card-${critIdx}`);
    if (card) card.classList.add("active-crit");

    // Highlight text in viewer if present
    document.querySelectorAll(".highlighted-span").forEach(s => s.classList.remove("active-highlight"));
    const matchingSpans = document.querySelectorAll(`[data-crit-code="${critCode}"]`);
    if (matchingSpans.length > 0) {
        matchingSpans.forEach(m => m.classList.add("active-highlight"));
        matchingSpans[0].scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
}

function copyAuditHash() {
    const hash = document.getElementById("audit-hash-display").textContent;
    if (!hash || hash.includes("Awaiting")) return;
    navigator.clipboard.writeText(hash).then(() => {
        showToast("SHA-256 Chain-of-Custody seal copied to clipboard.");
    });
}

// =============================================================================
// AUDIT LEDGER
// =============================================================================
async function loadAuditLogs() {
    try {
        // Enforce RBAC privacy banner & control visibility
        const bannerElem = document.getElementById("audit-role-privacy-banner");
        const purgeAllBtn = document.getElementById("btn-purge-all-audit");

        if (purgeAllBtn) {
            purgeAllBtn.style.display = (currentRole === "Admin") ? "inline-flex" : "none";
        }

        if (bannerElem) {
            if (currentRole === "Admin") {
                bannerElem.style.background = "rgba(245, 158, 11, 0.12)";
                bannerElem.style.border = "1px solid rgba(245, 158, 11, 0.35)";
                bannerElem.style.color = "#fbbf24";
                bannerElem.innerHTML = `
                    <span class="med-icon icon-sm" style="flex-shrink: 0;"><svg viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg></span>
                    <div>
                        <strong> HIPAA Minimum Necessary Standard (45 CFR § 164.502(b)):</strong>
                        You are authenticated as an <em>IT Administrator</em>. In accordance with clinical data minimization, clinical narratives, diagnostic quotes, and medical rationales are <strong>REDACTED</strong>. Only operational metadata (Case ID, Policy, Decision, Latency, and SHA-256 seal) is displayed.
                    </div>
                `;
            } else if (currentRole === "Auditor") {
                bannerElem.style.background = "rgba(6, 182, 212, 0.12)";
                bannerElem.style.border = "1px solid rgba(6, 182, 212, 0.35)";
                bannerElem.style.color = "#67e8f9";
                bannerElem.innerHTML = `
                    <span class="med-icon icon-sm" style="flex-shrink: 0;"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg></span>
                    <div>
                        <strong> CMS RAC/MAC Regulatory Auditor Oversight:</strong>
                        Authorized for forensic inspection. Full character-grounded clinical quotes, offsets, calibration scores, and SHA-256 cryptographic verification seals are displayed. Direct patient PHI is masked (<code>PT-***</code>) under HIPAA Safe Harbor. Audit logs are immutable; deletion and purging controls are disabled.
                    </div>
                `;
            } else {
                bannerElem.style.background = "rgba(16, 185, 129, 0.12)";
                bannerElem.style.border = "1px solid rgba(16, 185, 129, 0.35)";
                bannerElem.style.color = "#6ee7b7";
                bannerElem.innerHTML = `
                    <span class="med-icon icon-sm" style="flex-shrink: 0;"><svg viewBox="0 0 24 24"><path d="M22 12h-4l-3 9L9 3l-3 9H2"></path></svg></span>
                    <div>
                        <strong> Licensed Clinician Mode:</strong>
                        Viewing prior authorization determinations for clinical care delivery and peer-to-peer appeal documentation.
                    </div>
                `;
            }
        }

        const res = await fetch("/api/v1/audit-logs?limit=25", {
            headers: currentToken ? { "Authorization": `Bearer ${currentToken}` } : {}
        });
        if (res.ok) {
            const logs = await res.json();
            const tbody = document.getElementById("audit-table-body");
            tbody.innerHTML = "";

            if (logs.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 24px;">No adjudication audit logs recorded yet. Ephemeral zero-retention mode is active.</td></tr>`;
                return;
            }

            logs.forEach(log => {
                const tr = document.createElement("tr");
                const ts = new Date(log.created_at).toLocaleString();
                const shortHash = log.audit_hash.slice(0, 16) + "...";
                let decisionChip = `<span class="badge-status not-met">${escapeHtml(log.decision)}</span>`;
                if (log.decision === "APPROVED") decisionChip = `<span class="badge-status met">${escapeHtml(log.decision)}</span>`;
                else if (log.decision === "DEFERRED_TO_HUMAN") decisionChip = `<span class="badge-status insufficient">${escapeHtml(log.decision)}</span>`;

                let patientCellContent = escapeHtml(log.patient_id_masked);
                if (currentRole === "Admin") {
                    patientCellContent += ` <span class="badge-status insufficient" style="font-size: 0.72rem; padding: 2px 6px;">Metadata Only</span>`;
                }

                let actionsCell = "";
                if (currentRole === "Auditor") {
                    actionsCell = `
                        <button type="button" class="btn-batch-action" style="padding: 4px 10px; font-size: 0.75rem;" title="Inspect Forensic Evidence & Offsets" onclick="viewAuditRecordDetails('${escapeHtml(log.case_id)}')">
                            <span class="med-icon icon-xs"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg></span>
                            <span>Inspect</span>
                        </button>
                    `;
                } else if (currentRole === "Admin") {
                    actionsCell = `
                        <div style="display:inline-flex;align-items:center;gap:6px;">
                            <button type="button" class="btn-batch-action" style="padding: 4px 10px; font-size: 0.75rem;" title="Inspect Technical Metadata" onclick="viewAuditRecordDetails('${escapeHtml(log.case_id)}')">
                                <span class="med-icon icon-xs"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg></span>
                                <span>Inspect</span>
                            </button>
                            <button type="button" class="btn-icon-subtle" title="Purge Record (System Maintenance)" onclick="deleteSingleAuditRecord('${escapeHtml(log.case_id)}')">
                                <span class="med-icon icon-sm text-red"><svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></span>
                            </button>
                        </div>
                    `;
                } else {
                    actionsCell = `
                        <button type="button" class="btn-batch-action" style="padding: 4px 10px; font-size: 0.75rem;" title="View Adjudication Summary" onclick="viewAuditRecordDetails('${escapeHtml(log.case_id)}')">
                            <span class="med-icon icon-xs"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg></span>
                            <span>Inspect</span>
                        </button>
                    `;
                }

                tr.innerHTML = `
                    <td class="mono-cell">${ts}</td>
                    <td class="mono-cell" style="color: var(--accent-cyan); font-weight: 600; cursor: pointer;" title="Click to inspect audit record" onclick="viewAuditRecordDetails('${escapeHtml(log.case_id)}')"><span style="border-bottom: 1px dashed rgba(56, 189, 248, 0.4);">${escapeHtml(log.case_id)}</span></td>
                    <td class="mono-cell">${patientCellContent}</td>
                    <td><strong>${escapeHtml(log.policy_id)}</strong></td>
                    <td>${decisionChip}</td>
                    <td class="mono-cell">${log.abstention_status ? "<strong style='color: var(--accent-amber);'>YES</strong>" : "NO"}</td>
                    <td class="mono-cell">${(log.calibrated_confidence * 100).toFixed(1)}%</td>
                    <td class="mono-cell" title="${escapeHtml(log.audit_hash)}" style="cursor: pointer;" onclick="copySpecificHash('${escapeHtml(log.audit_hash)}')">
                        <span style="border-bottom: 1px dotted var(--accent-cyan);">${shortHash}</span>
                    </td>
                    <td>${actionsCell}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (e) {
        console.error("Failed to load audit logs:", e);
    }
}

window._activeAuditRecord = null;

function closeAuditDetailModal() {
    const modal = document.getElementById("audit-detail-modal");
    if (modal) modal.classList.add("hidden");
}

function copyModalAuditHash() {
    if (!window._activeAuditRecord || !window._activeAuditRecord.audit_hash) return;
    navigator.clipboard.writeText(window._activeAuditRecord.audit_hash).then(() => {
        showToast("Copied full SHA-256 seal to clipboard.", "success");
    }).catch(() => {
        showToast("Unable to copy SHA-256 seal.", "error");
    });
}

function copyCaseIdToClipboard() {
    if (!window._activeAuditRecord || !window._activeAuditRecord.case_id) return;
    navigator.clipboard.writeText(window._activeAuditRecord.case_id).then(() => {
        showToast(`Copied case ID ${window._activeAuditRecord.case_id} to clipboard.`, "success");
    }).catch(() => {
        showToast("Unable to copy case ID.", "error");
    });
}

async function viewAuditRecordDetails(caseId) {
    try {
        const res = await fetch(`/api/v1/audit-logs/${encodeURIComponent(caseId)}`, {
            headers: currentToken ? { "Authorization": `Bearer ${currentToken}` } : {}
        });
        if (!res.ok) {
            showToast("Failed to fetch record details", "error");
            return;
        }
        const data = await res.json();
        window._activeAuditRecord = data;

        // Modal Header Case ID
        const caseIdEl = document.getElementById("audit-modal-case-id");
        if (caseIdEl) caseIdEl.textContent = data.case_id;

        // Hero Card & Decision Badge
        const heroCard = document.getElementById("audit-hero-card");
        const decBadgeEl = document.getElementById("audit-hero-decision-badge");
        if (heroCard) {
            heroCard.className = "audit-hero-card";
            if (data.decision === "APPROVED") heroCard.classList.add("hero-approved");
            else if (data.decision === "DENIED") heroCard.classList.add("hero-denied");
            else heroCard.classList.add("hero-deferred");
        }

        if (decBadgeEl) {
            if (data.decision === "APPROVED") {
                decBadgeEl.innerHTML = `<span class="decision-pill approved"><span class="decision-dot"></span> Approved</span>`;
            } else if (data.decision === "DENIED") {
                decBadgeEl.innerHTML = `<span class="decision-pill denied"><span class="decision-dot"></span> Denied</span>`;
            } else {
                decBadgeEl.innerHTML = `<span class="decision-pill deferred"><span class="decision-dot"></span> Deferred to MD</span>`;
            }
        }

        // Confidence
        const confNumEl = document.getElementById("audit-modal-conf-num");
        if (confNumEl) {
            confNumEl.textContent = `${Math.round(data.calibrated_confidence * 100)}%`;
        }

        // Policy & Patient Metadata
        const polEl = document.getElementById("audit-modal-policy-title");
        if (polEl) {
            const spec = getPolicySpecialty(data.policy_id);
            polEl.textContent = `${data.policy_id} (${spec})`;
        }

        const patEl = document.getElementById("audit-modal-patient-id");
        if (patEl) patEl.textContent = data.patient_id_masked || "PT-***";

        const gateEl = document.getElementById("audit-modal-gate-text");
        if (gateEl) {
            gateEl.textContent = data.abstention_status ? "Abstention Triggered" : "Safety Gate Passed";
            gateEl.style.color = data.abstention_status ? "#FBBF24" : "#34D399";
        }

        // Clinical Narrative / Rationale
        const narrEl = document.getElementById("audit-modal-narrative");
        if (narrEl) {
            if (currentRole === "Admin" && data.sanitized_ehr_preview && data.sanitized_ehr_preview.includes("REDACTED")) {
                narrEl.textContent = "Clinical narrative is redacted under HIPAA Minimum Necessary (45 CFR 164.502(b)). Only operational audit metadata is accessible to IT Administrators.";
            } else {
                narrEl.textContent = data.sanitized_ehr_preview || "Clinical evaluation completed against statutory Medicare policy criteria.";
            }
        }

        // Criteria Checklist (Simple & uncluttered)
        const critListEl = document.getElementById("audit-modal-criteria-list");
        if (critListEl) {
            critListEl.innerHTML = "";
            let criteriaList = [];
            try {
                if (data.criterion_evaluations_json) {
                    criteriaList = JSON.parse(data.criterion_evaluations_json);
                }
            } catch (err) {
                console.warn("Could not parse criterion_evaluations_json:", err);
            }

            if (criteriaList && criteriaList.length > 0) {
                criteriaList.forEach(crit => {
                    const row = document.createElement("div");
                    row.className = "audit-criterion-row";
                    
                    const statusStr = (crit.status || (crit.satisfied ? "MET" : "NOT_MET")).toUpperCase();
                    let stChip = `<span class="badge-status not-met" style="padding:2px 8px;font-size:0.72rem;">Not Met</span>`;
                    if (statusStr === "MET") {
                        stChip = `<span class="badge-status met" style="padding:2px 8px;font-size:0.72rem;">Met</span>`;
                    } else if (statusStr === "EXCLUDED") {
                        stChip = `<span class="badge-status excluded" style="padding:2px 8px;font-size:0.72rem;">Excluded</span>`;
                    } else if (statusStr === "INSUFFICIENT" || statusStr.includes("DEFER")) {
                        stChip = `<span class="badge-status insufficient" style="padding:2px 8px;font-size:0.72rem;">Review</span>`;
                    }

                    row.innerHTML = `
                        <div class="audit-crit-info">
                            <span class="audit-crit-code">${escapeHtml(crit.criterion_code)}</span>
                            <span class="audit-crit-title" title="${escapeHtml(crit.name || crit.criterion_code)}">${escapeHtml(crit.name || crit.criterion_code)}</span>
                        </div>
                        <div>${stChip}</div>
                    `;
                    critListEl.appendChild(row);
                });
            } else {
                critListEl.innerHTML = `<div style="font-size:0.78rem;color:var(--text-muted);padding:6px;">No specific statutory criteria flags logged.</div>`;
            }
        }

        // Direct Chart Evidence (Only show if available)
        const evidSection = document.getElementById("audit-evidence-section");
        const evidBox = document.getElementById("audit-modal-evidence-box");
        let spansList = [];
        try {
            if (data.evidence_spans_json) {
                spansList = JSON.parse(data.evidence_spans_json);
            }
        } catch (err) {
            console.warn("Could not parse evidence_spans_json:", err);
        }

        if (spansList && spansList.length > 0 && evidSection && evidBox) {
            evidSection.style.display = "";
            evidBox.innerHTML = "";
            spansList.slice(0, 2).forEach(sp => {
                const quoteText = sp.text || sp.quote || sp.exact_quote || "";
                const codeText = sp.criterion_code || sp.code || "Requirement";
                const startChar = typeof sp.start_char === "number" ? sp.start_char : 0;
                const endChar = typeof sp.end_char === "number" ? sp.end_char : 0;

                const qDiv = document.createElement("div");
                qDiv.style.marginBottom = "6px";
                qDiv.innerHTML = `
                    <div class="audit-quote-text">"${escapeHtml(quoteText)}"</div>
                    <div class="audit-quote-sub">Referenced for <strong>${escapeHtml(codeText)}</strong> (Offset: [${startChar}-${endChar}])</div>
                `;
                evidBox.appendChild(qDiv);
            });
        } else if (evidSection) {
            evidSection.style.display = "none";
        }

        // SHA-256 Short Hash
        const hashShortEl = document.getElementById("audit-modal-hash-short");
        if (hashShortEl) {
            hashShortEl.textContent = data.audit_hash ? `${data.audit_hash.slice(0, 24)}...` : "--";
        }

        // Show Modal
        const modal = document.getElementById("audit-detail-modal");
        if (modal) modal.classList.remove("hidden");

    } catch (e) {
        console.error("Error displaying audit record:", e);
        showToast("Error retrieving audit record: " + e.message, "error");
    }
}


async function deleteSingleAuditRecord(caseId) {
    if (!confirm(`Permanently purge audit log for case ${caseId}? This action fulfills HIPAA Right-to-Erasure.`)) {
        return;
    }
    try {
        const res = await fetch(`/api/v1/audit-logs/${encodeURIComponent(caseId)}`, {
            method: "DELETE",
            headers: currentToken ? { "Authorization": `Bearer ${currentToken}` } : {}
        });
        if (res.ok) {
            showToast(`Purged audit log for case ${caseId}.`);
            loadAuditLogs();
        } else {
            const err = await res.json();
            showToast(`Purge failed: ${err.detail || res.statusText}`, true);
        }
    } catch (e) {
        showToast("Error deleting record: " + e.message, true);
    }
}

async function purgeAllAuditRecords() {
    if (!confirm("Are you sure you want to purge all unsubmitted and test audit records? This permanently clears cached records.")) {
        return;
    }
    try {
        const res = await fetch("/api/v1/audit-logs/purge/all", {
            method: "DELETE",
            headers: currentToken ? { "Authorization": `Bearer ${currentToken}` } : {}
        });
        if (res.ok) {
            const data = await res.json();
            showToast(data.message || "All audit records permanently purged.");
            loadAuditLogs();
            const termsModal = document.getElementById("terms-modal");
            if (termsModal && !termsModal.classList.contains("hidden")) {
                closeTermsModal();
            }
        } else {
            const err = await res.json();
            showToast(`Purge failed: ${err.detail || res.statusText}`, true);
        }
    } catch (e) {
        showToast("Error purging records: " + e.message, true);
    }
}

function copySpecificHash(hash) {
    navigator.clipboard.writeText(hash).then(() => {
        showToast("Copied SHA-256 seal: " + hash.slice(0, 16) + "...");
    });
}

// =============================================================================
// 4-CONFIGURATION RESEARCH BENCHMARK LAB
// =============================================================================
async function runLiveBenchmark() {
    const btn = document.getElementById("run-bench-btn");
    btn.disabled = true;
    btn.innerHTML = `<span class="btn-icon">&#8987;</span> Running 4-Config Benchmark Suite...`;

    try {
        const res = await fetch("/api/v1/benchmark/run", { method: "POST" });
        if (res.ok) {
            const data = await res.json();
            updateBenchmarkMetrics(data);
            showToast("Benchmark suite executed successfully across 4 configurations.");
        } else {
            showToast("Benchmark execution failed", true);
        }
    } catch (e) {
        showToast("Error running benchmark: " + e.message, true);
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span class="btn-icon">&#9881;</span> Run Benchmark Suite`;
    }
}

function updateBenchmarkMetrics(data) {
    const cfgs = data.configs;
    const a = cfgs.find(c => c.config_name === "Config A") || {};
    const b = cfgs.find(c => c.config_name === "Config B") || {};
    const c = cfgs.find(c => c.config_name === "Config C") || {};
    const d = cfgs.find(c => c.config_name === "Config D") || {};

    if (a.accuracy !== undefined) {
        const elAcc = document.getElementById("ba-acc");
        const elFaith = document.getElementById("ba-faith");
        const elEce = document.getElementById("ba-ece");
        if (elAcc) elAcc.textContent = `${(a.accuracy * 100).toFixed(1)}%`;
        if (elFaith) elFaith.textContent = `${(a.evidence_faithfulness * 100).toFixed(1)}%`;
        if (elEce) elEce.textContent = a.expected_calibration_error.toFixed(3);
    }
    if (b.accuracy !== undefined) {
        const elAcc = document.getElementById("bb-acc");
        const elFaith = document.getElementById("bb-faith");
        const elEce = document.getElementById("bb-ece");
        if (elAcc) elAcc.textContent = `${(b.accuracy * 100).toFixed(1)}%`;
        if (elFaith) elFaith.textContent = `${(b.evidence_faithfulness * 100).toFixed(1)}%`;
        if (elEce) elEce.textContent = b.expected_calibration_error.toFixed(3);
    }
    if (c.accuracy !== undefined) {
        const elAcc = document.getElementById("bc-acc");
        const elFaith = document.getElementById("bc-faith");
        const elEce = document.getElementById("bc-ece");
        if (elAcc) elAcc.textContent = `${(c.accuracy * 100).toFixed(1)}%`;
        if (elFaith) elFaith.textContent = `${(c.evidence_faithfulness * 100).toFixed(1)}%`;
        if (elEce) elEce.textContent = c.expected_calibration_error.toFixed(3);
    }
    if (d.accuracy !== undefined) {
        const elAcc = document.getElementById("bd-acc");
        const elFaith = document.getElementById("bd-faith");
        const elEce = document.getElementById("bd-ece");
        if (elAcc) elAcc.textContent = `${(d.accuracy * 100).toFixed(1)}%`;
        if (elFaith) elFaith.textContent = `${(d.evidence_faithfulness * 100).toFixed(1)}%`;
        if (elEce) elEce.textContent = d.expected_calibration_error.toFixed(3);
    }

    if (data.comparative_analysis) {
        const narr = document.getElementById("benchmark-narrative");
        if (narr) narr.textContent = data.comparative_analysis;
    }

    // Populate the 10-Vignette Breakdown Table
    const tableBody = document.getElementById("benchmark-vignettes-body");
    if (tableBody && data.vignette_results && data.vignette_results.length > 0) {
        tableBody.innerHTML = data.vignette_results.map(v => {
            const formatDec = (dec, isGold = false, isBaseline = false) => {
                if (isBaseline && dec === "APPROVED" && v.gold_decision !== "APPROVED") {
                    return `<span class="badge-status not-met" style="font-size: 0.72rem;" title="False Approval! High-liability citation error.">️ False Approval</span>`;
                }
                if (dec === "APPROVED") {
                    return `<span class="badge-status met" style="font-size: 0.72rem;"><span class="chip-dot"></span> Approved</span>`;
                } else if (dec === "DENIED") {
                    return `<span class="badge-status not-met" style="font-size: 0.72rem;"><span class="chip-dot"></span> Denied</span>`;
                } else if (dec === "DEFERRED_TO_HUMAN") {
                    return `<span class="badge-status insufficient" style="font-size: 0.72rem;"><span class="chip-dot"></span> Deferred</span>`;
                }
                return `<span class="badge-role-tag">${escapeHtml(dec)}</span>`;
            };

            return `
                <tr>
                    <td><strong>${escapeHtml(v.vignette_id)}</strong></td>
                    <td><span class="code-pill">${escapeHtml(v.policy_id)}</span></td>
                    <td>
                        <div style="font-weight: 600; color: var(--text-primary);">${escapeHtml(v.name)}</div>
                    </td>
                    <td><span class="text-secondary" style="font-size: 0.8rem;">${escapeHtml(v.clinical_domain)}</span></td>
                    <td>${formatDec(v.gold_decision, true)}</td>
                    <td>${formatDec(v.config_a_decision, false, true)}</td>
                    <td>${formatDec(v.config_b_decision, false, true)}</td>
                    <td>${formatDec(v.config_c_decision, false, false)}</td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 6px;">
                            ${formatDec(v.config_d_decision, false, false)}
                            <span class="tag-conf" style="font-size: 0.7rem; color: #34D399; font-weight: 700;">${(v.config_d_confidence * 100).toFixed(0)}%</span>
                        </div>
                    </td>
                    <td>
                        <span class="badge-status met" style="font-size: 0.72rem; padding: 2px 6px;">
                            ${v.config_d_grounded ? " 100% Grounded" : "Mismatch"}
                        </span>
                    </td>
                </tr>
            `;
        }).join("");
    }
}

// =============================================================================
// UTILITIES
// =============================================================================
function showToast(message, isError = false) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.style.borderColor = isError ? "var(--accent-red)" : "var(--accent-cyan)";
    toast.classList.remove("hidden");
    setTimeout(() => {
        toast.classList.add("hidden");
    }, 3200);
}

function escapeHtml(string) {
    const entityMap = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    };
    return String(string).replace(/[&<>"']/g, s => entityMap[s]);
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// =============================================================================
// DOCTOR'S NOTE UPLOAD & PRE-SUBMISSION COVERAGE PACKET WORKFLOW
// =============================================================================

function setupUploadDropzone() {
    const dropzone = document.getElementById("upload-dropzone");
    if (!dropzone) return;

    ["dragenter", "dragover"].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.style.borderColor = "var(--accent-cyan)";
            dropzone.style.background = "rgba(6, 182, 212, 0.12)";
        }, false);
    });

    ["dragleave", "drop"].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.style.borderColor = "#3B82F6";
            dropzone.style.background = "rgba(59, 130, 246, 0.04)";
        }, false);
    });

    dropzone.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            uploadFileAndAdjudicate(files[0]);
        }
    }, false);
}

function handleFileUpload(event) {
    const file = event.target.files[0];
    if (file) {
        uploadFileAndAdjudicate(file);
    }
}

async function uploadFileAndAdjudicate(file) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("patient_id", document.getElementById("patient-id-input").value.trim() || "PT-DOC-UPLOAD");
    formData.append("policy_id", "auto");
    const tau = parseFloat(document.getElementById("tau-input").value) || 0.85;
    formData.append("tau", tau);

    // Update UI if elements exist
    const mainText = document.getElementById("upload-main-text");
    const subText = document.getElementById("upload-sub-text");
    const statusChip = document.getElementById("upload-status-chip");
    if (mainText) mainText.textContent = `Uploaded: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    if (subText) subText.textContent = `Parsing clinical entities and auto-retrieving Medicare policy...`;
    if (statusChip) statusChip.textContent = "Processing Multi-Agent Pipeline...";

    // Run stepper animations
    animateStep("retrieval", "SEARCHING", "active");
    await sleep(200);

    try {
        const res = await fetch("/api/v1/upload-note", {
            method: "POST",
            body: formData
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || `Server error ${res.status}`);
        }

        const data = await res.json();
        
        // Populate extracted text into EHR textarea and visible pastebox
        document.getElementById("ehr-input").value = data.extracted_text;
        const pasteBox = document.getElementById("actual-paste-textarea");
        if (pasteBox) pasteBox.value = data.extracted_text;
        
        // Auto-select matched policy
        const matchedPolicyId = data.adjudication.policy_id;
        const policySelect = document.getElementById("policy-select");
        if (policySelect) {
            policySelect.value = matchedPolicyId;
        }

        // Stepper updates
        animateStep("retrieval", `MATCHED: ${matchedPolicyId}`, "completed");
        animateStep("evaluator", "EXTRACTED", "completed");
        animateStep("verifier", "VERIFIED", "completed");
        animateStep("abstention", data.adjudication.abstention_status ? "ABSTAINED" : "DECIDED", "completed");

        // Render results
        lastAdjudicationResult = data.adjudication;
        currentCoveragePacket = data.packet;
        renderAdjudicationResults(data.adjudication);

        const uploadChip = document.getElementById("upload-status-chip");
        if (uploadChip) uploadChip.textContent = `Auto-Matched ${matchedPolicyId}`;
        showToast(`Document parsed! Governing policy: ${matchedPolicyId}. Coverage check complete.`);
        
        updatePolicyStep2Preview();
        updateWorkflowRibbon(3);
        goToWizardScreen(3);
    } catch (e) {
        console.error("Upload error:", e);
        showToast("Document upload failed: " + e.message, true);
        resetStepper();
    }
}

// =============================================================================
// OFFICIAL CMS COVERAGE PACKET REVIEW & TRANSMISSION MODALS
// =============================================================================

function openPacketReviewModal() {
    goToWizardScreen(3);
}

function closePacketReviewModal() {
    goToWizardScreen(2);
}

function populatePacketDocument() {
    if (!currentCoveragePacket && lastAdjudicationResult) {
        loadAndShowCoveragePacket(lastAdjudicationResult.case_id);
    }

    if (!currentCoveragePacket) return;

    const p = currentCoveragePacket;

    // Header values
    const docPacketId = document.getElementById("doc-packet-id");
    const docPatientId = document.getElementById("doc-patient-id");
    const docDos = document.getElementById("doc-dos");
    const docPolicyId = document.getElementById("doc-policy-id");
    const docJurisdiction = document.getElementById("doc-jurisdiction");

    if (docPacketId) docPacketId.textContent = p.packet_id;
    if (docPatientId) docPatientId.textContent = p.patient_id_masked;
    if (docDos) docDos.textContent = p.date_of_service;
    if (docPolicyId) docPolicyId.textContent = `${p.policy_id} - ${p.policy_title}`;
    if (docJurisdiction) docJurisdiction.textContent = p.jurisdiction;

    // Status chip
    const statusChip = document.getElementById("doc-packet-status-chip");
    if (statusChip) {
        if (p.submission_status === "SUBMITTED_TO_PAYER") {
            statusChip.textContent = `STATUS: SUBMITTED (${p.payer_transaction_id || "ACCEPTED"})`;
            statusChip.style.color = "var(--accent-green)";
        } else if (p.abstention_status) {
            statusChip.textContent = "STATUS: DOCTOR REVIEW REQUIRED (ABSTAINED)";
            statusChip.style.color = "var(--accent-amber)";
        } else {
            statusChip.textContent = "STATUS: DRAFT REVIEW - READY FOR TRANSMISSION";
            statusChip.style.color = "var(--accent-cyan)";
        }
    }

    // ICD-10 Chips
    const icdContainer = document.getElementById("doc-icd-chips");
    if (icdContainer) {
        icdContainer.innerHTML = p.icd10_codes.map(c => `<span class="code-pill">${c}</span>`).join("");
    }

    // CPT Chips
    const cptContainer = document.getElementById("doc-cpt-chips");
    if (cptContainer) {
        cptContainer.innerHTML = p.cpt_hcpcs_codes.map(c => `<span class="code-pill">${c}</span>`).join("");
    }

    // Criteria Table - Plain Clean Medical Table
    const tbody = document.getElementById("doc-criteria-tbody");
    if (tbody) {
        tbody.innerHTML = "";
        p.criteria_sections.forEach((c, cIdx) => {
            const tr = document.createElement("tr");
            let statusText = "MET";
            let statusColor = "#166534";
            if (c.status === "NOT_MET") {
                statusText = "NOT MET";
                statusColor = "#991B1B";
            } else if (c.status === "INSUFFICIENT_EVIDENCE") {
                statusText = "REVIEW";
                statusColor = "#B45309";
            }

            tr.innerHTML = `
                <td>
                    <div class="table-req-title">${escapeHtml(c.name || c.criterion_code)}</div>
                    <div class="table-req-sub">${escapeHtml(c.criterion_code)}${c.required_temporal_window ? ` &bull; ${escapeHtml(c.required_temporal_window)}` : ''}</div>
                </td>
                <td style="font-weight: 700; color: ${statusColor}; text-align: center;">
                    ${statusText}
                </td>
                <td>
                    <div class="table-plain-evidence">“${escapeHtml(c.extracted_evidence_quote || 'Not documented in record')}”</div>
                </td>
                <td>
                    <input type="text" class="document-plain-input" id="doc-attest-${cIdx}" value="${escapeHtml(c.physician_attestation || 'Verified per patient clinical consultation record.')}">
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    // Clinical Summary (textarea)
    const clinicalSummary = document.getElementById("doc-clinical-summary");
    if (clinicalSummary) {
        clinicalSummary.value = p.clinical_summary || "";
    }

    // CMS Statutory Mandates & Validity Window
    const docValidity = document.getElementById("doc-validity-period");
    if (docValidity) {
        docValidity.textContent = p.authorization_validity_period || "180 Calendar Days";
    }
    const docSdm = document.getElementById("doc-sdm-text");
    if (docSdm) {
        docSdm.textContent = p.shared_decision_making_attestation || "Documented clinical consultation conducted pursuant to CMS Medicare Coverage Determination.";
    }

    // Physician Signature Input (Populate with detected doctor name if present)
    const sigInput = document.getElementById("doc-physician-signature");
    if (sigInput) {
        const ehrText = document.getElementById("ehr-input")?.value || "";
        const auth = checkNoteAuthenticity(ehrText);
        if (auth.has_doctor_name && auth.doctor_name) {
            sigInput.value = auth.doctor_name;
        } else if (p.signed_by) {
            sigInput.value = p.signed_by;
        }
    }

    // Signature Date
    const sigDate = document.getElementById("doc-signature-date");
    if (sigDate) {
        sigDate.textContent = p.date_of_service || new Date().toISOString().split("T")[0];
    }

    // Cryptographic Seal
    const docSealHash = document.getElementById("doc-seal-hash");
    if (docSealHash) docSealHash.textContent = p.audit_hash;

    // Denial & Exclusion Safeguard: Block Medicare Submission if Excluded
    const exclusionBanner = document.getElementById("step4-exclusion-warning-banner");
    const submitBtn = document.getElementById("btn-final-submit-insurance");
    const step4Title = document.getElementById("step4-screen-title");
    const step4Sub = document.getElementById("step4-screen-subtext");
    const isDenied = (lastAdjudicationResult && lastAdjudicationResult.adjudication_decision === "DENIED") || (p.decision === "DENIED");

    if (isDenied) {
        if (exclusionBanner) exclusionBanner.classList.remove("hidden");
        if (step4Title) step4Title.textContent = "Medicare Clinical Coverage Denial Advisory";
        if (step4Sub) step4Sub.textContent = "Coverage is excluded by Medicare criteria. Under CMS regulations, this document is restricted to internal hospital review and peer-to-peer appeal preparation.";
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.classList.add("btn-disabled-blocked");
            submitBtn.innerHTML = `
                <span class="med-icon icon-sm"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line></svg></span>
                Submission Blocked &mdash; Excluded by CMS Policy
            `;
            submitBtn.title = "Under Federal False Claims Act rules (31 U.S.C. §§ 3729-3733), an excluded prior authorization claim cannot be transmitted to Medicare.";
        }
    } else {
        if (exclusionBanner) exclusionBanner.classList.add("hidden");
        if (step4Title) step4Title.textContent = "Prior Authorization Packet";
        if (step4Sub) step4Sub.textContent = "This is the official Medicare prior authorization document that will be submitted directly to the insurance payer.";
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.classList.remove("btn-disabled-blocked");
            submitBtn.innerHTML = `
                Sign & Submit to Medicare
                <span class="med-icon icon-sm"><svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg></span>
            `;
            submitBtn.title = "Sign and submit this verified prior authorization packet directly to Medicare Part B.";
        }
    }
}

async function submitPacketToInsurance() {
    if (!currentCoveragePacket) return;

    if (lastAdjudicationResult && lastAdjudicationResult.adjudication_decision === "DENIED") {
        showToast("Submission Blocked: This patient's condition is excluded under Medicare policy. Excluded treatments cannot be submitted for prior authorization.", true);
        return;
    }

    if (currentRole === "Auditor") {
        showToast("Auditor access is read-only: Transmitting and signing prior-authorization packets to insurance requires an authenticated Verified Clinician.", true);
        return;
    }

    const certifyCheck = document.getElementById("doc-certify-check");
    if (certifyCheck && !certifyCheck.checked) {
        showToast("Please certify the clinical necessity check before transmitting.", true);
        return;
    }

    const sigInput = document.getElementById("doc-physician-signature");
    const signerName = (sigInput && sigInput.value.trim()) || "Dr. Sarah Jenkins, MD, FACC";
    const notesInput = document.getElementById("doc-clinical-summary");
    const clinicianNotes = notesInput ? notesInput.value.trim() : (currentCoveragePacket.clinical_summary || "");

    const submitBtn = document.getElementById("btn-final-submit-insurance");
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `Transmitting to Medicare Clearinghouse...`;
    }

    try {
        const res = await fetch("/api/v1/packet/submit", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(currentToken ? { "Authorization": `Bearer ${currentToken}` } : {})
            },
            body: JSON.stringify({
                case_id: currentCoveragePacket.case_id,
                signed_by: signerName,
                clinician_notes: clinicianNotes,
                payer_name: "CMS Medicare Part B / Regional MAC"
            })
        });

        if (!res.ok) {
            throw new Error(`Submission failed with status ${res.status}`);
        }

        const receipt = await res.json();

        // Update current packet status
        currentCoveragePacket.submission_status = "SUBMITTED_TO_PAYER";
        currentCoveragePacket.payer_transaction_id = receipt.payer_transaction_id;
        currentCoveragePacket.signed_by = signerName;

        // Render receipt details on Screen 5 and advance
        showSubmissionReceipt(receipt);
        goToWizardScreen(5);

        // Refresh audit ledger
        loadAuditLogs();
        showToast("Packet successfully signed and submitted to Medicare!");
    } catch (e) {
        console.error("Submission failed:", e);
        showToast("Submission failed: " + e.message, true);
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = `
                Sign & Submit to Medicare
                <span class="med-icon icon-sm"><svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg></span>
            `;
        }
    }
}

function showSubmissionReceipt(receipt) {
    const payerElem = document.getElementById("receipt-payer");
    const txElem = document.getElementById("receipt-tx-id");
    const caseElem = document.getElementById("receipt-case-id");
    const signerElem = document.getElementById("receipt-signer");
    const timeElem = document.getElementById("receipt-timestamp");
    const hashElem = document.getElementById("receipt-hash");

    if (payerElem) payerElem.textContent = receipt.payer_name;
    if (txElem) txElem.textContent = receipt.payer_transaction_id;
    if (caseElem) caseElem.textContent = receipt.case_id;
    if (signerElem) signerElem.textContent = receipt.signed_by;
    if (timeElem) timeElem.textContent = new Date(receipt.signed_at).toLocaleString();
    if (hashElem) hashElem.textContent = receipt.audit_hash;
}

function closeReceiptModal() {
    goToWizardScreen(1);
}

function printPacketDocument() {
    if (!currentCoveragePacket) {
        showToast("No active coverage packet to print.", true);
        return;
    }

    const p = currentCoveragePacket;
    const patientId = p.patient_id_masked || "PT-UNKNOWN";
    const dos = p.date_of_service || new Date().toISOString().split("T")[0];
    const policy = `${p.policy_id || ''} - ${p.policy_title || ''}`;
    const jurisdiction = p.jurisdiction || "National / Regional MAC";
    const packetId = p.packet_id || "CMS-PAC-2026-FORM";
    const icdCodes = (p.icd10_codes || []).join(", ") || "None specified";
    const cptCodes = (p.cpt_hcpcs_codes || []).join(", ") || "None specified";
    
    // Read current user edits from on-screen fields
    const summaryElem = document.getElementById("doc-clinical-summary");
    const clinicalSummary = summaryElem ? summaryElem.value.trim() : (p.clinical_summary || "");
    const sigElem = document.getElementById("doc-physician-signature");
    const signature = sigElem ? sigElem.value.trim() : (p.signed_by || "Attesting Physician, MD");
    const auditHash = p.audit_hash || "SECURE-VERIFIED-HASH";

    // Build criteria rows
    let criteriaRows = "";
    (p.criteria_sections || []).forEach((c, idx) => {
        const attestInput = document.getElementById(`doc-attest-${idx}`);
        const userAttest = attestInput ? attestInput.value.trim() : (c.physician_attestation || "Verified against clinical documentation.");
        
        let statusText = "MET";
        let statusColor = "#15803D";
        if (c.status === "NOT_MET") {
            statusText = "NOT MET";
            statusColor = "#B91C1C";
        } else if (c.status === "INSUFFICIENT_EVIDENCE") {
            statusText = "REVIEW";
            statusColor = "#B45309";
        }

        criteriaRows += `
            <tr style="border-bottom: 1px solid #D1D5DB;">
                <td style="padding: 8px 10px; vertical-align: top; width: 28%;">
                    <div style="font-weight: 700; color: #111827; font-size: 13px;">${escapeHtml(c.name || c.criterion_code)}</div>
                    <div style="font-size: 11px; color: #6B7280; font-family: monospace; margin-top: 2px;">${escapeHtml(c.criterion_code)}${c.required_temporal_window ? ` &bull; ${escapeHtml(c.required_temporal_window)}` : ''}</div>
                </td>
                <td style="padding: 8px 10px; vertical-align: top; width: 12%; text-align: center; font-weight: 700; color: ${statusColor}; font-size: 12px;">
                    ${statusText}
                </td>
                <td style="padding: 8px 10px; vertical-align: top; width: 40%; font-size: 12px; color: #1F2937; line-height: 1.45;">
                    “${escapeHtml(c.extracted_evidence_quote || 'Not documented in record')}”
                </td>
                <td style="padding: 8px 10px; vertical-align: top; width: 20%; font-size: 12px; color: #374151;">
                    ${escapeHtml(userAttest)}
                </td>
            </tr>
        `;
    });

    const printHtml = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CMS Prior Authorization Request - ${escapeHtml(patientId)}</title>
    <style>
        @page {
            size: letter portrait;
            margin: 18mm 18mm 18mm 18mm;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            color: #111827;
            background: #FFFFFF;
            margin: 0;
            padding: 0;
            font-size: 13px;
            line-height: 1.45;
        }
        .header-table {
            width: 100%;
            border-bottom: 2px solid #0F172A;
            padding-bottom: 12px;
            margin-bottom: 16px;
        }
        .header-title {
            font-size: 16px;
            font-weight: 800;
            color: #0F172A;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }
        .header-sub {
            font-size: 13px;
            font-weight: 600;
            color: #4B5563;
            margin-top: 2px;
        }
        .form-id-badge {
            text-align: right;
            font-family: monospace;
            font-size: 12px;
            font-weight: 700;
            color: #1F2937;
        }
        .section-header {
            font-size: 12px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #0F172A;
            border-bottom: 1px solid #111827;
            padding-bottom: 4px;
            margin-top: 18px;
            margin-bottom: 8px;
        }
        .grid-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 12px;
        }
        .grid-table td {
            padding: 4px 6px;
            vertical-align: top;
            font-size: 12.5px;
        }
        .field-label {
            font-weight: 600;
            color: #4B5563;
            font-size: 11px;
            text-transform: uppercase;
        }
        .field-value {
            font-weight: 600;
            color: #111827;
        }
        .criteria-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 6px;
            margin-bottom: 14px;
        }
        .criteria-table th {
            border-bottom: 1.5px solid #111827;
            border-top: 1px solid #D1D5DB;
            text-align: left;
            padding: 6px 8px;
            font-size: 11.5px;
            font-weight: 700;
            color: #374151;
            text-transform: uppercase;
        }
        .narrative-block {
            background: #F9FAFB;
            border: 1px solid #E5E7EB;
            padding: 10px 12px;
            font-size: 12.5px;
            line-height: 1.5;
            color: #1F2937;
            margin-bottom: 14px;
            white-space: pre-wrap;
        }
        .attestation-box {
            border: 1px solid #9CA3AF;
            background: #FAFAFA;
            padding: 12px 14px;
            margin-top: 12px;
        }
        .attestation-text {
            font-size: 11.5px;
            color: #374151;
            line-height: 1.45;
        }
        .signature-table {
            width: 100%;
            margin-top: 16px;
            border-collapse: collapse;
        }
        .signature-table td {
            vertical-align: bottom;
            padding: 6px 0;
        }
        .sig-line {
            border-bottom: 1px solid #111827;
            padding-bottom: 2px;
            font-weight: 700;
            font-size: 13px;
        }
        .seal-footer {
            margin-top: 24px;
            padding-top: 8px;
            border-top: 1px dashed #D1D5DB;
            font-family: monospace;
            font-size: 10px;
            color: #6B7280;
            display: flex;
            justify-content: space-between;
        }
    </style>
</head>
<body>
    <table class="header-table">
        <tr>
            <td>
                <div class="header-title">Centers for Medicare &amp; Medicaid Services (CMS)</div>
                <div class="header-sub">Medicare Part B Prior Authorization Request Form</div>
            </td>
            <td class="form-id-badge">
                FORM ID: ${escapeHtml(packetId)}<br>
                <span style="font-weight: normal; font-size: 11px; color: #6B7280;">Electronic Standard 837P / 278</span>
            </td>
        </tr>
    </table>

    <div class="section-header">Section A: Patient &amp; Coverage Information</div>
    <table class="grid-table">
        <tr>
            <td style="width: 25%;">
                <div class="field-label">Patient ID</div>
                <div class="field-value">${escapeHtml(patientId)}</div>
            </td>
            <td style="width: 25%;">
                <div class="field-label">Date of Service</div>
                <div class="field-value">${escapeHtml(dos)}</div>
            </td>
            <td style="width: 30%;">
                <div class="field-label">Governing Policy</div>
                <div class="field-value">${escapeHtml(policy)}</div>
            </td>
            <td style="width: 20%;">
                <div class="field-label">MAC Jurisdiction</div>
                <div class="field-value">${escapeHtml(jurisdiction)}</div>
            </td>
        </tr>
    </table>

    <div class="section-header">Section B: Medical Billing &amp; Diagnostic Coding</div>
    <table class="grid-table">
        <tr>
            <td style="width: 50%;">
                <div class="field-label">Diagnosis Codes (ICD-10-CM)</div>
                <div class="field-value" style="font-family: monospace;">${escapeHtml(icdCodes)}</div>
            </td>
            <td style="width: 50%;">
                <div class="field-label">Procedure / Service Codes (CPT &amp; HCPCS)</div>
                <div class="field-value" style="font-family: monospace;">${escapeHtml(cptCodes)}</div>
            </td>
        </tr>
    </table>

    <div class="section-header">Section C: Policy Coverage Criteria Verification &amp; Extracted Clinical Citations</div>
    <table class="criteria-table">
        <thead>
            <tr>
                <th>Medicare Requirement</th>
                <th style="text-align: center;">Status</th>
                <th>Evidence Cited From Medical Record</th>
                <th>Physician Attestation</th>
            </tr>
        </thead>
        <tbody>
            ${criteriaRows}
        </tbody>
    </table>

    <div class="section-header">Section D: Clinical Necessity &amp; Justification Summary</div>
    <div class="narrative-block">${escapeHtml(clinicalSummary || "Patient meets all specified clinical criteria under governing Medicare guidelines. Clinical chart supports procedure necessity.")}</div>

    <div class="section-header">Section E: Attesting Physician Certification &amp; Legal Sign-Off</div>
    <div class="attestation-box">
        <div class="attestation-text">
            <strong>Statutory Certification:</strong> I certify that I am the treating physician for this patient and that the clinical observations, diagnostic findings, and procedure justifications documented above are authentic and medically accurate. I understand that submitting false or misleading information to Medicare or Medicaid constitutes a violation of the Federal False Claims Act (31 U.S.C. &sect;&sect; 3729&ndash;3733).
        </div>
        <table class="signature-table">
            <tr>
                <td style="width: 60%;">
                    <div class="field-label">Attesting Physician Signature</div>
                    <div class="sig-line">${escapeHtml(signature)}</div>
                </td>
                <td style="width: 10%;"></td>
                <td style="width: 30%;">
                    <div class="field-label">Certification Date</div>
                    <div class="sig-line">${escapeHtml(dos)}</div>
                </td>
            </tr>
        </table>
    </div>

    <div class="seal-footer">
        <span>CMS Tamper-Evident SHA-256 Audit Seal: ${escapeHtml(auditHash)}</span>
        <span>Generated by CarePolicyGuard &bull; In-Memory HIPAA Safe Harbor</span>
    </div>

    <script>
        window.onload = function() {
            window.print();
        };
    </script>
</body>
</html>
    `;

    const printWindow = window.open("", "_blank");
    if (!printWindow) {
        showToast("Popup blocked. Please allow popups to print/save the document.", true);
        return;
    }

    printWindow.document.open();
    printWindow.document.write(printHtml);
    printWindow.document.close();
}




// =============================================================================
// PEER-TO-PEER APPEAL LETTER & FHIR EHR INTEROPERABILITY
// =============================================================================

let currentAppealLetter = null;
let currentFhirBundle = null;

async function openPeerToPeerAppealModal() {
    if (!lastAdjudicationResult && !currentCoveragePacket) {
        showToast("Please evaluate a clinical note first.", true);
        return;
    }

    const caseId = (currentCoveragePacket && currentCoveragePacket.case_id) || (lastAdjudicationResult && lastAdjudicationResult.case_id);
    const doctorName = (currentCoveragePacket && currentCoveragePacket.signed_by) || (document.getElementById("doc-physician-signature")?.value) || "Dr. Sarah Jenkins, MD, FACC";

    showToast("Generating formal Peer-to-Peer Appeal Letter & clinical talking points...", "info");

    try {
        const res = await fetch(`/api/v1/packet/${caseId}/appeal-letter`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(currentToken ? { "Authorization": `Bearer ${currentToken}` } : {})
            },
            body: JSON.stringify({
                case_id: caseId,
                physician_name: doctorName,
                physician_npi: "1043256787",
                physician_specialty: "Cardiology / Internal Medicine"
            })
        });

        if (!res.ok) throw new Error(`Failed to generate appeal letter: ${res.status}`);

        const data = await res.json();
        currentAppealLetter = data;

        // Render talking points
        const tpList = document.getElementById("appeal-talking-points-list");
        if (tpList) {
            tpList.innerHTML = data.peer_to_peer_talking_points.map(tp => `<li>${escapeHtml(tp)}</li>`).join("");
        }

        // Render full letter text
        const textElem = document.getElementById("appeal-letter-fulltext");
        if (textElem) {
            textElem.textContent = data.full_letter_text;
        }

        const modal = document.getElementById("appeal-letter-modal");
        if (modal) modal.classList.remove("hidden");
    } catch (e) {
        console.error("Appeal generation error:", e);
        showToast("Could not generate appeal letter: " + e.message, true);
    }
}

function closePeerToPeerAppealModal() {
    const modal = document.getElementById("appeal-letter-modal");
    if (modal) modal.classList.add("hidden");
}

function copyAppealLetterToClipboard() {
    if (!currentAppealLetter) return;
    navigator.clipboard.writeText(currentAppealLetter.full_letter_text).then(() => {
        showToast("Appeal letter copied to clipboard!", "success");
    }).catch(() => {
        showToast("Failed to copy text. Please select and copy manually.", true);
    });
}

function printAppealLetter() {
    if (!currentAppealLetter) return;
    const printWindow = window.open("", "_blank");
    if (!printWindow) {
        showToast("Popup blocked. Please allow popups to print.", true);
        return;
    }
    printWindow.document.open();
    printWindow.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>Peer-to-Peer Appeal Letter - ${escapeHtml(currentAppealLetter.appeal_id)}</title>
            <style>
                body { font-family: monospace; white-space: pre-wrap; margin: 40px; font-size: 13px; line-height: 1.5; color: #000; }
            </style>
        </head>
        <body>${escapeHtml(currentAppealLetter.full_letter_text)}<script>window.onload = function() { window.print(); };</script></body>
        </html>
    `);
    printWindow.document.close();
}

async function exportFhirBundle() {
    if (!lastAdjudicationResult && !currentCoveragePacket) {
        showToast("Please evaluate a clinical note first.", true);
        return;
    }

    const caseId = (currentCoveragePacket && currentCoveragePacket.case_id) || (lastAdjudicationResult && lastAdjudicationResult.case_id);
    showToast("Generating HL7 FHIR R4 Da Vinci PAS Bundle...", "info");

    try {
        const res = await fetch(`/api/v1/packet/${caseId}/fhir`);
        if (!res.ok) throw new Error(`FHIR export failed: ${res.status}`);

        const bundle = await res.json();
        currentFhirBundle = bundle;

        const codeElem = document.getElementById("fhir-bundle-json-display");
        if (codeElem) {
            codeElem.textContent = JSON.stringify(bundle, null, 2);
        }

        const modal = document.getElementById("fhir-bundle-modal");
        if (modal) modal.classList.remove("hidden");
    } catch (e) {
        console.error("FHIR export error:", e);
        showToast("FHIR export failed: " + e.message, true);
    }
}

function closeFhirModal() {
    const modal = document.getElementById("fhir-bundle-modal");
    if (modal) modal.classList.add("hidden");
}

function copyFhirJsonToClipboard() {
    if (!currentFhirBundle) return;
    navigator.clipboard.writeText(JSON.stringify(currentFhirBundle, null, 2)).then(() => {
        showToast("HL7 FHIR JSON copied to clipboard!", "success");
    }).catch(() => {
        showToast("Failed to copy. Please select and copy manually.", true);
    });
}

function downloadFhirJsonFile() {
    if (!currentFhirBundle) return;
    const jsonStr = JSON.stringify(currentFhirBundle, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `fhir-pas-bundle-${currentFhirBundle.id || "export"}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast("Downloaded HL7 FHIR JSON bundle!");
}

async function pushToHospitalEhr() {
    if (!lastAdjudicationResult && !currentCoveragePacket) {
        showToast("Please evaluate a clinical note first.", true);
        return;
    }

    const caseId = (currentCoveragePacket && currentCoveragePacket.case_id) || (lastAdjudicationResult && lastAdjudicationResult.case_id);
    showToast("Connecting to Hospital EHR (Epic Hyperdrive / FHIR Gateway)...", "info");

    try {
        const res = await fetch(`/api/v1/packet/${caseId}/ehr-push`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(currentToken ? { "Authorization": `Bearer ${currentToken}` } : {})
            },
            body: JSON.stringify({
                case_id: caseId,
                ehr_system: "Epic Systems Hyperdrive / FHIR R4 Endpoint"
            })
        });

        if (!res.ok) throw new Error(`EHR sync failed: ${res.status}`);

        const receipt = await res.json();
        showToast(`EHR Synchronized! Stored under Epic Document ID: ${receipt.ehr_document_id}`, "success");
    } catch (e) {
        console.error("EHR sync error:", e);
        showToast("EHR sync failed: " + e.message, true);
    }
}


// =============================================================================
// CMS BILLING, CLINICAL TIMELINE & SMART DEFICIENCY ADDENDUM HELPERS
// =============================================================================

function renderBillingCompliancePanel(data) {
    const panel = document.getElementById("billing-compliance-panel");
    if (!panel) return;

    const billing = data.billing_validation;
    if (!billing) {
        panel.classList.add("hidden");
        return;
    }

    panel.classList.remove("hidden");
    const badge = document.getElementById("billing-status-badge");
    const cptDisplay = document.getElementById("billing-cpt-display");
    const icdDisplay = document.getElementById("billing-icd-display");
    const advisoryElem = document.getElementById("billing-advisory-text");
    const carcContainer = document.getElementById("billing-carc-pills");

    if (badge) {
        if (billing.is_billing_compliant) {
            badge.className = "billing-status-badge badge-green";
            badge.textContent = "Codes Compliant (ANSI X12 PAS)";
        } else {
            badge.className = "billing-status-badge badge-red";
            badge.textContent = "Billing Code Warning";
        }
    }

    if (cptDisplay) {
        if (billing.detected_cpt_codes && billing.detected_cpt_codes.length > 0) {
            cptDisplay.innerHTML = billing.detected_cpt_codes.map(c => `
                <div class="code-entry ${c.status === 'COVERED' ? 'code-covered' : 'code-uncovered'}">
                    <strong>${escapeHtml(c.code)}</strong> &ndash; ${escapeHtml(c.description)}
                    <span class="code-status-tag ${c.status === 'COVERED' ? 'tag-covered' : 'tag-uncovered'}">${c.status}</span>
                </div>
            `).join("");
        } else {
            cptDisplay.innerHTML = `<span class="text-muted">Standard policy procedure code inferred</span>`;
        }
    }

    if (icdDisplay) {
        if (billing.detected_icd10_codes && billing.detected_icd10_codes.length > 0) {
            icdDisplay.innerHTML = billing.detected_icd10_codes.map(i => `
                <div class="code-entry ${i.status === 'COVERED' ? 'code-covered' : 'code-uncovered'}">
                    <strong>${escapeHtml(i.code)}</strong> &ndash; ${escapeHtml(i.description)}
                    <span class="code-status-tag ${i.status === 'COVERED' ? 'tag-covered' : 'tag-uncovered'}">${i.status}</span>
                </div>
            `).join("");
        } else {
            icdDisplay.innerHTML = `<span class="text-muted">Covered diagnosis inferred from clinical chart</span>`;
        }
    }

    if (advisoryElem) {
        advisoryElem.textContent = billing.billing_advisory || "";
    }

    if (carcContainer) {
        let carcHtml = "";
        const allCodes = [...(data.carc_codes || billing.carc_codes || []), ...(data.rarc_codes || billing.rarc_codes || [])];
        if (allCodes.length > 0) {
            carcHtml = allCodes.map(c => `
                <span class="carc-badge ${c.code.includes('CARC 0') || c.code.includes('MA01') ? 'carc-ok' : 'carc-warn'}" title="${escapeHtml(c.description)}">
                    ${escapeHtml(c.code)}
                </span>
            `).join("");
        }
        carcContainer.innerHTML = carcHtml;
    }
}

function renderTimelineAnalysisPanel(data) {
    const panel = document.getElementById("timeline-analysis-panel");
    if (!panel) return;

    const timeline = data.timeline_analysis;
    if (!timeline || !timeline.milestones || timeline.milestones.length === 0) {
        panel.classList.add("hidden");
        return;
    }

    panel.classList.remove("hidden");
    const badge = document.getElementById("timeline-status-badge");
    const container = document.getElementById("timeline-milestones-container");

    if (badge) {
        if (timeline.all_waiting_periods_satisfied) {
            badge.className = "timeline-status-badge badge-green";
            badge.textContent = "All Waiting Periods Satisfied";
        } else {
            badge.className = "timeline-status-badge badge-red";
            badge.textContent = "Statutory Waiting Period Deficit";
        }
    }

    if (container) {
        container.innerHTML = timeline.milestones.map(m => {
            const isOk = m.status === "SATISFIED";
            return `
                <div class="timeline-milestone-card ${isOk ? 'milestone-ok' : 'milestone-unmet'}">
                    <div class="milestone-top-row">
                        <span class="milestone-label">${escapeHtml(m.event_label)}</span>
                        <span class="milestone-badge ${isOk ? 'badge-met' : 'badge-unmet'}">
                            ${isOk ? 'Satisfied (' + m.elapsed_days + 'd &ge; ' + m.required_days + 'd)' : 'Deficit: ' + m.deficit_days + ' days remaining'}
                        </span>
                    </div>
                    <div class="milestone-calc-row">
                        <span>Event Date: <strong>${escapeHtml(m.event_date)}</strong></span>
                        <span class="meta-sep">&bull;</span>
                        <span>Evaluation Date: <strong>${escapeHtml(m.evaluation_date)}</strong></span>
                        <span class="meta-sep">&bull;</span>
                        <span>Elapsed: <strong>${m.elapsed_days} days</strong> (Medicare Mandate: &ge; ${m.required_days} days)</span>
                    </div>
                    <div class="milestone-advisory">${escapeHtml(m.advisory)}</div>
                    <div class="milestone-citation">${escapeHtml(m.citation)}</div>
                </div>
            `;
        }).join("");
    }
}

let currentTargetCriterionCode = null;
let currentSuggestedTemplate = "";

function openAddendumModalForCriterion(code, name, desc) {
    currentTargetCriterionCode = code;
    const modal = document.getElementById("addendum-modal");
    if (!modal) return;

    const labelElem = document.getElementById("addendum-criterion-label");
    const descElem = document.getElementById("addendum-criterion-desc");
    const guidanceElem = document.getElementById("addendum-guidance-text");
    const inputElem = document.getElementById("addendum-narrative-input");

    if (labelElem) labelElem.textContent = `${code}: ${name}`;
    if (descElem) descElem.textContent = desc || "Clinical criterion requirement.";

    // Configure Minimum Required Documentation per Medicare LCD/NCD guidelines
    let guidanceHtml = "";
    if (code.includes("GDMT") || code.includes("04")) {
        guidanceHtml = `
            <strong>Required Clinical Information per Policy:</strong>
            <ul>
                <li>Specific drug names &amp; dosages (e.g. ARNI / ACEi / Beta-blocker).</li>
                <li>Start date or documented duration of therapy (must document <strong>&ge; 90 days</strong>).</li>
                <li>Documentation that patient tolerated the regimen without disqualifying adverse effects.</li>
            </ul>
        `;
        currentSuggestedTemplate = "Patient has been compliant on optimal guideline-directed medical therapy ([Medication name & dose, e.g. Entresto 49/51mg BID and Carvedilol 25mg BID]) since [Date / > 90 days] with documented tolerance and no adverse effects.";
    } else if (code.includes("LVEF") || code.includes("01")) {
        guidanceHtml = `
            <strong>Required Clinical Information per Policy:</strong>
            <ul>
                <li>Diagnostic imaging modality (e.g., Transthoracic Echocardiogram, Cardiac MRI, or MUGA).</li>
                <li>Date of diagnostic study (must be within the required policy timeframe, typically 12 months).</li>
                <li>Quantitative Left Ventricular Ejection Fraction (must verify <strong>&le; 35%</strong>).</li>
            </ul>
        `;
        currentSuggestedTemplate = "Follow-up echocardiogram completed on [Date, e.g. 2026-02-10] demonstrates severe left ventricular systolic dysfunction with LVEF calculated at [Measured %, e.g. 28%] by biplane Simpson's method.";
    } else if (code.includes("AHI") || code.includes("OSA")) {
        guidanceHtml = `
            <strong>Required Clinical Information per Policy:</strong>
            <ul>
                <li>Polysomnography or Home Sleep Apnea Test report date.</li>
                <li>Apnea-Hypopnea Index (AHI) or Respiratory Disturbance Index (RDI) count (&ge; 15, or &ge; 5 with comorbidities).</li>
                <li>Documented clinical symptoms (e.g. daytime hypersomnolence, refractory hypertension).</li>
            </ul>
        `;
        currentSuggestedTemplate = "Polysomnography report dated [Date] confirms obstructive sleep apnea with an Apnea-Hypopnea Index (AHI) of [Value, e.g. 22.4] events per hour accompanied by documented daytime somnolence.";
    } else if (code.includes("HBOT") || code.includes("WOUND")) {
        guidanceHtml = `
            <strong>Required Clinical Information per Policy:</strong>
            <ul>
                <li>Exact anatomic wound location and physical ulcer depth.</li>
                <li>Wagner Grading classification (Grade 3 or 4 involving tendon, capsule, or bone).</li>
                <li>Documented failure of standard wound therapy for &ge; 30 days prior to hyperbaric oxygen evaluation.</li>
            </ul>
        `;
        currentSuggestedTemplate = "Physical examination dated [Date] confirms diabetic foot ulcer of [Anatomic location] with involvement of [tendon/bone], consistent with Wagner Grade [3 or 4]. Standard wound care was administered for > 30 days without healing response.";
    } else {
        guidanceHtml = `
            <strong>Required Clinical Information per Policy:</strong>
            <ul>
                <li>Encounter date of physical observation or diagnostic testing.</li>
                <li>Specific clinical finding, lab result, or diagnostic confirmation.</li>
                <li>Clinician attestation addressing Medicare condition: <em>${escapeHtml(desc || name)}</em>.</li>
            </ul>
        `;
        currentSuggestedTemplate = `Clinician attestation for ${name}: Documented clinical observation on [Date] confirms [Specific clinical findings satisfying Medicare condition].`;
    }

    if (guidanceElem) {
        guidanceElem.innerHTML = guidanceHtml;
    }

    // Leave the textarea empty so the physician directly types their authentic note!
    if (inputElem) {
        inputElem.value = "";
        inputElem.placeholder = "Enter authentic clinician attestation with exact patient observations, dates, and dosages...";
    }

    modal.classList.remove("hidden");
    if (inputElem) {
        setTimeout(() => inputElem.focus(), 100);
    }
}

function applySuggestedAddendumTemplate() {
    const inputElem = document.getElementById("addendum-narrative-input");
    if (!inputElem) return;
    if (inputElem.value.trim().length > 0) {
        if (!confirm("Replace current addendum draft with template starter?")) {
            return;
        }
    }
    inputElem.value = currentSuggestedTemplate;
    inputElem.focus();
}

function closeAddendumModal() {
    const modal = document.getElementById("addendum-modal");
    if (modal) modal.classList.add("hidden");
}

async function submitClinicalAddendum() {
    if (!lastAdjudicationResult) {
        showToast("No active adjudication case to amend.", true);
        return;
    }

    const inputElem = document.getElementById("addendum-narrative-input");
    const physicianElem = document.getElementById("addendum-physician-name");
    const npiElem = document.getElementById("addendum-physician-npi");

    const addendumText = inputElem ? inputElem.value.trim() : "";
    if (!addendumText || addendumText.length < 10) {
        showToast("Please enter authentic clinical observations for the patient (minimum 10 characters).", true);
        if (inputElem) inputElem.focus();
        return;
    }
    if (addendumText.includes("[") && addendumText.includes("]")) {
        showToast("Please replace bracketed placeholders (e.g. [Date], [Medication]) with actual patient clinical data.", true);
        if (inputElem) inputElem.focus();
        return;
    }

    const caseId = lastAdjudicationResult.case_id;
    const btn = document.getElementById("btn-submit-addendum");
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-small"></span> Re-Adjudicating...`;
    }

    try {
        const res = await fetch(`/api/v1/packet/${caseId}/addendum`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(currentToken ? { "Authorization": `Bearer ${currentToken}` } : {})
            },
            body: JSON.stringify({
                criterion_code: currentTargetCriterionCode,
                addendum_text: addendumText,
                clinician_name: physicianElem ? physicianElem.value : "Attending Physician",
                clinician_npi: npiElem ? npiElem.value : "1043256787"
            })
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `Addendum failed: ${res.status}`);
        }

        const respData = await res.json();
        closeAddendumModal();
        closeCriterionModal();

        // Update the active adjudication result with the newly returned one!
        lastAdjudicationResult = respData.updated_adjudication;
        populateStep3(lastAdjudicationResult);

        showToast(respData.message, "success");
    } catch (e) {
        console.error("Addendum submission error:", e);
        showToast("Failed to apply addendum: " + e.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<span class="med-icon icon-xs"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg></span> Sign Addendum &amp; Re-Adjudicate`;
        }
    }
}

function highlightQuoteInEHR(startChar, endChar, criterionCode) {
    const ehrViewer = document.getElementById("grounded-ehr-section");
    if (ehrViewer) {
        ehrViewer.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    const marks = document.querySelectorAll("#ehr-highlight-display mark");
    marks.forEach(m => m.classList.remove("pulse-focus"));

    let found = null;
    marks.forEach(m => {
        if (m.getAttribute("data-crit-code") === criterionCode) {
            found = m;
        }
    });

    if (found) {
        found.classList.add("pulse-focus");
        found.scrollIntoView({ behavior: "smooth", block: "center" });
        showToast(`Grounding quote for ${criterionCode} focused in chart!`, "info");
    } else {
        showToast(`Showing verified evidence quote for ${criterionCode}`, "info");
    }
}

function exportAuditTrailCsv() {
    window.location.href = "/api/v1/audit/trail/export";
}


// =============================================================================
// BATCH ROSTER ADJUDICATION ENGINE
// =============================================================================

const SAMPLE_BATCH_ROSTERS = {
    cardiology: [
        {
            patient_id: "PT-CARD-881",
            policy_id: "NCD-20.4",
            requested_procedure_code: "33249",
            clinical_narrative: "68-year-old male with ischemic cardiomyopathy. Prior MI in 2021 (>3 years ago). Echo on 01/10/2024 shows severe systolic dysfunction with LVEF 28%. NYHA Class II symptoms with mild dyspnea on exertion. On guideline-directed medical therapy for >6 months with Carvedilol 25mg BID, Lisinopril 20mg daily, and Spironolactone 25mg daily. No cardiogenic shock, no terminal illness."
        },
        {
            patient_id: "PT-CARD-882",
            policy_id: "NCD-20.4",
            requested_procedure_code: "33249",
            clinical_narrative: "55-year-old female post acute STEMI 12 days ago. Underwent emergency stenting. Echo demonstrates LVEF 30%. NYHA Class II. Currently in hospital recovering from acute event."
        },
        {
            patient_id: "PT-CARD-883",
            policy_id: "NCD-20.4",
            requested_procedure_code: "33249",
            clinical_narrative: "72-year-old female with dilated non-ischemic cardiomyopathy. Transthoracic echocardiogram reveals LVEF 32%. Patient reports NYHA Class III heart failure symptoms with fatigue at low workloads. Treated with GDMT including Sacubitril/Valsartan 49/51mg and Metoprolol succinate 100mg for 5 months. No acute ischemic events. Life expectancy exceeds 1 year."
        },
        {
            patient_id: "PT-CARD-884",
            policy_id: "NCD-20.4",
            requested_procedure_code: "33249",
            clinical_narrative: "61-year-old male presenting with shortness of breath and lower extremity edema. Chart mentions heart failure with reduced ejection fraction, but recent quantitative echocardiogram or radionuclide LVEF measurement report is completely missing from current hospitalization records."
        }
    ],
    mixed: [
        {
            patient_id: "PT-PULM-701",
            policy_id: "LCD-L33829",
            requested_procedure_code: "E0601",
            clinical_narrative: "52-year-old male with chronic severe snoring and witnessed apneas. Prior in-person face-to-face evaluation by Dr. Stevens documented severe daytime somnolence (Epworth 16/24). Diagnostic polysomnography performed showing severe OSA with AHI 36.4 events/hr. Recommending auto-CPAP trial."
        },
        {
            patient_id: "PT-WOUND-702",
            policy_id: "NCD-20.29",
            requested_procedure_code: "G0277",
            clinical_narrative: "64-year-old male with type 2 diabetes presenting with non-healing right plantar ulcer. Physical exam demonstrates Wagner Grade 3 diabetic foot ulcer with exposed tendon and deep abscess. Patient has undergone 45 days of standard wound care including sharp debridement and offloading without improvement. Lower extremity arterial Doppler demonstrates ABI 0.82 and palpable posterior tibial pulse."
        },
        {
            patient_id: "PT-PULM-703",
            policy_id: "NCD-240.2",
            requested_procedure_code: "E1390",
            clinical_narrative: "70-year-old female with severe end-stage COPD. Resting arterial blood gas on room air demonstrates PaO2 51 mmHg and pulse oximetry SpO2 86% at rest. Prescribing home stationary oxygen concentrator continuous 2 L/min."
        }
    ]
};

let currentBatchRoster = [];

// =============================================================================
// TAB 4: MULTI-PATIENT BATCH ROSTER ADJUDICATION
// =============================================================================

const POLICY_SPECIALTY_MAP = {
    "NCD-20.4": "Cardiology",
    "LCD-L33829": "Pulmonology",
    "NCD-20.29": "Wound Care",
    "NCD-240.2": "Pulmonology"
};

function getPolicySpecialty(policyId) {
    return POLICY_SPECIALTY_MAP[policyId] || "Medicare Part B";
}

let currentBatchCohortType = 'cardiology';
let currentBatchFilter = 'ALL';

function switchBatchCohort(cohortType) {
    currentBatchCohortType = cohortType;
    currentBatchFilter = 'ALL';
    
    const btnCardio = document.getElementById("btn-cohort-cardiology");
    const btnMixed = document.getElementById("btn-cohort-mixed");
    if (btnCardio && btnMixed) {
        if (cohortType === 'cardiology') {
            btnCardio.classList.add("active");
            btnMixed.classList.remove("active");
        } else {
            btnMixed.classList.add("active");
            btnCardio.classList.remove("active");
        }
    }
    loadSampleBatchRoster(cohortType);
}

function filterBatchTable(filterType) {
    currentBatchFilter = filterType;
    
    const pills = document.querySelectorAll(".batch-filter-pill");
    pills.forEach(pill => pill.classList.remove("active"));
    
    const targetPillId = {
        'ALL': 'filter-all',
        'APPROVED': 'filter-approved',
        'DENIED': 'filter-denied',
        'DEFERRED': 'filter-deferred'
    }[filterType] || 'filter-all';
    
    const activeEl = document.getElementById(targetPillId);
    if (activeEl) activeEl.classList.add("active");
    
    const rows = document.querySelectorAll("#batch-table-body tr");
    rows.forEach(tr => {
        const rowDecision = tr.getAttribute("data-decision") || "PENDING";
        if (filterType === 'ALL') {
            tr.style.display = "";
        } else if (filterType === 'APPROVED' && rowDecision === 'APPROVED') {
            tr.style.display = "";
        } else if (filterType === 'DENIED' && rowDecision === 'DENIED') {
            tr.style.display = "";
        } else if (filterType === 'DEFERRED' && (rowDecision === 'DEFERRED' || rowDecision === 'HOLD' || rowDecision.includes('DEFER'))) {
            tr.style.display = "";
        } else {
            tr.style.display = "none";
        }
    });
}

function loadSampleBatchRoster(rosterType) {
    window._activeBatchLoaded = true;
    currentBatchCohortType = rosterType;
    currentBatchRoster = JSON.parse(JSON.stringify(SAMPLE_BATCH_ROSTERS[rosterType] || SAMPLE_BATCH_ROSTERS.cardiology));
    
    const titleEl = document.getElementById("batch-roster-title");
    if (titleEl) {
        titleEl.textContent = rosterType === 'cardiology' 
            ? "Current Roster: Cardiology Clinic Morning Cohort (4 Patients)" 
            : "Current Roster: Mixed Specialty Outpatient Cohort (3 Patients)";
    }
    const subEl = document.getElementById("batch-cohort-name-sub");
    if (subEl) {
        subEl.textContent = rosterType === 'cardiology'
            ? "Cardiology Clinic Morning Cohort"
            : "Mixed Specialty Outpatient Cohort";
    }
    
    document.getElementById("batch-total-count").textContent = currentBatchRoster.length;
    document.getElementById("batch-approved-count").textContent = "--";
    document.getElementById("batch-denied-count").textContent = "--";
    document.getElementById("batch-deferred-count").textContent = "--";
    document.getElementById("batch-latency-count").textContent = "-- ms";
    
    renderBatchTablePending();
}

function renderBatchTablePending() {
    const tbody = document.getElementById("batch-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    currentBatchFilter = 'ALL';
    const pills = document.querySelectorAll(".batch-filter-pill");
    pills.forEach(pill => pill.classList.remove("active"));
    const allPill = document.getElementById("filter-all");
    if (allPill) allPill.classList.add("active");

    const totalEl = document.getElementById("filter-count-all");
    if (totalEl) totalEl.textContent = currentBatchRoster.length;
    const appEl = document.getElementById("filter-count-approved");
    if (appEl) appEl.textContent = "0";
    const denEl = document.getElementById("filter-count-denied");
    if (denEl) denEl.textContent = "0";
    const defEl = document.getElementById("filter-count-deferred");
    if (defEl) defEl.textContent = "0";

    currentBatchRoster.forEach((item, idx) => {
        const tr = document.createElement("tr");
        tr.setAttribute("data-decision", "PENDING");
        
        const snippet = item.clinical_narrative.length > 95 
            ? item.clinical_narrative.substring(0, 95) + "..." 
            : item.clinical_narrative;
        const specialty = getPolicySpecialty(item.policy_id);

        tr.innerHTML = `
            <td><strong style="color:var(--text-muted);">#${idx + 1}</strong></td>
            <td>
                <div class="patient-chip">
                    <span class="patient-avatar-mini">PT</span>
                    <span>${escapeHtml(item.patient_id)}</span>
                </div>
            </td>
            <td>
                <div class="policy-tag-badge">
                    <span class="policy-code-pill">${escapeHtml(item.policy_id)}</span>
                    <span class="policy-specialty-sub">${escapeHtml(specialty)}</span>
                </div>
            </td>
            <td><span class="procedure-cpt-pill">${escapeHtml(item.requested_procedure_code || 'N/A')}</span></td>
            <td><div class="clinical-snippet-box">${escapeHtml(snippet)}</div></td>
            <td>
                <span class="decision-pill pending">
                    <span class="decision-dot"></span>
                    Pending Run
                </span>
            </td>
            <td><span style="color:var(--text-muted);font-size:0.75rem;">--</span></td>
            <td><span style="color:var(--text-muted);font-size:0.75rem;">--</span></td>
            <td style="text-align: right;">
                <button type="button" class="btn-batch-action" onclick="loadRosterItemIntoWizard(${idx})">
                    <span>Inspect Note</span>
                    <span style="font-size:0.8rem;">&rarr;</span>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

async function executeBatchAdjudication() {
    if (!currentBatchRoster || currentBatchRoster.length === 0) {
        loadSampleBatchRoster('cardiology');
    }

    const btn = document.getElementById("btn-run-batch-adjudication");
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="med-icon icon-sm spinning"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-linecap="round"></circle></svg></span> Adjudicating Roster...`;

    try {
        const payload = {
            batch_name: document.getElementById("batch-roster-title").textContent,
            items: currentBatchRoster
        };

        const res = await fetch("/api/v1/adjudicate/batch", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(currentToken ? { "Authorization": `Bearer ${currentToken}` } : {})
            },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            throw new Error(`Batch adjudication failed: ${res.statusText}`);
        }

        const data = await res.json();
        
        // Update summary metrics
        document.getElementById("batch-total-count").textContent = data.total_patients;
        document.getElementById("batch-approved-count").textContent = data.approved_count;
        document.getElementById("batch-denied-count").textContent = data.denied_count;
        document.getElementById("batch-deferred-count").textContent = data.deferred_count;
        document.getElementById("batch-latency-count").textContent = `${data.processing_time_ms} ms`;

        renderBatchResults(data.results);
        showToast(`Batch completed: ${data.approved_count} Approved, ${data.denied_count} Denied, ${data.deferred_count} Deferred.`, "success");

    } catch (err) {
        console.error("Batch error:", err);
        showToast(`Batch execution failed: ${err.message}`, "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

function renderBatchResults(results) {
    const tbody = document.getElementById("batch-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    let approvedCount = 0;
    let deniedCount = 0;
    let deferredCount = 0;

    results.forEach((item) => {
        const tr = document.createElement("tr");
        const decisionNorm = (item.decision || "PENDING").toUpperCase();
        tr.setAttribute("data-decision", decisionNorm);

        if (decisionNorm === "APPROVED") approvedCount++;
        else if (decisionNorm === "DENIED") deniedCount++;
        else deferredCount++;

        const snippet = item.adjudication.sanitized_ehr_text.length > 95 
            ? item.adjudication.sanitized_ehr_text.substring(0, 95) + "..." 
            : item.adjudication.sanitized_ehr_text;

        const specialty = getPolicySpecialty(item.policy_id);
        const cptCode = item.adjudication.cpt_codes && item.adjudication.cpt_codes.length > 0 
            ? item.adjudication.cpt_codes[0] 
            : (item.requested_procedure_code || 'N/A');

        let decisionBadge = "";
        if (decisionNorm === "APPROVED") {
            decisionBadge = `
                <span class="decision-pill approved">
                    <span class="decision-dot"></span>
                    Approved
                </span>
            `;
        } else if (decisionNorm === "DENIED") {
            decisionBadge = `
                <span class="decision-pill denied">
                    <span class="decision-dot"></span>
                    Denied
                </span>
            `;
        } else {
            decisionBadge = `
                <span class="decision-pill deferred">
                    <span class="decision-dot"></span>
                    Deferred to MD
                </span>
            `;
        }

        let gateBadge = "";
        if (item.abstention_status) {
            gateBadge = `
                <span class="safety-gate-pill gate-triggered">
                    <span class="decision-dot"></span>
                    Triggered (&tau; &lt; 0.85)
                </span>
            `;
        } else {
            gateBadge = `
                <span class="safety-gate-pill gate-pass">
                    <span class="decision-dot"></span>
                    Passed (&ge; 0.85)
                </span>
            `;
        }

        const confPct = Math.round(item.calibrated_confidence * 100);
        const confClass = confPct >= 85 ? "high" : (confPct >= 65 ? "medium" : "low");

        tr.innerHTML = `
            <td><strong style="color:var(--text-muted);">#${item.index}</strong></td>
            <td>
                <div class="patient-chip">
                    <span class="patient-avatar-mini">PT</span>
                    <span>${escapeHtml(item.patient_id_masked)}</span>
                </div>
            </td>
            <td>
                <div class="policy-tag-badge">
                    <span class="policy-code-pill">${escapeHtml(item.policy_id)}</span>
                    <span class="policy-specialty-sub">${escapeHtml(specialty)}</span>
                </div>
            </td>
            <td><span class="procedure-cpt-pill">${escapeHtml(cptCode)}</span></td>
            <td><div class="clinical-snippet-box">${escapeHtml(snippet)}</div></td>
            <td>${decisionBadge}</td>
            <td>
                <div class="conf-meter-wrapper">
                    <div class="conf-meter-label">
                        <span>Confidence</span>
                        <span>${confPct}%</span>
                    </div>
                    <div class="conf-bar-bg">
                        <div class="conf-bar-fill ${confClass}" style="width: ${confPct}%;"></div>
                    </div>
                </div>
            </td>
            <td>${gateBadge}</td>
            <td style="text-align: right;">
                <button type="button" class="btn-batch-action" onclick="viewBatchItemInWizard(${item.index - 1})">
                    <span>Open Case</span>
                    <span style="font-size:0.8rem;">&rarr;</span>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });

    const totalEl = document.getElementById("filter-count-all");
    if (totalEl) totalEl.textContent = results.length;
    const appEl = document.getElementById("filter-count-approved");
    if (appEl) appEl.textContent = approvedCount;
    const denEl = document.getElementById("filter-count-denied");
    if (denEl) denEl.textContent = deniedCount;
    const defEl = document.getElementById("filter-count-deferred");
    if (defEl) defEl.textContent = deferredCount;

    window._lastBatchResults = results;
    if (currentBatchFilter !== 'ALL') {
        filterBatchTable(currentBatchFilter);
    }
}

function viewBatchItemInWizard(idx) {
    if (!window._lastBatchResults || !window._lastBatchResults[idx]) return;
    const item = window._lastBatchResults[idx];
    lastAdjudicationResult = item.adjudication;
    currentCoveragePacket = null;
    
    switchMainTab('adjudicate');
    renderCoverageScreen(item.adjudication);
    goToWizardScreen(3);
}

function loadRosterItemIntoWizard(idx) {
    if (!currentBatchRoster || !currentBatchRoster[idx]) return;
    const item = currentBatchRoster[idx];
    
    switchMainTab('adjudicate');
    document.getElementById("actual-paste-textarea").value = item.clinical_narrative;
    syncPastedNoteToInput();
    goToWizardScreen(1);
    showToast(`Loaded note for ${item.patient_id} into Prior Auth wizard.`, "info");
}

// =============================================================================
// HL7 DA VINCI CRD & DTR SIMULATOR
// =============================================================================

const CRD_PRESETS = {
    icd_approved: {
        patientId: "PT-CARDIOLOGY-101",
        hook: "order-sign",
        narrative: "History of anterior myocardial infarction in 2021 (>3 years ago). Echo on 01/10/2024: severe systolic dysfunction, LVEF 26%. NYHA Class III heart failure on optimal medical therapy (carvedilol and lisinopril for >6 months). No active cardiogenic shock."
    },
    cas_approved: {
        patientId: "PT-NEURO-205",
        hook: "order-sign",
        narrative: "Diagnostic carotid duplex and CTA confirm 85% severe right internal carotid artery stenosis. Patient experienced a transient ischemic attack (TIA) with left facial droop and arm weakness 2 months ago. High risk for open CEA due to prior radical neck radiation and hostile neck anatomy. Order: Percutaneous transluminal angioplasty with FDA-approved carotid stent and distal embolic protection device (EPD) filter deployment."
    },
    teer_approved: {
        patientId: "PT-VALVULAR-301",
        hook: "order-sign",
        narrative: "Transesophageal echocardiogram demonstrates severe mitral regurgitation (Grade 4+ MR) with posterior leaflet flail. Multidisciplinary Heart Team consultation with interventional cardiologist and cardiac surgeon confirms prohibitive surgical risk (STS operative mortality score 9.2%). Recommended for Transcatheter Edge-to-Edge Repair (TEER / MitraClip)."
    },
    icd_warning: {
        patientId: "PT-CARDIOLOGY-102",
        hook: "order-sign",
        narrative: "Acute anterior STEMI 10 days ago. Diagnostic echocardiogram shows LVEF 25%."
    }
};

function initCrdSimulator() {
    const input = document.getElementById("crd-narrative-input");
    if (!input.value) {
        loadCrdPreset("icd_approved");
    }
}

function loadCrdPreset(key) {
    const preset = CRD_PRESETS[key];
    if (!preset) return;
    document.getElementById("crd-patient-id").value = preset.patientId;
    document.getElementById("crd-hook-type").value = preset.hook;
    document.getElementById("crd-narrative-input").value = preset.narrative;
}

async function triggerCrdHook() {
    const patientId = document.getElementById("crd-patient-id").value.trim() || "PT-UNKNOWN";
    const hookType = document.getElementById("crd-hook-type").value;
    const narrative = document.getElementById("crd-narrative-input").value.trim();
    const outputContainer = document.getElementById("crd-cards-output");

    outputContainer.innerHTML = '<div style="text-align: center; padding: 20px; color: #38bdf8;">Evaluating EHR draft order via HL7 Da Vinci CRD CDS Hooks...</div>';

    const payload = {
        hook: hookType,
        hookInstance: "hook-" + Math.random().toString(36).substring(2, 10),
        context: {
            userId: "Practitioner/1043256787",
            patientId: patientId,
            draftOrders: {
                resourceType: "ServiceRequest",
                description: narrative
            }
        },
        prefetch: {
            clinicalNotes: narrative
        }
    };

    try {
        const res = await fetch("/api/v1/cds-services/medicare-crd-coverage-check", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(currentToken ? { "Authorization": `Bearer ${currentToken}` } : {})
            },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            throw new Error(`CRD service returned HTTP ${res.status}`);
        }

        const data = await res.json();
        const cards = data.cards || [];

        if (cards.length === 0) {
            outputContainer.innerHTML = '<div style="color: #94a3b8; padding: 16px;">No decision cards returned for this scenario.</div>';
            return;
        }

        let html = "";
        cards.forEach((card, idx) => {
            const isApproved = card.indicator === "info";
            const borderColor = isApproved ? "#10b981" : "#f59e0b";
            const bgColor = isApproved ? "rgba(16, 185, 129, 0.08)" : "rgba(245, 158, 11, 0.08)";
            const badgeLabel = isApproved ? "CRD Clearance Approved" : "CRD Documentation Alert";

            let linksHtml = "";
            if (card.links && card.links.length > 0) {
                linksHtml = card.links.map(l => `
                    <a href="${l.url}" target="_blank" class="btn-demo-chip" style="display: inline-block; margin-top: 8px; text-decoration: none; font-size: 11px;">
                        ${l.label}
                    </a>
                `).join("");
            }

            let suggestionsHtml = "";
            if (card.suggestions && card.suggestions.length > 0) {
                suggestionsHtml = card.suggestions.map(s => `
                    <div style="margin-top: 8px; font-size: 11px; color: #fbbf24; background: rgba(245, 158, 11, 0.15); padding: 4px 8px; border-radius: 4px;">
                        Suggested EHR Action: ${s.label}
                    </div>
                `).join("");
            }

            html += `
                <div style="background: ${bgColor}; border: 1px solid ${borderColor}; border-left: 4px solid ${borderColor}; border-radius: 6px; padding: 14px; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <strong style="color: #f8fafc; font-size: 13px;">${card.summary}</strong>
                        <span style="font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: ${borderColor}; color: #0f172a;">
                            ${badgeLabel}
                        </span>
                    </div>
                    <p style="font-size: 12px; color: #cbd5e1; margin-bottom: 6px; line-height: 1.4;">${card.detail || ""}</p>
                    <div style="font-size: 11px; color: #94a3b8;">Source: ${card.source ? card.source.label : "CMS Engine"}</div>
                    ${linksHtml}
                    ${suggestionsHtml}
                </div>
            `;
        });

        outputContainer.innerHTML = html;
    } catch (err) {
        outputContainer.innerHTML = `<div style="color: #f43f5e; padding: 16px;">Failed to evaluate CRD hook: ${err.message}</div>`;
    }
}

async function runDtrPopulate() {
    const patientId = document.getElementById("crd-patient-id").value.trim() || "PT-UNKNOWN";
    const narrative = document.getElementById("crd-narrative-input").value.trim();
    const dtrBox = document.getElementById("dtr-output-box");
    const itemsList = document.getElementById("dtr-items-list");
    const badge = document.getElementById("dtr-completeness-badge");
    const advisory = document.getElementById("dtr-advisory-text");

    let policyId = "NCD-20.4";
    const lower = narrative.lower ? narrative.lower() : narrative.toLowerCase();
    if (lower.includes("carotid") || lower.includes("cas") || lower.includes("stenosis")) {
        policyId = "NCD-20.7";
    } else if (lower.includes("mitral") || lower.includes("teer")) {
        policyId = "NCD-20.33";
    }

    dtrBox.classList.remove("hidden");
    itemsList.innerHTML = '<div style="color: #38bdf8; font-size: 12px; padding: 10px;">Executing FHIR R4 $populate operation...</div>';

    try {
        const res = await fetch("/api/v1/dtr/populate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(currentToken ? { "Authorization": `Bearer ${currentToken}` } : {})
            },
            body: JSON.stringify({
                policy_id: policyId,
                patient_id: patientId,
                clinical_narrative: narrative
            })
        });

        if (!res.ok) {
            throw new Error(`DTR $populate failed: HTTP ${res.status}`);
        }

        const data = await res.json();
        const percent = data.completeness_percent || 0;
        const isComplete = data.status === "completed";

        badge.textContent = `${percent}% Complete (${data.status.toUpperCase()})`;
        badge.style.background = isComplete ? "#10b981" : "#f59e0b";
        badge.style.color = "#0f172a";

        advisory.textContent = data.clinical_advisory;

        let itemsHtml = "";
        (data.items || []).forEach(item => {
            const hasVal = item.answered && item.value !== null && item.value !== undefined;
            const isDeficient = hasVal && String(item.value).includes("DEFICIENT");
            const statusColor = isDeficient ? "#f43f5e" : (hasVal ? "#10b981" : "#64748b");
            const statusLabel = isDeficient ? "DEFICIENT" : (hasVal ? "ANSWERED" : "MISSING");

            itemsHtml += `
                <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 6px; padding: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <span style="font-size: 12px; font-weight: 600; color: #f1f5f9;">${item.text}</span>
                        <span style="font-size: 10px; font-weight: 700; color: ${statusColor};">${statusLabel}</span>
                    </div>
                    <div style="font-size: 11px; color: ${hasVal ? "#38bdf8" : "#94a3b8"}; font-family: var(--font-mono);">
                        Value: ${hasVal ? item.value : "Not documented in clinical chart"}
                    </div>
                    ${item.evidence_span ? `
                        <div style="font-size: 10px; color: #64748b; margin-top: 2px;">
                            Evidence Span: "${item.evidence_span}" (Confidence: ${Math.round((item.confidence || 0.9) * 100)}%)
                        </div>
                    ` : ""}
                </div>
            `;
        });

        itemsList.innerHTML = itemsHtml;
    } catch (err) {
        itemsList.innerHTML = `<div style="color: #f43f5e; font-size: 12px;">Failed to populate DTR questionnaire: ${err.message}</div>`;
    }
}

// =============================================================================
// OPERATIONAL TELEMETRY & METRICS
// =============================================================================

async function loadLiveTelemetry() {
    try {
        const res = await fetch("/api/v1/metrics/json", {
            headers: currentToken ? { "Authorization": `Bearer ${currentToken}` } : {}
        });

        if (!res.ok) {
            throw new Error(`Metrics endpoint returned HTTP ${res.status}`);
        }

        const data = await res.json();
        const adj = data.adjudications || {};
        const sec = data.security || {};
        const rules = data.clinical_rules || {};

        const total = adj.total || 0;
        const approved = adj.approved || 0;
        const denied = adj.denied || 0;
        const abstained = adj.abstained || 0;
        const appRate = total > 0 ? Math.round((approved / total) * 100) : 100;

        document.getElementById("telemetry-total-adjudications").textContent = total;
        document.getElementById("telemetry-approval-rate").textContent = `${appRate}%`;
        document.getElementById("telemetry-latency-avg").textContent = `${adj.average_latency_ms || 45} ms`;
        document.getElementById("telemetry-active-sessions").textContent = sec.active_sessions || 1;

        document.getElementById("telemetry-count-approved").textContent = approved;
        document.getElementById("telemetry-count-denied").textContent = denied;
        document.getElementById("telemetry-count-abstained").textContent = abstained;

        if (total > 0) {
            document.getElementById("telemetry-bar-approved").style.width = `${(approved / total) * 100}%`;
            document.getElementById("telemetry-bar-denied").style.width = `${(denied / total) * 100}%`;
            document.getElementById("telemetry-bar-abstained").style.width = `${(abstained / total) * 100}%`;
        } else {
            document.getElementById("telemetry-bar-approved").style.width = "0%";
            document.getElementById("telemetry-bar-denied").style.width = "0%";
            document.getElementById("telemetry-bar-abstained").style.width = "0%";
        }

        document.getElementById("telemetry-total-users").textContent = sec.total_users || 4;
        document.getElementById("telemetry-revoked-sessions").textContent = sec.revoked_sessions || 0;
        document.getElementById("telemetry-policies-count").textContent = rules.active_policies_count || 6;

        // Populate Cache & System Telemetry
        const cache = data.cache_and_system || {};
        const cacheHits = cache.hits || 0;
        const cacheMisses = cache.misses || 0;
        const cacheRatio = cache.hit_ratio !== undefined ? (cache.hit_ratio * 100).toFixed(1) : "0.0";
        const cacheRatioElem = document.getElementById("telemetry-cache-ratio");
        if (cacheRatioElem) cacheRatioElem.textContent = `${cacheRatio}%`;

        const hitsMissesElem = document.getElementById("telemetry-cache-hits-misses");
        if (hitsMissesElem) hitsMissesElem.textContent = `${cacheHits} / ${cacheMisses}`;

        const cacheKeysElem = document.getElementById("telemetry-cache-keys");
        if (cacheKeysElem) cacheKeysElem.textContent = `${cache.active_cached_keys || 0} keys`;
    } catch (err) {
        console.warn("Failed to fetch live telemetry:", err);
    }
}


// =============================================================================

// =============================================================================
// OFFICIAL CMS PACKET & APPEAL LETTER PDF EXPORT
// =============================================================================

function downloadPacketPdf(customCaseId) {
    const caseId = customCaseId || 
        (currentCoveragePacket && currentCoveragePacket.case_id) || 
        (lastAdjudicationResult && lastAdjudicationResult.case_id);

    if (!caseId) {
        showToast("No active clinical case identifier found.", true);
        return;
    }

    const token = currentToken || sessionStorage.getItem("access_token");
    const downloadUrl = `/api/v1/packet/${encodeURIComponent(caseId)}/pdf`;

    showToast("Synthesizing official CMS Coverage Packet PDF...", "info");

    fetch(downloadUrl, {
        headers: token ? { "Authorization": `Bearer ${token}` } : {}
    })
    .then(res => {
        if (!res.ok) throw new Error(`Server returned HTTP ${res.status}`);
        return res.blob();
    })
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.style.display = "none";
        a.href = url;
        a.download = `CMS_Coverage_Packet_${caseId}.pdf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        showToast("Downloaded CMS Coverage Determination Packet PDF.", "success");
    })
    .catch(err => {
        console.error("PDF download failed:", err);
        showToast("Failed to download PDF: " + err.message, true);
    });
}

function downloadAppealLetterPdf(customCaseId) {
    const caseId = customCaseId || 
        (currentCoveragePacket && currentCoveragePacket.case_id) || 
        (lastAdjudicationResult && lastAdjudicationResult.case_id);

    if (!caseId) {
        showToast("No active clinical case identifier found.", true);
        return;
    }

    const token = currentToken || sessionStorage.getItem("access_token");
    const downloadUrl = `/api/v1/packet/${encodeURIComponent(caseId)}/appeal-letter/pdf`;

    showToast("Generating formal Peer-to-Peer Appeal Letter PDF...", "info");

    fetch(downloadUrl, {
        headers: token ? { "Authorization": `Bearer ${token}` } : {}
    })
    .then(res => {
        if (!res.ok) throw new Error(`Server returned HTTP ${res.status}`);
        return res.blob();
    })
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.style.display = "none";
        a.href = url;
        a.download = `Peer_to_Peer_Appeal_Letter_${caseId}.pdf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        showToast("Downloaded Peer-to-Peer Appeal Letter PDF.", "success");
    })
    .catch(err => {
        console.error("Appeal PDF download failed:", err);
        showToast("Failed to download appeal PDF: " + err.message, true);
    });
}

// HIPAA INACTIVITY SESSION AUTO-LOCK (45 CFR § 164.312(a)(2)(iii))
// =============================================================================

const HIPAA_INACTIVITY_LIMIT_MS = 15 * 60 * 1000; // 15 minutes
let lastUserInteractionTime = Date.now();

function initHipaaInactivityWatcher() {
    const activityEvents = ["mousemove", "mousedown", "keydown", "touchstart", "scroll", "click"];
    activityEvents.forEach(evt => {
        window.addEventListener(evt, () => {
            lastUserInteractionTime = Date.now();
        }, { passive: true });
    });

    setInterval(() => {
        if (!currentToken) return;
        const elapsed = Date.now() - lastUserInteractionTime;
        if (elapsed >= HIPAA_INACTIVITY_LIMIT_MS) {
            handleHipaaInactivityTimeout();
        }
    }, 15000);
}

function handleHipaaInactivityTimeout() {
    currentToken = null;
    sessionStorage.removeItem("carepolicyguard_token");
    sessionStorage.removeItem("carepolicyguard_role");
    sessionStorage.removeItem("carepolicyguard_user");

    const gate = document.getElementById("login-gate");
    if (gate) gate.classList.remove("hidden");

    const appHeader = document.querySelector(".app-header");
    if (appHeader) appHeader.style.display = "none";
    const mainContent = document.querySelector(".main-content");
    if (mainContent) mainContent.style.display = "none";

    const errBox = document.getElementById("login-error-box");
    if (errBox) {
        errBox.textContent = "HIPAA Security Auto-Lock: Session automatically locked after 15 minutes of inactivity to protect Protected Health Information (45 CFR § 164.312(a)(2)(iii)). Please sign in again.";
        errBox.classList.remove("hidden");
    }
}



// =============================================================================
// ON-DEMAND POLICY SPECIFICATION DOCUMENT & TOGGLES
// =============================================================================

function openPolicyDocumentModal(policyId) {
    if (!policyId) {
        const policySelect = document.getElementById("policy-select");
        policyId = (policySelect && policySelect.value) ? policySelect.value : (lastAdjudicationResult ? lastAdjudicationResult.policy_id : "NCD-20.4");
    }

    const modal = document.getElementById("policy-document-modal");
    if (!modal) return;

    let policy = (cachedPoliciesList || []).find(p => p.policy_id === policyId);
    if (!policy && lastMultiPolicyScanResult && lastMultiPolicyScanResult.all_matches) {
        policy = lastMultiPolicyScanResult.all_matches.find(m => m.policy_id === policyId);
    }

    const titleElem = document.getElementById("policy-doc-title");
    const subElem = document.getElementById("policy-doc-subtitle");
    const bodyElem = document.getElementById("policy-doc-modal-body");

    const pTitle = policy ? (policy.title || policy.policy_title) : "Implantable Automatic Defibrillators";
    const pJurisdiction = policy ? (policy.jurisdiction || "National Coverage Determination (CMS)") : "National Coverage Determination (CMS)";
    const pCategory = policy ? policy.category : "Cardiology";
    const pEffDate = policy ? (policy.effective_date || "2018-02-15") : "2018-02-15";
    const pDesc = policy ? (policy.description || "CMS National Coverage Determination establishing statutory clinical indications, objective diagnostic thresholds, and disqualifying exclusions.") : "";

    if (titleElem) titleElem.textContent = `${policyId} - ${pTitle}`;
    if (subElem) subElem.textContent = `${pJurisdiction} | Category: ${pCategory} | Effective: ${pEffDate}`;

    let criteriaHtml = "";
    if (policy && policy.criteria && policy.criteria.length > 0) {
        criteriaHtml = `
            <table class="policy-doc-crit-table">
                <thead>
                    <tr>
                        <th style="width: 16%;">Code</th>
                        <th style="width: 26%;">Requirement</th>
                        <th style="width: 44%;">Statutory Coverage Condition</th>
                        <th style="width: 14%;">Type</th>
                    </tr>
                </thead>
                <tbody>
                    ${policy.criteria.map(c => `
                        <tr>
                            <td><span class="code-pill">${escapeHtml(c.criterion_code)}</span></td>
                            <td><strong>${escapeHtml(c.name || c.criterion_code)}</strong></td>
                            <td>
                                <div>${escapeHtml(c.description || 'Statutory Medicare criteria condition.')}</div>
                                ${c.required_temporal_window ? `<div style="font-size: 0.74rem; color: #38BDF8; margin-top: 3px;">Timing Window: ${escapeHtml(c.required_temporal_window)}</div>` : ''}
                            </td>
                            <td><span class="badge-role-tag">${c.is_exclusion ? 'Exclusion' : 'Mandatory'}</span></td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        `;
    } else {
        criteriaHtml = `
            <p style="font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5;">
                Evaluates mandatory left ventricular ejection fraction threshold (&le; 35%), optimal guideline-directed medical therapy (&ge; 90 days), NYHA functional heart failure classification (Class II/III), acute myocardial infarction waiting periods (&ge; 40 days), and absence of cardiogenic shock.
            </p>
        `;
    }

    if (bodyElem) {
        bodyElem.innerHTML = `
            <div class="policy-doc-section">
                <div class="policy-doc-section-title">
                    <span class="med-icon icon-xs"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg></span>
                    Coverage Indications &amp; Statutory Scope
                </div>
                <p class="policy-doc-text">${escapeHtml(pDesc || 'CMS policy governing coverage requirements under Title XVIII of the Social Security Act § 1862(a)(1)(A).')}</p>
            </div>

            <div class="policy-doc-section">
                <div class="policy-doc-section-title">
                    <span class="med-icon icon-xs"><svg viewBox="0 0 24 24"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg></span>
                    Evaluated Statutory Criteria Specifications
                </div>
                ${criteriaHtml}
            </div>

            <div class="policy-doc-section">
                <div class="policy-doc-section-title">
                    <span class="med-icon icon-xs"><svg viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg></span>
                    Governing Regulatory Authority &amp; Integrity Rules
                </div>
                <p class="policy-doc-text" style="font-size: 0.78rem;">
                    Pursuant to CMS Program Integrity Manual (PIM Ch. 3) and 42 CFR § 410.38, all objective diagnostic measures must be grounded in contemporaneous patient records signed by the treating clinician.
                </p>
            </div>
        `;
    }

    modal.classList.remove("hidden");
}

function closePolicyDocumentModal() {
    const modal = document.getElementById("policy-document-modal");
    if (modal) modal.classList.add("hidden");
}

function toggleGroundedEHRViewer() {
    const section = document.getElementById("grounded-ehr-section");
    const label = document.getElementById("toggle-ehr-label");
    if (!section) return;

    if (section.classList.contains("hidden")) {
        section.classList.remove("hidden");
        if (label) label.textContent = "Hide Chart Evidence Quotes";
        section.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else {
        section.classList.add("hidden");
        if (label) label.textContent = "View Chart Evidence Quotes";
    }
}

function toggleBillingDetails() {
    const billingPanel = document.getElementById("billing-compliance-panel");
    const timelinePanel = document.getElementById("timeline-analysis-panel");
    const label = document.getElementById("toggle-billing-label");

    const isHidden = billingPanel ? billingPanel.classList.contains("hidden") : true;
    if (isHidden) {
        if (billingPanel) billingPanel.classList.remove("hidden");
        if (timelinePanel) timelinePanel.classList.remove("hidden");
        if (label) label.textContent = "Hide Billing & Milestones";
        if (billingPanel) billingPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else {
        if (billingPanel) billingPanel.classList.add("hidden");
        if (timelinePanel) timelinePanel.classList.add("hidden");
        if (label) label.textContent = "View Billing & Milestones";
    }
}


// Global modal backdrop click & Escape key handler
window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (typeof closePolicyDocumentModal === 'function') closePolicyDocumentModal();
        if (typeof closeAddendumModal === 'function') closeAddendumModal();
        if (typeof closeCriterionModal === 'function') closeCriterionModal();
        if (typeof closeSampleTutorialModal === 'function') closeSampleTutorialModal();
        if (typeof closeTermsModal === 'function') closeTermsModal();
        if (typeof closePeerToPeerAppealModal === 'function') closePeerToPeerAppealModal();
        if (typeof closeFhirModal === 'function') closeFhirModal();
    }
});

document.addEventListener('click', (e) => {
    if (e.target && e.target.classList && e.target.classList.contains('modal-overlay')) {
        if (e.target.id === 'audit-detail-modal' && typeof closeAuditDetailModal === 'function') closeAuditDetailModal();
        else if (e.target.id === 'policy-document-modal' && typeof closePolicyDocumentModal === 'function') closePolicyDocumentModal();
        else if (e.target.id === 'addendum-modal' && typeof closeAddendumModal === 'function') closeAddendumModal();
        else if (e.target.id === 'criterion-detail-modal' && typeof closeCriterionModal === 'function') closeCriterionModal();
        else if (e.target.id === 'sample-tutorial-modal' && typeof closeSampleTutorialModal === 'function') closeSampleTutorialModal();
        else if (e.target.id === 'terms-modal' && typeof closeTermsModal === 'function') closeTermsModal();
        else if (e.target.id === 'appeal-letter-modal' && typeof closePeerToPeerAppealModal === 'function') closePeerToPeerAppealModal();
        else if (e.target.id === 'fhir-bundle-modal' && typeof closeFhirModal === 'function') closeFhirModal();
    }
});
