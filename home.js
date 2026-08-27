document.addEventListener("DOMContentLoaded", () => {
  let storedUser = null;

  try {
    storedUser = JSON.parse(localStorage.getItem("netchill-user") || "null");
  } catch (error) {
    localStorage.removeItem("netchill-user");
  }

  if (!storedUser || typeof storedUser.email !== "string") {
    localStorage.removeItem("netchill-user");
    window.location.href = "index.html";
    return;
  }

  const rows = document.querySelectorAll(".media-row");
  const navLinks = document.querySelectorAll(".nav-link");
  const categoryBlocks = document.querySelectorAll(".category-block");
  const profileWrap = document.querySelector(".profile-wrap");
  const profileButton = document.querySelector(".profile-btn");
  const profileLabel = document.querySelector(".profile-label");
  const profileAvatar = document.querySelector(".profile-avatar");
  const profileItems = document.querySelectorAll(".profile-menu-item[data-name]");
  const signOutMenuItem = document.querySelector(".profile-menu-item.sign-out");
  const overlay = document.getElementById("panel-overlay");
  const modals = document.querySelectorAll(".panel-modal");
  const closeButtons = document.querySelectorAll(".panel-close");

  rows.forEach((row) => {
    const leftButton = row.parentElement.querySelector(".scroll-btn.left");
    const rightButton = row.parentElement.querySelector(".scroll-btn.right");

    leftButton?.addEventListener("click", () => {
      row.scrollBy({ left: -260, behavior: "smooth" });
    });

    rightButton?.addEventListener("click", () => {
      row.scrollBy({ left: 260, behavior: "smooth" });
    });
  });

  navLinks.forEach((link) => {
    link.addEventListener("click", () => {
      const view = link.dataset.view;
      const mappedView = view === "series" ? "shows" : view;

      navLinks.forEach((item) => item.classList.toggle("active", item === link));

      categoryBlocks.forEach((block) => {
        const show =
          view === "home"
            ? block.dataset.category === "movies" || block.dataset.category === "shows"
            : block.dataset.category === mappedView;

        block.classList.toggle("visible", show);
      });
    });
  });

  const setProfileMenuState = (open) => {
    if (!profileWrap || !profileButton) return;

    profileWrap.classList.toggle("open", open);
    profileButton.setAttribute("aria-expanded", String(open));
  };

  profileButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    const isOpen = profileWrap.classList.contains("open");
    setProfileMenuState(!isOpen);
  });

  document.addEventListener("click", (event) => {
    if (profileWrap && !profileWrap.contains(event.target)) {
      setProfileMenuState(false);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setProfileMenuState(false);
    }
  });

  const openPanel = (panelId) => {
    if (!overlay) return;

    overlay.classList.remove("hidden");
    overlay.setAttribute("aria-hidden", "false");

    modals.forEach((modal) => {
      modal.classList.toggle("active", modal.id === panelId);
    });
  };

  const closePanel = () => {
    if (!overlay) return;

    overlay.classList.add("hidden");
    overlay.setAttribute("aria-hidden", "true");
    modals.forEach((modal) => modal.classList.remove("active"));
  };

  const profileActionMap = {
    "Manage Profiles": "manage-profiles.html",
    Account: "account.html",
    "Help Center": "help-center.html",
  };

  const signOutUser = () => {
    localStorage.removeItem("netchill-user");
    window.location.href = "index.html";
  };

  profileItems.forEach((item) => {
    item.addEventListener("click", () => {
      const selectedName = item.dataset.name;
      const selectedColor = item.dataset.color;

      if (!selectedName) {
        const actionName = item.textContent.trim();
        const targetPage = profileActionMap[actionName];

        if (targetPage) {
          window.location.href = targetPage;
          return;
        }

        if (actionName.includes("Sign out")) {
          signOutUser();
          return;
        }

        setProfileMenuState(false);
        return;
      }

      profileItems.forEach((profile) => {
        profile.classList.toggle("active", profile === item);
      });

      if (profileLabel) {
        profileLabel.textContent = selectedName;
      }

      if (profileAvatar) {
        profileAvatar.textContent = selectedName.charAt(0);

        const colorMap = {
          amber: "linear-gradient(135deg, #f8d488, #f59e0b)",
          pink: "linear-gradient(135deg, #f9a8d4, #ec4899)",
          blue: "linear-gradient(135deg, #93c5fd, #2563eb)",
        };

        profileAvatar.style.background = colorMap[selectedColor] || colorMap.amber;
      }

      setProfileMenuState(false);
    });
  });

  signOutMenuItem?.addEventListener("click", () => {
    signOutUser();
  });

  document.querySelectorAll("[data-page]").forEach((pageButton) => {
    pageButton.addEventListener("click", () => {
      const targetPage = pageButton.dataset.page;
      if (targetPage) {
        window.location.href = targetPage;
      }
    });
  });

  closeButtons.forEach((button) => {
    button.addEventListener("click", closePanel);
  });

  overlay?.addEventListener("click", (event) => {
    if (event.target === overlay) {
      closePanel();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && overlay && !overlay.classList.contains("hidden")) {
      closePanel();
    }
  });

  document.querySelector("[data-close-panel='true']")?.addEventListener("click", closePanel);
  document.querySelector(".panel-button.danger")?.addEventListener("click", () => {
    closePanel();
    signOutUser();
  });
});
