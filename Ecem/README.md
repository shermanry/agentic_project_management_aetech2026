# Ecem

## Manufacturing project card: aerial additive manufacturing

This is the manufacturing example from the brief's next step (inspection, monitoring, manufacturing). The project is a building element 3D printed in place by a team of drones, based on the Aerial-AM research (Zhang et al., *Nature* 609, 2022) and Collective Aerial Additive Manufacturing (Stuart-Smith et al.).

It's the hardest of the three cards for a decision tool. Decisions don't stop at planning: one comes up every layer, 72 times for a 2.05 m tower.

### Why drones

Drones turn construction from a machine you bring to the site into a crew that moves through it. They build bigger than themselves and reach where cranes and people can't. That freedom brings flexibility, and with it live data that has to be controlled: wind, robot health, material left, layer deviation, the stability of every in-between stage.

Drones aren't always the answer. Use them only if the structure is bigger than any machine you could put around it, the work is at height or hard to reach, the ground is congested, or the form would need scaffolding that grows with its span. Otherwise a ground method is faster, stronger and more accurate.

### Production steps

17 steps in five phases, with decision gates. Steps 10–15 repeat for every layer.

| Phase | Steps | Gate |
|---|---|---|
| A · Define | 01 Brief and site · 02 Fabrication method | G1 method |
| B · Design | 03 Geometry · 04 Material and tests · 05 Role and tolerance · 06 Digital twin and toolpath · 07 Plan and budget | G2 buildability, G3 design freeze |
| C · Prepare | 08 Site setup · 09 Dry run (light-trace flight) | G4 safety |
| D · Build | 10 Load · 11 Deposit · 12 Scan · 13 Evaluate · 14 Adapt · 15 Layer gate | Layer gate, every layer |
| E · Close | 16 Final validation · 17 Handover | G5 acceptance |

Diagram: `manufacturing-card/assets/14_production_process.svg`. Questions per step: assets `15_` and `16_`, data `production_stages.json`.

### What the team asked for

[`manufacturing-card/card.md`](manufacturing-card/card.md) answers the open items for this card: the inputs and APIs, which node types manufacturing adds, test data with a decision history, a rule pack, and the drone-expert questions from a manufacturing view.

### How it maps to the brief

- **Nodes:** `aerial_am_nodes.csv` / `aerial_am_edges.csv` hold 95 constraint nodes (restrictions, environmental challenges, design and material constraints, metrics, feedback loops, open problems) with typed edges.
- **Decisions:** `decisions.json` holds 24 decisions (design, production, project management), each with options, criteria, linked nodes, gate, cadence, an answer for this case and a decision rule.
- **Role-based views:** `tiers.json` describes Basic, Medium and Advanced. In this card the levels describe how much decision support a project needs; they line up with the brief's client, PM and pilot/designer views.
- **Live data:** the build loop's evaluate step (deviation, cure, stability, wind) is the same pattern as `monitors/`.

### Files

```
manufacturing-card/
  card.md                                      answers to the team's open questions
  seed_manufacturing.py / .json                24 nodes, 22 edges, 8-step replay (northstar seed format)
  rules.json                                   9 rules, aerial-am-manufacturing pack
  data/
    aerial_am_nodes.csv, aerial_am_edges.csv   constraint graph, with team_type and team_relation columns
    decisions.json / .csv, decision.schema.json 24 decisions with answers
    production_stages.json                     17 steps, owners, gates, questions
    tiers.json                                 Basic / Medium / Advanced
    method_comparison.json / .csv              5 fabrication methods × 9 criteria
    drone_rationale.json                       when drones are justified, gains, costs
    tokens.json                                colours and type for the assets
  assets/
    01–16 *.svg                                case-study graphics
    icons/*.svg                                25 icons (phase, level, status, node type)
```

### Sources and confidence

Every node and decision has a `source` or `answer_basis` field. `zhang2022_nature` and `caam_abstract` come from the papers; `dams2024_frontiers_review` from the 2024 *Frontiers in Materials* review. `production_inferred` and `general_knowledge` mark planning additions that need a pilot or expert check: weather limits, failure rules, costs, permits, and ratings for non-aerial methods.

- Zhang et al., Aerial additive manufacturing with multiple autonomous robots, *Nature* 609, 709–717 (2022)
- Stuart-Smith, Darekar, Danahy, Pawar, Kovac, Collective Aerial Additive Manufacturing
- The rise of aerial additive manufacturing in construction, *Frontiers in Materials* (2024)
