document.addEventListener("DOMContentLoaded", () => {
  const revealItems = document.querySelectorAll("[data-reveal]");
  const dismissButtons = document.querySelectorAll("[data-dismiss-flash]");

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.18 }
    );

    revealItems.forEach(item => observer.observe(item));
  } else {
    revealItems.forEach(item => item.classList.add("is-visible"));
  }

  dismissButtons.forEach(button => {
    button.addEventListener("click", () => {
      const flash = button.closest("[data-flash]");
      if (flash) {
        flash.remove();
      }
    });
  });

  window.setTimeout(() => {
    document.querySelectorAll("[data-flash]").forEach(flash => flash.remove());
  }, 5000);
});