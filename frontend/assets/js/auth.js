/* Page controllers for the auth flow (signup/login/forgot/reset/verify).
 * Each page calls the matching init function once its DOM is ready. */

function setFieldError(form, field, message) {
  const el = form.querySelector(`[data-error-for="${field}"]`);
  if (el) {
    el.textContent = message;
    el.classList.toggle("visible", Boolean(message));
  }
  const input = form.querySelector(`[name="${field}"]`);
  if (input) input.classList.toggle("is-invalid", Boolean(message));
}

function clearFieldErrors(form) {
  form.querySelectorAll(".field-error").forEach((el) => {
    el.textContent = "";
    el.classList.remove("visible");
  });
  form.querySelectorAll(".is-invalid").forEach((el) => el.classList.remove("is-invalid"));
}

function showAlert(alertEl, message, type = "error") {
  alertEl.textContent = message;
  alertEl.className = `alert-inline visible ${type}`;
}

function hideAlert(alertEl) {
  alertEl.className = "alert-inline";
}

function setLoading(button, loading, loadingLabel = "Please wait…") {
  if (loading) {
    button.dataset.originalLabel = button.innerHTML;
    button.innerHTML = `<span class="spinner-border spinner-border-sm"></span> ${loadingLabel}`;
    button.disabled = true;
  } else {
    button.innerHTML = button.dataset.originalLabel || button.innerHTML;
    button.disabled = false;
  }
}

function applyFieldErrorsFromApi(form, err) {
  if (err.fieldErrors && err.fieldErrors.length) {
    err.fieldErrors.forEach((fe) => setFieldError(form, fe.field, fe.message));
    return true;
  }
  return false;
}

function scorePassword(pw) {
  let score = 0;
  if (pw.length >= 10) score++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++;
  if (/\d/.test(pw)) score++;
  if (/[^\w\s]/.test(pw)) score++;
  if (pw.length >= 14) score++;
  return Math.min(score, 4);
}

function initPasswordStrength(input, barsContainer, labelEl) {
  const bars = barsContainer.querySelectorAll(".bar");
  const labels = ["Very weak", "Weak", "Fair", "Strong", "Excellent"];
  const colors = ["var(--danger)", "var(--danger)", "var(--warning)", "var(--success)", "var(--success)"];
  input.addEventListener("input", () => {
    const score = input.value ? scorePassword(input.value) : -1;
    bars.forEach((bar, i) => {
      bar.style.background = i <= score ? colors[score] : "var(--border-subtle)";
    });
    labelEl.textContent = score >= 0 ? labels[score] : "";
  });
}

function initSignup() {
  const form = document.getElementById("signup-form");
  const alertEl = document.getElementById("signup-alert");
  const submitBtn = document.getElementById("signup-submit");
  const pwInput = form.querySelector('[name="password"]');
  const strengthBars = document.getElementById("password-strength-bars");
  const strengthLabel = document.getElementById("password-strength-label");
  if (pwInput && strengthBars) initPasswordStrength(pwInput, strengthBars, strengthLabel);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(form);
    hideAlert(alertEl);

    const payload = {
      full_name: form.full_name.value.trim(),
      email: form.email.value.trim(),
      password: form.password.value,
      confirm_password: form.confirm_password.value,
      accept_terms: form.accept_terms.checked,
    };

    if (!payload.accept_terms) {
      setFieldError(form, "accept_terms", "You must accept the Terms of Service.");
      return;
    }

    setLoading(submitBtn, true, "Creating account…");
    try {
      const res = await window.AIAgentApi.post("/auth/signup", payload);
      showAlert(alertEl, res.message, "success");
      form.reset();
      setTimeout(() => {
        window.location.href = `login.html?verify_pending=1&email=${encodeURIComponent(payload.email)}`;
      }, 1800);
    } catch (err) {
      if (!applyFieldErrorsFromApi(form, err)) showAlert(alertEl, err.message, "error");
    } finally {
      setLoading(submitBtn, false);
    }
  });
}

function initLogin() {
  const form = document.getElementById("login-form");
  const alertEl = document.getElementById("login-alert");
  const submitBtn = document.getElementById("login-submit");

  const params = new URLSearchParams(window.location.search);
  if (params.get("verify_pending")) {
    showAlert(
      alertEl,
      "Account created. Please check your email and verify your address before logging in.",
      "info"
    );
    if (params.get("email")) form.email.value = params.get("email");
  }
  if (params.get("reset") === "1") {
    showAlert(alertEl, "Your password has been reset. Please log in with your new password.", "success");
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(form);
    hideAlert(alertEl);

    const payload = { email: form.email.value.trim(), password: form.password.value };
    setLoading(submitBtn, true, "Signing in…");
    try {
      await window.AIAgentApi.post("/auth/login", payload);
      window.location.href = "dashboard.html";
    } catch (err) {
      if (err.status === 403 && /verify/i.test(err.message)) {
        showAlert(alertEl, err.message, "error");
        const resendBtn = document.getElementById("resend-verification-link");
        if (resendBtn) resendBtn.classList.remove("d-none");
      } else if (!applyFieldErrorsFromApi(form, err)) {
        showAlert(alertEl, err.message, "error");
      }
    } finally {
      setLoading(submitBtn, false);
    }
  });

  const resendBtn = document.getElementById("resend-verification-link");
  if (resendBtn) {
    resendBtn.addEventListener("click", async () => {
      const email = form.email.value.trim();
      if (!email) return;
      try {
        await window.AIAgentApi.post("/auth/resend-verification", { email });
        window.AIAgentToast.show("Verification email sent (if that account exists).", "success");
      } catch (err) {
        window.AIAgentToast.show(err.message, "error");
      }
    });
  }
}

function initForgotPassword() {
  const form = document.getElementById("forgot-form");
  const alertEl = document.getElementById("forgot-alert");
  const submitBtn = document.getElementById("forgot-submit");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(form);
    hideAlert(alertEl);
    setLoading(submitBtn, true, "Sending…");
    try {
      const res = await window.AIAgentApi.post("/auth/forgot-password", {
        email: form.email.value.trim(),
      });
      showAlert(alertEl, res.message, "success");
      form.reset();
    } catch (err) {
      if (!applyFieldErrorsFromApi(form, err)) showAlert(alertEl, err.message, "error");
    } finally {
      setLoading(submitBtn, false);
    }
  });
}

function initResetPassword() {
  const form = document.getElementById("reset-form");
  const alertEl = document.getElementById("reset-alert");
  const submitBtn = document.getElementById("reset-submit");
  const pwInput = form.querySelector('[name="new_password"]');
  const strengthBars = document.getElementById("password-strength-bars");
  const strengthLabel = document.getElementById("password-strength-label");
  if (pwInput && strengthBars) initPasswordStrength(pwInput, strengthBars, strengthLabel);

  const token = new URLSearchParams(window.location.search).get("token");
  if (!token) {
    showAlert(alertEl, "This password reset link is missing its token. Request a new one.", "error");
    form.querySelectorAll("input, button").forEach((el) => (el.disabled = true));
    return;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(form);
    hideAlert(alertEl);
    setLoading(submitBtn, true, "Resetting…");
    try {
      await window.AIAgentApi.post("/auth/reset-password", {
        token,
        new_password: form.new_password.value,
        confirm_password: form.confirm_password.value,
      });
      window.location.href = "login.html?reset=1";
    } catch (err) {
      if (!applyFieldErrorsFromApi(form, err)) showAlert(alertEl, err.message, "error");
    } finally {
      setLoading(submitBtn, false);
    }
  });
}

function initVerifyEmail() {
  const statusEl = document.getElementById("verify-status");
  const token = new URLSearchParams(window.location.search).get("token");

  if (!token) {
    statusEl.innerHTML = `
      <div class="empty-icon"><i class="bi bi-x-circle"></i></div>
      <h2>Missing verification token</h2>
      <p class="subtitle">This link is malformed. Please use the link from your verification email.</p>`;
    return;
  }

  window.AIAgentApi
    .post("/auth/verify-email", { token })
    .then((res) => {
      statusEl.innerHTML = `
        <div class="empty-icon text-success"><i class="bi bi-check-circle"></i></div>
        <h2>Email verified</h2>
        <p class="subtitle">${res.message}</p>
        <a class="btn-brand" href="login.html">Continue to login</a>`;
    })
    .catch((err) => {
      statusEl.innerHTML = `
        <div class="empty-icon text-danger"><i class="bi bi-x-circle"></i></div>
        <h2>Verification failed</h2>
        <p class="subtitle">${err.message}</p>
        <a class="btn-ghost" href="login.html">Back to login</a>`;
    });
}

window.AuthPages = { initSignup, initLogin, initForgotPassword, initResetPassword, initVerifyEmail };
