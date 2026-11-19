document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("mobileToggle");
  const nav = document.getElementById("mainNav");
  if (toggle && nav) toggle.addEventListener("click", () => nav.classList.toggle("open"));

  document.querySelectorAll(".flash-close").forEach(btn => btn.addEventListener("click", () => btn.parentElement.remove()));

  document.querySelectorAll("form[data-confirm]").forEach(form => {
    form.addEventListener("submit", event => {
      if (!window.confirm(form.dataset.confirm || "Are you sure?")) event.preventDefault();
    });
  });

  const roleSelect = document.getElementById("roleSelect");
  const roleBlocks = document.querySelectorAll(".role-extra");
  function updateRoleFields() {
    roleBlocks.forEach(block => {
      const active = block.dataset.role === roleSelect?.value;
      block.style.display = active ? "grid" : "none";
      block.querySelectorAll("input").forEach(input => input.disabled = !active);
    });
  }
  if (roleSelect) {
    roleSelect.addEventListener("change", updateRoleFields);
    updateRoleFields();
  }

  const provider = document.getElementById("providerSelect");
  const policy = document.getElementById("policyNumber");
  if (provider && policy) {
    const sync = () => { policy.value = provider.selectedOptions[0]?.dataset.policy || ""; };
    provider.addEventListener("change", sync);
    sync();
  }

  document.querySelectorAll("input[type=file]").forEach(input => {
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (file && file.size > 10 * 1024 * 1024) {
        alert("Please select a file smaller than 10 MB.");
        input.value = "";
      }
    });
  });
});
