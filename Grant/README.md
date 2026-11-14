# Grant

Front-end and interface work: perspectives, the canvas, decision nodes and project setup.

## Prototype

Self-contained HTML pages. Open any of them in a browser; no build step. The 3D graph loads three.js from cdnjs, so it needs internet. All project data in them is invented.

| File | What it is |
| --- | --- |
| `prototype/base-layer.html` | The clickable base platform. It starts with project setup; choose "Open a full example project" for the Harbor Street Clinic example. It has four perspectives (Decisions, Canvas, List, Graph), statement-style decision nodes, a decision page with Compare, Dashboard and Record layouts, and a Design / Operations switch where decisions report live data against their targets. |
| `prototype/node-study.html` | Visual language study: node anatomy, content previews, semantic zoom, link styles, states and decision layouts. |
| `prototype/decision-node.html` | Three directions for the decision node. We chose A (the statement) for the canvas, with C (the balance) inside the Compare layout. |

## Decisions and dashboards

A dashboard is one face of a decision. When a decision is made, it commits to targets. Once the building is in use, live data is measured against them, and each target reports *on track*, *at risk* or *missed*. A missed target sets the decision to *needs review*. The draft contract between decisions and dashboards is in the front-end concepts doc.
