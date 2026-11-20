/* ================================================================
   Custom select — replaces the OS-drawn dropdown list (which CSS can't
   style) with one that matches the design system.

   Progressive enhancement: the native <select> stays in the DOM, hidden,
   and remains the single source of truth. So existing code keeps working
   untouched — inline onchange handlers, reading .value, and setting .value
   programmatically (the trigger re-syncs automatically).

   Keyboard: Enter / Space / ↑ / ↓ open; ↑ ↓ Home End move; Enter selects;
   Esc or Tab closes; typing a letter jumps to the next matching option.
================================================================ */
(function () {
  "use strict";

  const CHECK_SVG =
    '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const valueDesc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value");
  const indexDesc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "selectedIndex");
  let openInstance = null;
  let uid = 0;

  function labelOf(select) {
    const opt = select.options[select.selectedIndex];
    return opt ? opt.textContent.trim() : "";
  }

  function enhance(select) {
    if (select.dataset.csEnhanced || select.multiple || select.size > 1) return;
    select.dataset.csEnhanced = "1";
    const id = "cs-" + ++uid;

    const wrap = document.createElement("div");
    wrap.className = "cs";
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "cs-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    trigger.setAttribute("aria-controls", id + "-list");
    const label = select.getAttribute("aria-label");
    if (label) trigger.setAttribute("aria-label", label);
    trigger.innerHTML = '<span class="cs-sizer" aria-hidden="true"></span><span class="cs-label"></span>';
    const list = document.createElement("div");
    list.className = "cs-list";
    list.id = id + "-list";
    list.setAttribute("role", "listbox");
    list.hidden = true;
    if (label) list.setAttribute("aria-label", label);

    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    wrap.appendChild(trigger);
    wrap.appendChild(list);
    select.classList.add("cs-native");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");

    const inst = { select, wrap, trigger, list, active: -1, items: [] };

    // Keep the trigger in sync when code sets .value / .selectedIndex directly.
    Object.defineProperty(select, "value", {
      configurable: true,
      get() { return valueDesc.get.call(this); },
      set(v) { valueDesc.set.call(this, v); sync(inst); },
    });
    Object.defineProperty(select, "selectedIndex", {
      configurable: true,
      get() { return indexDesc.get.call(this); },
      set(v) { indexDesc.set.call(this, v); sync(inst); },
    });

    // Options replaced (e.g. month list), hidden toggled, classes changed (is-set).
    new MutationObserver(() => { build(inst); sync(inst); })
      .observe(select, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["hidden", "class", "disabled"] });
    select.addEventListener("change", () => sync(inst));

    trigger.addEventListener("click", () => (openInstance === inst ? close(inst, true) : open(inst)));
    trigger.addEventListener("keydown", e => onTriggerKey(inst, e));
    list.addEventListener("keydown", e => onListKey(inst, e));
    list.addEventListener("mousemove", e => {
      const item = e.target.closest(".cs-option");
      if (item) setActive(inst, inst.items.indexOf(item), false);
    });
    list.addEventListener("mousedown", e => e.preventDefault()); // keep focus, avoid blur-close
    list.addEventListener("click", e => {
      const item = e.target.closest(".cs-option");
      if (item) choose(inst, inst.items.indexOf(item));
    });

    build(inst);
    sync(inst);
  }

  function build(inst) {
    const { select, list, trigger } = inst;
    list.innerHTML = "";
    inst.items = [];
    const sizer = trigger.querySelector(".cs-sizer");
    sizer.innerHTML = "";
    const addOption = (opt, parent) => {
      const item = document.createElement("div");
      item.className = "cs-option";
      item.setAttribute("role", "option");
      item.id = list.id + "-" + inst.items.length;
      item.dataset.index = String(opt.index);
      item.innerHTML = '<span class="cs-option-label"></span>' + CHECK_SVG;
      item.firstChild.textContent = opt.textContent.trim();
      if (opt.disabled) item.setAttribute("aria-disabled", "true");
      parent.appendChild(item);
      inst.items.push(item);
      const s = document.createElement("span");
      s.textContent = opt.textContent.trim();
      sizer.appendChild(s);
    };
    Array.from(select.children).forEach(child => {
      if (child.tagName === "OPTGROUP") {
        const group = document.createElement("div");
        group.className = "cs-group";
        group.setAttribute("role", "group");
        const head = document.createElement("div");
        head.className = "cs-group-label";
        head.textContent = child.label;
        group.setAttribute("aria-label", child.label);
        group.appendChild(head);
        Array.from(child.children).forEach(o => addOption(o, group));
        list.appendChild(group);
      } else if (child.tagName === "OPTION") {
        addOption(child, list);
      }
    });
  }

  function sync(inst) {
    const { select, wrap, trigger } = inst;
    trigger.querySelector(".cs-label").textContent = labelOf(select);
    // Mirror the select's own classes (filter-select, is-set, size variants) onto the trigger.
    trigger.className = "cs-trigger " + Array.from(select.classList).filter(c => c !== "cs-native").join(" ");
    wrap.hidden = select.hidden;
    trigger.disabled = select.disabled;
    const sel = select.selectedIndex;
    inst.items.forEach(item => item.setAttribute("aria-selected", String(+item.dataset.index === sel)));
  }

  function open(inst) {
    if (openInstance && openInstance !== inst) close(openInstance, false);
    openInstance = inst;
    const { list, trigger, wrap } = inst;
    list.hidden = false;
    wrap.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    position(inst);
    const selIdx = inst.items.findIndex(i => i.getAttribute("aria-selected") === "true");
    setActive(inst, selIdx >= 0 ? selIdx : 0, true);
    list.tabIndex = -1;
    list.focus({ preventScroll: true });
  }

  function close(inst, refocus) {
    const { list, trigger, wrap } = inst;
    list.hidden = true;
    wrap.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
    list.removeAttribute("aria-activedescendant");
    if (openInstance === inst) openInstance = null;
    if (refocus) trigger.focus({ preventScroll: true });
  }

  // The list is position:fixed so it is never clipped by a scrolling parent
  // (e.g. the tracker table). Open below the trigger, or above if there's more
  // room there; keep it inside the viewport horizontally.
  function position(inst) {
    const { list, trigger } = inst;
    const GAP = 6, EDGE = 8, MAX_H = 320;
    const t = trigger.getBoundingClientRect();
    list.style.minWidth = t.width + "px";
    list.style.maxHeight = "";
    const below = window.innerHeight - t.bottom - GAP - EDGE;
    const above = t.top - GAP - EDGE;
    const natural = Math.min(list.scrollHeight, MAX_H);
    const openUp = natural > below && above > below;
    const h = Math.min(natural, openUp ? above : below);
    list.style.maxHeight = h + "px";
    list.style.top = (openUp ? t.top - GAP - h : t.bottom + GAP) + "px";
    const w = list.offsetWidth;
    let left = t.left;
    if (left + w > window.innerWidth - EDGE) left = Math.max(EDGE, t.right - w);
    list.style.left = left + "px";
  }

  function setActive(inst, idx, scroll) {
    const { items, list } = inst;
    if (!items.length) return;
    idx = Math.max(0, Math.min(items.length - 1, idx));
    if (inst.active >= 0 && items[inst.active]) items[inst.active].classList.remove("is-active");
    inst.active = idx;
    items[idx].classList.add("is-active");
    list.setAttribute("aria-activedescendant", items[idx].id);
    if (scroll) {
      // Scroll only the list (scrollIntoView could also scroll the page, which closes the list).
      const item = items[idx];
      const top = item.offsetTop, bottom = top + item.offsetHeight;
      if (top < list.scrollTop) list.scrollTop = top - 4;
      else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight + 4;
    }
  }

  function choose(inst, idx) {
    const item = inst.items[idx];
    if (!item || item.getAttribute("aria-disabled") === "true") return;
    const { select } = inst;
    const changed = select.selectedIndex !== +item.dataset.index;
    select.selectedIndex = +item.dataset.index;
    close(inst, true);
    if (changed) select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function onTriggerKey(inst, e) {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
      e.preventDefault();
      open(inst);
    }
  }

  let typeBuffer = "", typeTimer = null;
  function onListKey(inst, e) {
    const { items } = inst;
    switch (e.key) {
      case "ArrowDown": e.preventDefault(); setActive(inst, inst.active + 1, true); break;
      case "ArrowUp":   e.preventDefault(); setActive(inst, inst.active - 1, true); break;
      case "Home":      e.preventDefault(); setActive(inst, 0, true); break;
      case "End":       e.preventDefault(); setActive(inst, items.length - 1, true); break;
      case "Enter":
      case " ":         e.preventDefault(); choose(inst, inst.active); break;
      case "Escape":    e.preventDefault(); close(inst, true); break;
      case "Tab":       close(inst, false); break;
      default:
        if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
          clearTimeout(typeTimer);
          typeBuffer += e.key.toLowerCase();
          typeTimer = setTimeout(() => (typeBuffer = ""), 600);
          const start = typeBuffer.length === 1 ? inst.active + 1 : inst.active;
          for (let k = 0; k < items.length; k++) {
            const i = (start + k) % items.length;
            if (items[i].textContent.trim().toLowerCase().startsWith(typeBuffer)) { setActive(inst, i, true); break; }
          }
        }
    }
  }

  // Close on outside click, scroll of the page, or resize.
  document.addEventListener("mousedown", e => {
    if (openInstance && !openInstance.wrap.contains(e.target)) close(openInstance, false);
  });
  window.addEventListener("resize", () => openInstance && close(openInstance, false));
  document.addEventListener("scroll", e => {
    if (openInstance && !openInstance.list.contains(e.target)) close(openInstance, false);
  }, true);

  function enhanceAll(root) {
    (root.querySelectorAll ? root.querySelectorAll("select") : []).forEach(enhance);
  }

  // Enhance what's on the page now, and anything rendered later (e.g. tracker rows).
  function start() {
    enhanceAll(document);
    new MutationObserver(muts => {
      for (const m of muts) {
        m.addedNodes.forEach(n => {
          if (n.nodeType !== 1) return;
          if (n.tagName === "SELECT") enhance(n);
          else enhanceAll(n);
        });
      }
    }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();

  window.enhanceSelect = enhance;
})();
