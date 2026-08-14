async function init() {
  const user = await window.AppShell.initAppShell("profile");
  if (!user) return;

  document.getElementById("profile-name").textContent = user.full_name;
  document.getElementById("profile-email").textContent = user.email;
  document.getElementById("profile-avatar").textContent = user.full_name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join("");
  document.getElementById("full_name").value = user.full_name;

  const badge = document.getElementById("profile-verified-badge");
  if (user.email_verified) {
    badge.className = "badge-pill badge-success";
    badge.innerHTML = '<i class="bi bi-patch-check-fill"></i> Verified';
  } else {
    badge.className = "badge-pill badge-warning";
    badge.innerHTML = '<i class="bi bi-exclamation-triangle-fill"></i> Unverified';
  }

  window.AppShell.loadSessions();

  // Profile form
  const profileForm = document.getElementById("profile-form");
  const profileAlert = document.getElementById("profile-alert");
  profileForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(profileForm);
    hideAlert(profileAlert);
    const btn = document.getElementById("profile-save-btn");
    setLoading(btn, true, "Saving…");
    try {
      const updated = await window.AIAgentApi.patch("/users/me", {
        full_name: profileForm.full_name.value.trim(),
      });
      document.getElementById("profile-name").textContent = updated.full_name;
      document.getElementById("topbar-user-name").textContent = updated.full_name;
      showAlert(profileAlert, "Profile updated.", "success");
    } catch (err) {
      if (!applyFieldErrorsFromApi(profileForm, err)) showAlert(profileAlert, err.message, "error");
    } finally {
      setLoading(btn, false);
    }
  });

  // Email form
  const emailForm = document.getElementById("email-form");
  const emailAlert = document.getElementById("email-alert");
  emailForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(emailForm);
    hideAlert(emailAlert);
    const btn = document.getElementById("email-save-btn");
    setLoading(btn, true, "Updating…");
    try {
      const res = await window.AIAgentApi.post("/users/me/change-email", {
        new_email: emailForm.new_email.value.trim(),
        current_password: emailForm.current_password.value,
      });
      showAlert(emailAlert, res.message, "success");
      emailForm.reset();
    } catch (err) {
      if (!applyFieldErrorsFromApi(emailForm, err)) showAlert(emailAlert, err.message, "error");
    } finally {
      setLoading(btn, false);
    }
  });

  // Password form
  const passwordForm = document.getElementById("password-form");
  const passwordAlert = document.getElementById("password-alert");
  const pwInput = passwordForm.querySelector('[name="new_password"]');
  const strengthBars = document.getElementById("password-strength-bars");
  const strengthLabel = document.getElementById("password-strength-label");
  if (pwInput && strengthBars) initPasswordStrength(pwInput, strengthBars, strengthLabel);

  passwordForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(passwordForm);
    hideAlert(passwordAlert);
    const btn = document.getElementById("password-save-btn");
    setLoading(btn, true, "Updating…");
    try {
      const res = await window.AIAgentApi.post("/users/me/change-password", {
        current_password: passwordForm.current_password.value,
        new_password: passwordForm.new_password.value,
        confirm_password: passwordForm.confirm_password.value,
      });
      showAlert(passwordAlert, res.message, "success");
      passwordForm.reset();
    } catch (err) {
      if (!applyFieldErrorsFromApi(passwordForm, err)) showAlert(passwordAlert, err.message, "error");
    } finally {
      setLoading(btn, false);
    }
  });

  document.getElementById("logout-all-btn").addEventListener("click", async () => {
    try {
      await window.AIAgentApi.post("/auth/logout-all", {});
      window.location.href = "login.html";
    } catch (err) {
      window.AIAgentToast.show(err.message, "error");
    }
  });
}

init();
