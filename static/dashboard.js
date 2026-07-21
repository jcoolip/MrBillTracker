document.querySelectorAll(".category-heading").forEach((heading) => {

    heading.addEventListener("click", () => {

        const panel = heading.closest(".category-panel");

        panel.classList.toggle("collapsed");

        const symbol = heading.querySelector(".category-toggle");

        symbol.textContent =
            panel.classList.contains("collapsed")
                ? "[+]"
                : "[-]";

    });

});
