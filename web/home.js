const swatches = {
  "ART-SOFA-721": "#8d8578",
  "ART-COF-48R": "#6b4a2b",
  "RUG-8X10-JUT": "#c4b18a",
  "ART-LAMP-ARC": "#b0894b",
  "ART-CHAIR-LEO": "#d8cbb8",
  "IKE-SOFA-KL1": "#9aa0a4",
  "ART-STOR-CRD": "#5c3d24",
  "WSM-DIN-OAK": "#c9b48a",
};

function money(cents) {
  return `$${(cents / 100).toFixed(0)}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function renderCatalog() {
  const root = document.getElementById("products");
  try {
    const response = await fetch("/api/catalog?limit=96");
    const payload = await response.json();
    const featured = ["ART-SOFA-721", "RUG-8X10-JUT", "ART-COF-48R", "ART-LAMP-ARC"];
    const products = (payload.products || []).filter((item) => featured.includes(item.sku));
    const ordered = featured
      .map((sku) => products.find((item) => item.sku === sku))
      .filter(Boolean);
    root.innerHTML = ordered
      .map((item) => {
        const color = swatches[item.sku] || "#d7d1c7";
        const photo = item.image_url
          ? `<img class="product-photo" src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.name)}" onerror="this.remove()">`
          : "";
        return `<article class="product">
          <div class="product-media" style="background:${color}">${photo}</div>
          <div class="product-copy">
            <small>${escapeHtml(item.brand)} · ${escapeHtml(item.sku)}</small>
            <strong>${escapeHtml(item.name)}</strong>
            ${money(item.price_cents)}
          </div>
        </article>`;
      })
      .join("");
  } catch {
    root.innerHTML = "<p class='muted'>Catalog is unavailable.</p>";
  }
}

document.querySelectorAll(".faq-item button").forEach((button) => {
  button.addEventListener("click", () => {
    button.parentElement.classList.toggle("open");
  });
});

renderCatalog();
