// Markdown from models and remote papers is untrusted. Keep a small HTML vocabulary.
const allowedTags = new Set([
  "P",
  "BR",
  "STRONG",
  "B",
  "EM",
  "I",
  "S",
  "DEL",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
  "UL",
  "OL",
  "LI",
  "BLOCKQUOTE",
  "PRE",
  "CODE",
  "TABLE",
  "THEAD",
  "TBODY",
  "TR",
  "TH",
  "TD",
  "HR",
  "A",
]);
export function renderMarkdown(markdown) {
  const container = document.createElement("div");
  if (!window.marked) {
    container.textContent = markdown || "";
    return container;
  }
  const doc = new DOMParser().parseFromString(
    window.marked.parse(markdown || ""),
    "text/html",
  );
  function copy(node, parent) {
    if (node.nodeType === Node.TEXT_NODE) {
      parent.append(document.createTextNode(node.textContent));
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    if (!allowedTags.has(node.tagName)) {
      // Disallow both active content and its descendants, including SVG/MathML.
      return;
    }
    const clean = document.createElement(node.tagName.toLowerCase());
    if (node.tagName === "A") {
      const href = node.getAttribute("href") || "";
      try {
        const url = new URL(href, window.location.origin);
        if (["http:", "https:"].includes(url.protocol)) {
          clean.href = url.href;
          clean.rel = "noopener noreferrer";
          clean.target = "_blank";
        }
      } catch {
        /* retain link text without navigation */
      }
    }
    for (const child of node.childNodes) copy(child, clean);
    parent.append(clean);
  }
  for (const child of doc.body.childNodes) copy(child, container);
  return container;
}

export function moleculeCard({ name, smiles, label }) {
  const figure = document.createElement("figure");
  const image = document.createElement("img");
  const params = new URLSearchParams(smiles ? { smiles } : { name });
  image.src = `/api/molimg?${params}`;
  image.alt = `${name || "类似物"} 分子结构`;
  image.loading = "lazy";
  image.width = 260;
  image.height = 200;
  image.addEventListener(
    "error",
    () => {
      const message = document.createElement("div");
      message.className = "image-error";
      message.textContent = "结构图暂不可用";
      image.replaceWith(message);
    },
    { once: true },
  );
  const caption = document.createElement("figcaption");
  caption.textContent = label || name;
  figure.append(image, caption);
  return figure;
}
