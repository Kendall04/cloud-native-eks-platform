// Presentation-only adapter for the five SHA-pinned Archify 3.1.0 exports.
// Exact anchors fail closed. Geometry stays intact; the atomic image role becomes
// a labelled group because its descendants are genuine keyboard controls.
function replaceOnce(html, before, after) {
  if (html.split(before).length !== 2)
    throw new Error("Archify viewport anchor changed: " + before.slice(0, 70));
  return html.replace(before, after);
}
export function adaptViewport(html) {
  html = replaceOnce(
    html,
    'role="img" lang="en" aria-labelledby="archify-diagram-title archify-diagram-description"',
    'role="group" lang="en" aria-labelledby="archify-diagram-title archify-diagram-description"',
  );
  html = replaceOnce(
    html,
    "if (action === 'present') return Archify.presentation.enter();",
    "if (action === 'present') return Archify.view.fitWidth();",
  );
  html = replaceOnce(html, "f: 'present',", "w: 'present',");
  html = replaceOnce(
    html,
    "function setActive(next, options) {\n        options = options || {};\n        next = Boolean(next);",
    "function setActive(next, options) {\n        options = options || {};\n        next = true; // Embedded stage is owned by the React host.",
  );
  html = replaceOnce(
    html,
    "target.closest('[data-node-id], [data-relationship-hit-key], .overview-map, #btn-export, #export-menu')",
    'target.closest(\'[data-node-id], [data-relationship-hit-key], .overview-map, .toolbar, [data-view="in"], [data-view="out"], .fit-width, #btn-export, #export-menu\')',
  );
  html = replaceOnce(
    html,
    "reset: reset,\n        reveal: reveal,",
    `readNode: function (id) {
          var boxes = boxesFor([id], false);
          if (!boxes.length || !viewBox) return;
          stopCameraMotion('reading-guide', false);
          var box = boxes[0], width = svg.clientWidth, height = svg.clientHeight;
          var base = Math.min(width / viewBox.width, height / viewBox.height);
          if (!(base > 0)) return;
          var scale = Math.max(1, Math.min(16, 2 / base, (width - 32) / (box.width * base)));
          var offsetX = (width - viewBox.width * base) / 2;
          var offsetY = (height - viewBox.height * base) / 2;
          // Leave the native semantic passport above the selected component on
          // narrow stages. The guide does not hide it or remove its controls.
          var nodeWidth = box.width * base * scale;
          var besidePassport = width >= nodeWidth + 388;
          var centerX = besidePassport ? Math.max(width / 2, 388 + nodeWidth / 2) : width / 2;
          var centerY = besidePassport ? height / 2 : height - box.height * base * scale / 2 - 24;
          readingNodeId = id;
          state = { scale: scale,
            x: centerX - (offsetX + (box.x + box.width / 2 - viewBox.x) * base) * scale,
            y: centerY - (offsetY + (box.y + box.height / 2 - viewBox.y) * base) * scale,
            mode: 'reading' };
          apply();
        },
        fitWidth: function () {
          stopCameraMotion('fit-width', false);
          var width = svg.clientWidth, height = svg.clientHeight;
          if (!viewBox || width <= 0 || height <= 0) return;
          var base = Math.min(width / viewBox.width, height / viewBox.height);
          var scale = Math.max(1, Math.min(maximumZoom, width * 0.96 / (viewBox.width * base)));
          state = { scale: scale, x: width * (1 - scale) / 2, y: 0, mode: 'width' };
          apply();
        },
        reset: reset,
        reveal: reveal,`,
  );
  html = replaceOnce(
    html,
    "if (state.mode === 'semantic') syncSemantic();\n          else apply();",
    "if (state.mode === 'semantic') syncSemantic();\n          else if (state.mode === 'reading') Archify.view.readNode(readingNodeId);\n          else if (state.mode === 'width') Archify.view.fitWidth();\n          else apply();",
  );
  html = replaceOnce(
    html,
    "var maximumZoom = 3;",
    "var maximumZoom = 16;\n      var readingNodeId = null;",
  );
  // A guided focus may need positive translation for nodes near the top/left.
  // Native manual pan remains clamped; only a bounded, existing node is framed.
  html = replaceOnce(
    html,
    "function clamp() {",
    "function clamp() {\n        if (state.mode === 'reading') return;",
  );
  html = replaceOnce(
    html,
    "function apply() {\n        clamp();\n        svg.style.transform",
    "function apply() {\n        clamp();\n        container.toggleAttribute('data-guided-reading', state.mode === 'reading');\n        svg.style.transform",
  );
  // Only the host owns focus/fullscreen. Keep the inner presentation layout fixed;
  // otherwise Escape/F would introduce a second, conflicting expansion mode.
  html = replaceOnce(
    html,
    "} else if (e.key === 'f' || e.key === 'F') {\n        e.preventDefault();\n        Archify.presentation.toggle();",
    "} else if (e.key === 'w' || e.key === 'W') {\n        e.preventDefault();\n        Archify.view.fitWidth();",
  );
  html = replaceOnce(
    html,
    "} else if (e.key === 'Escape' && Archify.presentation.active()) {\n        e.preventDefault();\n        Archify.presentation.exit();",
    "",
  );
  // The original camera readout remains the single Fit all / reset control.
  html = replaceOnce(
    html,
    "resetBtn.setAttribute('aria-label', readout + ' · '",
    "resetBtn.setAttribute('aria-label', 'Fit all · ' + readout + ' · '",
  );
  return html;
}

export const viewportStyle = `
/* Embedded diagram stage: native tools, one camera, no nested page scrolling. */
html[data-present="true"]:not([data-embed="true"]) body {
  padding: 0; height: 100dvh; overflow: hidden;
}
html[data-present="true"]:not([data-embed="true"]) .container {
  width: 100%; height: 100dvh; max-width: none; gap: 0;
}
html[data-present="true"]:not([data-embed="true"]) .header { display: none; }
html[data-present="true"]:not([data-embed="true"]) .toolbar {
  top: 8px; right: 10px; left: auto; max-width: calc(100% - 20px);
}
#btn-present { display: none !important; }
html[data-present="true"]:not([data-embed="true"]) .diagram-container {
  margin: 0; border: 0; border-radius: 0; overflow: hidden;
  padding: 58px 16px 76px; min-width: 0; min-height: 0;
}
html[data-present="true"]:not([data-embed="true"]) .diagram-container > svg {
  width: 100% !important; height: 100% !important; min-width: 0 !important;
  max-width: none !important; flex: 1 1 auto;
}
.diagram-nav [data-view="reset"]::before { content: "Fit all"; font-size: 11px; margin-right: 5px; }
.fit-width { font: inherit; white-space: nowrap; }
/* Small relationship labels require text contrast, not the lighter node accent. */
html[data-theme="light"] .relationship-lens-row[data-direction="out"] .relationship-lens-direction {
  color: #0e7490;
}
.diagram-container.is-pannable { touch-action: none; }
/* Keep the native passport available in a predictable dock during a tour.
   Its automatic placement otherwise follows the node and can cover it. */
.diagram-container[data-guided-reading] .focus-chip {
  top: 64px !important; left: 12px !important; right: auto !important;
  width: min(352px, calc(100% - 24px)); max-width: calc(100% - 24px);
  max-height: 190px; overflow: auto;
}
@media (max-width: 720px) {
  html[data-present="true"]:not([data-embed="true"]) .diagram-container { padding: 58px 12px 122px; }
  .diagram-nav { flex-wrap: wrap; justify-content: center; overflow: visible; max-width: calc(100% - 16px); }
  .diagram-nav button { flex-shrink: 0; white-space: nowrap; }
  .diagram-nav [data-view="reset"] { min-width: 104px; }
}
`;

export const viewportScript = `
// No storage or network. The parent can only focus an existing diagram node.
// Resize stays inside Archify's native
// rAF camera handler: overview refits, width refits, manual scale is preserved.
var fitWidthButton = document.createElement('button');
fitWidthButton.type = 'button';
fitWidthButton.className = 'fit-width';
fitWidthButton.textContent = 'Fit width';
fitWidthButton.title = 'Fit width (W) · vertical content may need pan/zoom';
fitWidthButton.setAttribute('aria-label', 'Fit diagram width');
fitWidthButton.addEventListener('click', function () { Archify.view.fitWidth(); });
document.querySelector('.diagram-nav').appendChild(fitWidthButton);
var widthGuide = document.querySelector('[data-guide-action="present"]');
widthGuide.setAttribute('aria-label', 'Fit diagram width');
widthGuide.querySelector('strong').textContent = 'Fit width';
widthGuide.querySelector('small').textContent = 'Enlarge tall diagrams; pan to explore. Fit all restores the overview.';
widthGuide.querySelector('kbd').textContent = 'W';
window.addEventListener('message', function (event) {
  var data = event.data;
  if (event.source !== window.parent || !data || typeof data !== 'object' ||
      Object.keys(data).sort().join(',') !== 'id,type' ||
      data.type !== 'archify-focus-node' || typeof data.id !== 'string' ||
      !/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(data.id)) return;
  if (!document.querySelector('[data-node-id="' + data.id + '"]')) return;
  Archify.focus.set(data.id, { toggle: false });
  Archify.view.readNode(data.id);
});
`;
