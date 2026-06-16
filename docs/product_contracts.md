# Spario Product Contracts

Documentation only. This file defines product and backend-facing contracts for
category taxonomy, access policy, and Spario Insight language. It does not
change runtime behavior, schema, API responses, ranking, importers, or frontend.

## A. Purpose

Spario needs product contracts before frontend and premium decisions because the
UX must stay honest about what the backend can actually support.

Spario is not a coupon app, marketplace, or simple price comparator. The promise
is:

```text
Spario does not only tell the user where it costs less.
It tells the user whether it makes sense to buy now.
```

That promise only works if three layers stay coherent:

- product categories are clear and stable
- access rules explain what each user can do
- prediction language reflects actual data quality

Current backend reality:

- the catalog is structurally healthy
- product/offers/history relationships are clean
- data depth is still limited
- only 1 product currently has multiple offers
- average price history depth is 1.06 points per product
- 189/194 products are still `insufficient_data`
- 0/194 products have stronger buy/wait signal
- product titles are often long/noisy
- product matching must remain conservative

UX consequence:

- product discovery can be useful now
- comparison should be honest when only one store is available
- Spario Insight must use conservative language
- strong buy/wait claims must wait until price history is deeper and fresher

## B. Product Category Taxonomy

The MVP taxonomy should feel like a serious electronics shopping assistant, not
an internal database dump.

Recommended clean category order for UI:

1. Smartphones
2. Headphones & Audio
3. TV & Home Entertainment
4. Gaming & Consoles
5. Accessories
6. Laptops & Computers
7. Smart Home
8. Home Appliances
9. Supermarket

### Category Contract

| Internal key | Italian label | Description | Examples | MVP priority | Matching complexity | Emphasize |
| --- | --- | --- | --- | --- | --- | --- |
| `smartphone` | Smartphone | Phones and mobile devices where model/storage matter. | iPhone, Samsung Galaxy, Xiaomi, Motorola | high | medium | now |
| `cuffie` | Cuffie e audio | Headphones, earbuds, audio wearables, small speakers when relevant. | AirPods, Sony WH, Bose, JBL earbuds | high | medium | now |
| `tv` | TV e home entertainment | TVs and living-room entertainment devices. | OLED TV, QLED TV, Smart TV, soundbar later | high | high | now, but carefully |
| `gaming` | Gaming e console | Consoles and core gaming hardware. | PS5, Xbox, Nintendo Switch | high | medium | now |
| `gaming_accessori` | Accessori gaming | Gaming accessories and peripherals. | controller, headset, dock, charging station | medium | medium | now, selected |
| `accessori` | Accessori tech | General electronics accessories. | chargers, cables, cases, storage | medium | medium | later/selected |
| `laptop` | Laptop e computer | Laptops, desktop PCs, monitors, all-in-one devices. | MacBook, HP laptop, Lenovo, desktop PC | medium | high | later/limited |
| `smart_home` | Casa smart | Connected home products. | Echo, Nest, smart bulbs, cameras | future | medium | later |
| `home_appliances` | Elettrodomestici | Home appliances and large domestic devices. | washing machine, coffee machine, vacuum | future | high | future |
| `supermarket` | Supermercato | Grocery and recurring consumer goods. | food, personal care, household goods | future | high | future |
| `unknown` | Altro | Fallback for unmapped or uncertain categories. | uncategorized product | none | unknown | do not emphasize |

### MVP Focus

Focus now:

- smartphones
- headphones/earbuds
- TVs
- gaming consoles
- gaming accessories

Use caution:

- laptops, because CPU/RAM/SSD/screen/model variants are complex
- supermarket and home categories, because they require different data logic and
  are not MVP electronics priorities
- home appliances, because model matching, shipping, and local availability can
  be messy

### Category Card Labels In Italian

Recommended UI card labels:

- Smartphone
- Cuffie e audio
- TV e cinema
- Gaming
- Accessori gaming
- Laptop e PC
- Casa smart
- Elettrodomestici

Shorter mobile labels:

- Smartphone
- Cuffie
- TV
- Gaming
- Accessori
- Laptop
- Casa smart

### Category Empty State Microcopy

Use calm, honest copy:

- Smartphone: "Stiamo tracciando nuovi smartphone. Prova iPhone, Samsung o Xiaomi."
- Cuffie e audio: "Nuove cuffie in arrivo. Prova AirPods, Sony, Bose o JBL."
- TV e cinema: "Stiamo ampliando le TV tracciate. Prova OLED, QLED o Smart TV."
- Gaming: "Stiamo tracciando console e accessori gaming. Prova PS5, Xbox o Nintendo."
- Laptop e PC: "Categoria in espansione. I laptop richiedono controlli più accurati."
- Generic: "Non abbiamo ancora abbastanza prodotti affidabili in questa categoria."

### Mapping Messy Backend Categories

Frontend-facing category mapping should be stable even if importer categories
are messy.

Rules:

- map `smartphone`, `telefono`, `cellulari` to `smartphone`
- map `cuffie`, `auricolari`, `audio`, `speaker`, `casse_audio` to `cuffie`
- map `tv`, `smart_tv`, `televisori`, `home_cinema` to `tv`
- map `gaming`, `console`, `ps5`, `xbox`, `nintendo` to `gaming`
- map `controller`, `headset_gaming`, `dock`, `gaming_accessori` to `gaming_accessori`
- map `laptop`, `notebook`, `desktop`, `pc`, `computer` to `laptop`
- map unknown or low-confidence category to `unknown`

When category is unknown:

- do not hide the product if price data is valid
- show it under "Altro" or in search results only
- avoid category-specific insight copy
- prioritize fixing importer mapping later

## C. Guest / Free / Premium Access Policy

Access policy should let users understand Spario's value before asking for too
much commitment.

Do not make Spario AI fully invisible to every non-premium user too early.
Spario needs a preview loop: users should feel the value, then upgrade for
deeper monitoring and decision support.

### User Types

| User type | Access level | Product intent |
| --- | --- | --- |
| Guest | browse and preview | understand value with low friction |
| Registered Free | limited personal use | save intent and sample assistant |
| Premium | full decision support | monitoring, alerts, advanced guidance |

### Guest

Guest can:

- use simple catalog/search
- see product cards
- view basic product detail
- compare visible prices/offers when available
- see limited Spario Insight state labels
- see Spario AI preview/teaser

Guest cannot:

- save wishlist
- create alerts
- use personal monitoring
- access full Spario AI guidance
- see advanced alternatives or deep history

Guest goal:

- understand what Spario does in under 30 seconds
- reach sign-up only when they try to personalize

### Registered Free

Free user can:

- use catalog/search
- view product detail
- use limited Spario AI advice previews
- save a limited wishlist, if product plan allows
- create limited/basic alerts, if product plan allows
- see basic "tracking/data limited" insight language
- receive upgrade prompts for advanced decision support

Suggested limits:

- limited number of saved products
- limited number of active alerts
- limited AI responses per period
- no priority tracking
- no advanced alternatives

Free user goal:

- experience recurring value
- build trust before premium conversion

### Premium

Premium user gets:

- full Spario AI
- smarter alerts
- automatic product monitoring
- advanced product alternatives
- price history access when available
- buy/wait/monitor guidance when data supports it
- priority tracking for wishlist products
- future local offer intelligence if implemented

Premium should not mean "fake certainty." Even Premium users should see
conservative insight states when data is shallow.

### Recommended Paywall Model

Use a preview/paywall model:

- Guest sees teaser
- Free sees limited AI advice
- Premium gets complete guidance and monitoring

Do not block too early:

- basic product search
- product cards
- visible offers
- basic product detail
- simple comparison when data exists

Paywall trigger points:

- saving wishlist
- creating an alert
- asking for repeated monitoring
- viewing deeper price history
- asking Spario AI for advanced alternatives
- requesting full buy/wait reasoning
- tracking more than the free limit

### Guest Sign-Up Prompts

Prompt when the user tries to personalize:

- "Crea un account per salvare questo prodotto."
- "Accedi per ricevere avvisi quando il prezzo cambia."
- "Vuoi ritrovare questo prodotto più tardi? Salvalo gratis."

### Premium Upgrade Copy

Use calm, value-based Italian copy:

- "Sblocca il monitoraggio automatico"
- "Ricevi avvisi più intelligenti sui prodotti che ti interessano"
- "Con Premium Spario segue i prezzi per te"
- "Ottieni consigli più completi quando ci sono abbastanza dati"
- "Vedi alternative migliori prima di comprare"

Avoid pushy copy:

- "Offerta imperdibile"
- "Compra subito"
- "Ultima occasione"
- "Prezzo garantito"
- "Spario sa già cosa succederà"

## D. Prediction / Spario Insight Contract

Spario Insight is the safe UX layer for decision guidance. It should never
pretend that prediction is stronger than the data.

Required states:

| Internal key | Italian label | When to use | Allowed CTA | Disallowed claims |
| --- | --- | --- | --- | --- |
| `insufficient_data` | Storico ancora limitato | 0-1 valid history points, no reliable trend, missing comparable store history | Monitora prezzo | "Compra ora", "Aspetta, scenderà" |
| `tracking_active` | Tracking attivo | User is tracking product but data is still shallow | Ricevi aggiornamenti | "Previsione affidabile" |
| `monitor` | Da monitorare | Price exists, some context exists, but signal is not strong | Aggiungi alert | "Conviene sicuramente" |
| `weak_signal` | Segnale iniziale | 4-9 valid points or early useful pattern, still limited | Valuta con cautela | "Prezzo previsto" as certainty |
| `stronger_signal` | Dati sufficienti | 10+ fresh valid points and backend readiness supports stronger guidance | Vedi perché | "Garantito", "scenderà di sicuro" |

### State Copy

`insufficient_data`

- Label: "Storico ancora limitato"
- Copy: "Spario sta raccogliendo dati. Per ora non ci sono abbastanza informazioni per una previsione affidabile."
- CTA: "Monitora prezzo"
- Avoid: "Compra ora", "Aspetta, scenderà"

`tracking_active`

- Label: "Tracking attivo"
- Copy: "Stiamo seguendo questo prodotto per rilevare variazioni significative."
- CTA: "Ricevi aggiornamenti"
- Avoid: "Previsione affidabile", "Trend confermato"

`monitor`

- Label: "Da monitorare"
- Copy: "Il prezzo è interessante, ma i dati non bastano ancora per un consiglio forte."
- CTA: "Aggiungi alert"
- Avoid: "Compra subito", "Aspetta sicuramente"

`weak_signal`

- Label: "Segnale iniziale"
- Copy: "I dati disponibili mostrano un primo segnale, ma lo storico è ancora limitato."
- CTA: "Valuta con cautela"
- Avoid: "Previsione certa", "Prezzo garantito"

`stronger_signal`

- Label: "Dati sufficienti"
- Copy: "Lo storico disponibile permette una valutazione più affidabile."
- CTA: "Vedi perché"
- Note: only use when actual backend readiness supports it.
- Avoid: "Sicuro", "garantito", fake urgency

### Product Detail Copy Rules

Product detail should show a "Spario Insight" area with:

- insight state label
- short explanation
- current best offer when available
- history limitation if data is shallow
- CTA based on user access level

Do not show a large prediction block when data is insufficient. In that case,
use a compact trust-building message:

"Stiamo raccogliendo storico su questo prodotto. Puoi monitorarlo per ricevere
aggiornamenti quando il prezzo cambia."

### Spario AI Answer Copy Rules

Spario AI should:

- answer directly with real prices and stores only
- say when comparison is limited to one store
- say when history is insufficient
- prefer "monitor" language when data is shallow
- avoid pretending that GPT can forecast price changes

Allowed:

- "Al momento il prezzo migliore tracciato è..."
- "Ho pochi dati storici, quindi non posso dare una previsione forte."
- "Puoi monitorarlo: Spario continuerà a raccogliere prezzi."

Disallowed:

- "Il prezzo scenderà"
- "Compra ora con certezza"
- "Sarà più economico domani"
- "Previsione garantita"

### Product Card Copy Rules

Product cards should stay light:

- show product name
- show best current price
- show store name when available
- show a short insight badge only
- avoid long prediction explanations

Good badges:

- "Storico limitato"
- "Da monitorare"
- "Segnale iniziale"
- "Dati sufficienti"

Avoid:

- long AI reasoning inside cards
- countdowns
- fake urgency
- overconfident buy/wait labels

### Fallback Text

When no prediction data exists:

"Non ho ancora abbastanza storico per una previsione affidabile."

When no offer exists:

"Non ho offerte valide tracciate per questo prodotto al momento."

When only one store exists:

"Il confronto è limitato: al momento ho dati da un solo negozio."

### Terms To Avoid

Avoid:

- guaranteed
- sure prediction
- price will go down
- buy now with certainty
- countdown
- fake urgency
- last chance
- unbeatable
- certain saving

Italian equivalents to avoid:

- garantito
- sicuro
- scenderà sicuramente
- compra ora senza dubbi
- ultima occasione
- conto alla rovescia
- risparmio certo

## E. Frontend Implementation Guidance

This section is guidance for Lovable/frontend only. It does not require backend
changes in this step.

Search should feel like product discovery/catalog:

- fast
- visual
- browsable
- product/category oriented
- no heavy AI copy in every card

Spario AI should feel like decision support:

- natural language input
- concise answer
- product cards from real Supabase data
- clear limitation when data is shallow
- premium value tied to monitoring and guidance

Product detail should show "Spario Insight":

- compact state badge
- short explanation
- best offer comparison
- history limitation when relevant
- CTA based on Guest/Free/Premium state

Product cards should not become too text-heavy:

- one price
- one store
- one status badge
- one primary action

Guest should not be confused by locked features:

- show what is available
- lock only personal/advanced actions
- explain why sign-up helps

Premium upsells should explain value, not pressure:

- "Spario segue i prezzi per te"
- "Ricevi avvisi più intelligenti"
- "Sblocca consigli più completi"

Keep dark premium style:

- calm
- trustworthy
- no fake urgency
- no coupon-like visual noise

## F. Backend / Future API Considerations

Do not implement these in this step. These are future contract needs.

Future API or schema may need:

- standardized category keys
- user access entitlement flags
- `prediction_state` or `spario_insight_state`
- reason codes for insufficient data
- price history depth indicators
- product matching confidence
- data freshness indicators
- store count per product
- offer count per product
- latest history timestamp
- confidence source, such as structured parser vs fallback parser

Potential future fields or response concepts:

- `category_key`
- `access_level`
- `can_save_wishlist`
- `can_create_alert`
- `can_use_full_ai`
- `insight_state`
- `insight_reason_code`
- `history_points`
- `history_freshness`
- `matching_confidence`

These are not implemented now. They should be introduced only after product
decisions are stable and backend readiness supports them.

## G. Recommended Decisions

Recommended product decisions:

- Do not make Spario AI fully invisible to non-premium users yet.
- Let Guest users use basic comparator/search.
- Let Guest users see AI teaser/preview, not full value.
- Let Free users sample limited Spario AI.
- Put full AI decision support behind Premium.
- Put smart alerts, monitoring, advanced alternatives, and deeper insights
  behind Premium.
- Use conservative prediction language until price history improves.
- Organize categories like a serious online store.
- Keep MVP categories limited.
- Do not emphasize supermarket/home categories yet.
- Do not overpromise buy/wait guidance while 0/194 products have stronger
  signal.

Recommended MVP category emphasis:

1. Smartphone
2. Cuffie e audio
3. TV e cinema
4. Gaming
5. Accessori gaming

Recommended access model:

```text
Guest: discover and preview
Free: save limited intent and sample AI
Premium: full monitoring and decision support
```

Recommended insight model:

```text
insufficient_data -> tracking_active -> monitor -> weak_signal -> stronger_signal
```

## H. Next UX Steps

1. Clean category navigation/cards
   - use the clean taxonomy labels
   - hide or de-emphasize future categories
   - map messy backend categories to stable UI categories

2. Define Guest/Free/Premium UI gates
   - decide exact free wishlist and alert limits
   - keep search and product detail accessible
   - gate monitoring and advanced guidance

3. Add safe Spario Insight states to product detail
   - start with conservative states
   - show limited-history copy often
   - do not show strong buy/wait unless backend readiness supports it

4. Adjust Spario AI entry/paywall
   - Guest teaser
   - Free limited advice
   - Premium full decision support

5. Refine product cards with less technical language
   - avoid dumping backend confidence terms
   - show simple user-facing badges
   - keep cards scannable

6. Keep dark premium style
   - serious, calm, modern
   - no coupon-app urgency
   - no fake countdowns
   - no overpromising

## Final Contract Summary

Spario should feel like a premium decision-support assistant built on real data.

The frontend can show discovery value now, but advanced insight must be tied to
actual backend readiness. Categories should be clean, access gates should be
calm, and prediction copy should stay honest until price history is deep enough.
