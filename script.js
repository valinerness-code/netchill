document.addEventListener("DOMContentLoaded", () => {
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
      const value = input.value.trim();

      if (!value) {
        input.focus();
        input.placeholder = "Please enter a valid email";
        return;
      }

      alert("Thanks! We’ll keep you posted on the latest releases.");
      form.reset();
    });
  });

  const modal = document.getElementById("signin-modal");
  const openButton = document.getElementById("open-signin");
  const closeButton = document.querySelector(".modal-close");
  const signinForm = document.getElementById("signin-form");

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

  signinForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const email = signinForm.email.value.trim();
    const password = signinForm.password.value.trim();

    if (!email || !password) {
      return;
    }

    const user = { email, password };
    localStorage.setItem("netchill-user", JSON.stringify(user));

    const confirmationMessage = encodeURIComponent(
      `Thank you for signing in.\n\nEmail: ${email}\nPassword: ${password}`
    );
    const mailLink = `mailto:${email}?subject=${encodeURIComponent(
      "Welcome to Netchill"
    )}&body=${confirmationMessage}`;

    window.location.href = mailLink;
    setTimeout(() => {
      window.location.href = "home.html";
    }, 500);

    signinForm.reset();
    closeModal();
  });
});
