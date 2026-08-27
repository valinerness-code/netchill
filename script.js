document.addEventListener("DOMContentLoaded", () => {
  // Security utility functions
  const SecurityUtils = {
    sanitizeInput: (input) => {
      if (input === null || input === undefined) return "";
      const safeValue = String(input).trim();
      const div = document.createElement("div");
      div.textContent = safeValue;
      return div.innerHTML;
    },

    validateEmail: (email) => {
      if (typeof email !== "string") return false;
      const normalized = email.trim();
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      return emailRegex.test(normalized);
    },

    validatePassword: (password) => {
      if (typeof password !== "string") return false;
      const trimmed = password.trim();
      if (trimmed.length < 6 || trimmed.length > 128) return false;
      return /^[a-zA-Z0-9!@#$%^&*()_+\-=\[\]{};':",./<>?]*$/.test(trimmed);
    },

    sanitizeSQL: (input) => {
      return String(input).replace(/['"`;\\]/g, "");
    },

    escapeHTML: (text) => {
      const map = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      };
      return String(text).replace(/[&<>"']/g, (m) => map[m]);
    },

    safeRedirect: (targetPage) => {
      const safePages = new Set([
        "index.html",
        "membership.html",
        "home.html",
        "manage-profiles.html",
        "account.html",
        "help-center.html",
      ]);
      const normalized = String(targetPage || "").trim();

      if (safePages.has(normalized)) {
        window.location.href = normalized;
      }
    },
  };

  const readStoredUser = () => {
    try {
      const raw = localStorage.getItem("netchill-user");
      return raw ? JSON.parse(raw) : null;
    } catch (error) {
      localStorage.removeItem("netchill-user");
      return null;
    }
  };

  const faqItems = document.querySelectorAll(".faq-item");

  faqItems.forEach((item) => {
    const button = item.querySelector(".faq-question");

    button.addEventListener("click", () => {
      const isActive = item.classList.contains("active");

      faqItems.forEach((faq) => {
        faq.classList.remove("active");
      });

      if (!isActive) {
        item.classList.add("active");
      }
    });
  });

  const signupForms = document.querySelectorAll(".signup-form");

  signupForms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const input = form.querySelector("input");
      const value = SecurityUtils.sanitizeInput(input.value);

      if (!value) {
        input.value = "";
        input.focus();
        input.placeholder = "Please enter a valid email";
        return;
      }
      if (!SecurityUtils.validateEmail(value)) {
        input.value = "";
        input.placeholder = "Please enter a valid email address";
        input.focus();
        return;
      }

      sessionStorage.setItem("netchill-signup-email", value);
      window.location.href = "membership.html";
    });
  });

  const modal = document.getElementById("signin-modal");
  const openButton = document.getElementById("open-signin");
  const closeButton = document.querySelector(".modal-close");
  const signinForm = document.getElementById("signin-form");
  const passwordInput = signinForm?.querySelector('input[name="password"]');
  const passwordToggle = signinForm?.querySelector(".password-toggle");

  const storedUser = readStoredUser();

  if (storedUser && SecurityUtils.validateEmail(storedUser.email) && window.location.pathname.endsWith("index.html")) {
    SecurityUtils.safeRedirect("home.html");
  }

  function openModal() {
    modal.classList.add("visible");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeModal() {
    modal.classList.remove("visible");
    modal.setAttribute("aria-hidden", "true");
  }

  openButton.addEventListener("click", openModal);
  closeButton.addEventListener("click", closeModal);

  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      closeModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modal.classList.contains("visible")) {
      closeModal();
    }
  });

  passwordToggle?.addEventListener("click", () => {
    const isPassword = passwordInput.type === "password";
    passwordInput.type = isPassword ? "text" : "password";
    passwordToggle.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
    passwordToggle.setAttribute("aria-pressed", String(isPassword));
    passwordInput.focus();
  });

  signinForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = SecurityUtils.sanitizeInput(signinForm.email.value);
    const password = SecurityUtils.sanitizeInput(signinForm.password.value);

    if (!email || !password) {
      alert("Please fill in all fields.");
      return;
    }

    if (!SecurityUtils.validateEmail(email)) {
      signinForm.email.value = "";
      signinForm.email.placeholder = "Enter a valid email";
      signinForm.email.focus();
      return;
    }

    if (!SecurityUtils.validatePassword(password)) {
      signinForm.password.value = "";
      signinForm.password.placeholder = "Password must be 6+ characters";
      signinForm.password.focus();
      return;
    }

    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ email, password }),
      });
      if (!response.ok) throw new Error(await response.text());
      localStorage.setItem("netchill-user", JSON.stringify({ email }));
      signinForm.reset();
      closeModal();
      SecurityUtils.safeRedirect("home.html");
    } catch (error) {
      alert(error.message || "Could not sign in.");
    }
  });
});
