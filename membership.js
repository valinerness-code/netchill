document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("membership-form");
  const emailInput = document.getElementById("membership-email");
  const errorMessage = document.getElementById("membership-error");
  const storedEmail = sessionStorage.getItem("netchill-signup-email");

  if (storedEmail && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(storedEmail)) {
    emailInput.value = storedEmail;
    sessionStorage.removeItem("netchill-signup-email");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    const email = emailInput.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      errorMessage.textContent = "Please enter a valid email address.";
      errorMessage.hidden = false;
      emailInput.focus();
      return;
    }

    const password = form.elements.password.value;
    try {
      const response = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ email, password }),
      });
      if (!response.ok) throw new Error(await response.text());
      localStorage.setItem("netchill-user", JSON.stringify({ email }));
      window.location.href = "home.html";
    } catch (error) {
      errorMessage.textContent = error.message || "Could not create your account.";
      errorMessage.hidden = false;
    }
  });
});
