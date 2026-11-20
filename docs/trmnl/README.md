# TRMNL "Ce soir" screen

Shows the next planned meal and what is missing for it on the TRMNL ("Fridge"). Mealie does all the work
(`GET /api/households/trmnl/tonight`); [`tonight-full.liquid`](tonight-full.liquid) only lays it out.
Design: [`docs/superpowers/specs/2026-11-11-trmnl-tonight-design.md`](../superpowers/specs/2026-11-11-trmnl-tonight-design.md).

## What the screen says

Top left, a black tab says when (`CE SOIR`, `DEMAIN MIDI`, `SAMEDI SOIR`) next to the date.

| State | Left | Right |
|---|---|---|
| A recipe is planned | Recipe name, time, portions, last verdict, the photo when there is room; at the bottom `Déjà là :` (foods to use soon bold and underlined) | `À acheter`, `N sur M`: a tick-box row per food with the quantity, in shopping-aisle order (by kind of food); under the name `reste 50 ml` when the pantry is short and `déjà sur la liste` (dashed box) when already on a shopping list; then `+ N à vérifier dans la recette` |
| Everything is at home | same, without `Déjà là` | `✓ Rien à acheter`, then `À sortir`: the ingredients to take out, one line per kind of food. Never shown while something can't be checked (a line without a food, units that don't compare, a missing quantity). |
| Free-text entry (no recipe) | The entry's title and `Pas de recette liée dans le planning.` | `À finir vite`: what to use up, or `✓ Rien à finir` |
| Nothing planned in the next 7 days | Just the date and `Aucun repas prévu cette semaine`. `À finir vite` (worst first; `dépassé` black, `à vérifier` dashed, `aujourd'hui` outlined, `N j`), then the fridge | The other places. Each place has one line per kind of food (`FÉCULENTS  pâtes 1 kg · riz 500 g`), with quantities. Nothing to finish: fridge and freezer left, cupboard right, and the header says `✓ Rien à finir en urgence` |

**What is listed.** Only pantry items with a quantity. Staples kept without one (`farine`, `sel`) are left out of
every list, but still count as at home: they never become "à acheter".

**Kind of food.** The food's Mealie label when it has one (the shopping list aisle), else a built-in table of common
French and English names (`mealie/services/claude_context/food_type.py`), else `Autres`. Order: Légumes, Fruits,
Viandes, Poisson, Crèmerie, Fromages, Féculents, Conserves, Pâtisserie, Assaisonner, Condiments, Fruits secs, then
your own labels, then Autres.

**Nothing is cut off.** Text wraps, and a small script in the template shrinks each column's text until it fits, down
to 12 px. Only past that does a column hide its last lines behind `+ N autres`.

Next meal = the first meal still to come in the next 7 days, in the order breakfast, lunch, snack, dinner, side.
A meal ticked cooked is done; today's meal is also done once its hour has passed (breakfast 10:00, lunch 14:00,
snack 17:00, dinner and side 21:00). An entry with a recipe wins over a free-text one. The heading says when:
`CE MIDI · MERCREDI 11 NOV.`, `DEMAIN SOIR · JEUDI 12 NOV.`, `SAMEDI SOIR · 14 NOV.`.

## Setup

1. **Mealie token.** In Mealie: Profile → API Tokens → create one named `TRMNL`. Keep it out of the repo.
2. **TRMNL plugin.** trmnl.com → Plugins → Private Plugin → new:
   - Strategy: **Polling**
   - Polling URL: `https://mealie.christophepecsteen.site/api/households/trmnl/tonight`
   - Polling verb: GET; Polling headers: `authorization=Bearer <token>`
   - Refresh: every 60 minutes
   - Markup → Full: paste [`tonight-full.liquid`](tonight-full.liquid). The JSON's top-level keys are the Liquid
     variables (`kicker`, `recipe.name`, `toBuy`, …).
3. Add the plugin to the **Fridge** playlist.

## Letting TRMNL's servers reach Mealie

TRMNL cloud fetches the URL from outside, but `mealie.christophepecsteen.site` sits behind Cloudflare Access and the
"Block outside Belgium" WAF rule. Open only this path, as was done for `/mcp`:

- **Access**: a Bypass application for `mealie.christophepecsteen.site/api/households/trmnl/tonight`, built like
  the `/mcp` one in [`dev/cloudflare-access-bypass.sh`](../../dev/cloudflare-access-bypass.sh) (that script only
  lists the MCP paths). The Mealie token still protects the endpoint.
- **WAF**: add the same path to the exception of the "Block outside Belgium" rule.
- **Photo**: the recipe photo is fetched by TRMNL from `/api/media/recipes/<id>/images/min-original.webp`. Either
  open `/api/media/recipes/` the same way, or accept that the photo doesn't show (the rest of the screen works).

## Checking it

```sh
curl -s -H "Authorization: Bearer $MEALIE_TOKEN" \
  https://mealie.christophepecsteen.site/api/households/trmnl/tonight | jq
```

Then use "Force refresh" on the plugin in TRMNL and look at its preview.
