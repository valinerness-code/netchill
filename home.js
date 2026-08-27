document.addEventListener("DOMContentLoaded", () => {
  const rows = document.querySelectorAll(".media-row");
  const navLinks = document.querySelectorAll(".nav-link");
  const categoryBlocks = document.querySelectorAll(".category-block");

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
});
