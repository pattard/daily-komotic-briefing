"""Conservative, explainable relevance scoring; never alters source evidence.

Match specific developments within a title or sentence, not bags of keywords
across an entire page. Repeated buzzwords and watchlist mentions cannot qualify
a story by themselves. English, French and Spanish cover the configured feeds.
"""
from __future__ import annotations

import re
import unicodedata


def normalise(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


def near(left: str, right: str, distance: int = 100) -> str:
    # No sentence-spanning co-occurrence; either word order is allowed.
    return rf"(?:{left}).{{0,{distance}}}(?:{right})|(?:{right}).{{0,{distance}}}(?:{left})"


CHANGE = (r"\b(?:launch\w*|introduc\w*|announc\w*|unveil\w*|add\w*|new|change\w*|"
          r"updat\w*|rais\w*|cut\w*|reduc\w*|remov\w*|end\w*|switch\w*|expand\w*|"
          r"debut\w*|roll\w*|revis\w*|allow\w*|enable\w*|now|offer\w*|set|"
          r"lanc\w*|nouve\w*|annonc\w*|ajout\w*|modifi\w*|augmen\w*|permet\w*|"
          r"desormais|lanz\w*|nuev\w*|anunci\w*|anad\w*|cambi\w*|permit\w*)\b")
PLATFORM = (r"\b(?:platform\w*|plataforma\w*|plateforme\w*|marketplace\w*|"
            r"app|apps|application\w*|aplicacion\w*|reader|reading service|"
            r"digital (?:comics? )?(?:store|shop|library)|publishing service|"
            r"service de lecture|boutique numerique|tienda digital)\b")
COMPANY = (r"\b(?:company|companies|business|publisher\w*|studio\w*|platform\w*|"
           r"app|service|entreprise\w*|societe\w*|editeur\w*|editorial\w*|"
           r"empresa\w*|plateforme\w*|plataforma\w*)\b")
LAUNCH = r"\b(?:launch\w*|introduc\w*|unveil\w*|debut\w*|lanc\w*|lanz\w*)\b"
# Object modifiers are bounded and cannot jump over a title/issue or a
# preposition such as 'on the platform' to turn a release into an app launch.
MODIFIERS = (r"(?:(?:a|an|the|its|their|new|dedicated|digital|comics?|comic[ -]reading|"
             r"reading|publishing|responsive|adaptive|free|paid|mobile|un|une|la|le|"
             r"nouvelle|nouveau|numerique|de|lecture|una|nueva|nuevo|su)\s+){0,8}")

# Each category contributes once; title matches carry more weight. Generic
# 'launch', 'publishing', 'licensing' and 'digital' are deliberately not signals.
POSITIVE = {
    "acquisition_merger": near(
        r"\b(?:acquir\w*|acquisition\w*|merg\w*|buyout|takeover|rachat\w*|"
        r"rachet\w*|fusion\w*|adquisicion\w*|adquier\w*|compra de)\b", COMPANY),
    "closure_restructuring": near(
        r"\b(?:shutdown|shut(?:s|ting)? down|clos(?:es|ing|ure)|ceas\w*|bankrupt\w*|"
        r"insolven\w*|restructur\w*|layoffs?|redundan\w*|fermeture\w*|ferm\w*|"
        r"liquidation|cierre\w*|cierra\w*|despid\w*|reestructur\w*)\b", COMPANY),
    "funding": near(
        r"\b(?:rais\w*|secur\w*|receiv\w*|invest\w*|leve\w*|obtient|capta\w*|"
        r"recibe|ronda\w*)\b",
        r"\b(?:funding|capital|financing|investment|series [a-f]|financement|"
        r"fonds|inversion|financiacion)\b"),
    # Recognise noun phrases such as 'launch of a dedicated app' while still
    # requiring a platform object, rather than a title released on a platform.
    "platform_launch_change": rf"{LAUNCH}\s+(?:of\s+)?{MODIFIERS}{PLATFORM}|"
                              rf"\b(?:new|nouvelle|nouveau|nueva|nuevo)\s+{MODIFIERS}{PLATFORM}|"
                              rf"{PLATFORM}\s+(?:launches|debuts|opens|goes live)"
                              r"(?=\s*(?:$|[.,;:]|\btoday\b|\btomorrow\b))",
    "creator_economics": near(CHANGE,
        r"\b(?:revenue[ -]shar\w*|royalt\w*|commission\w*|creator[ -]controlled.{0,25}pric\w*|"
        r"creator\w*.{0,30}(?:pay\w*|earn\w*|compensat\w*|terms)|"
        r"artist\w*.{0,30}(?:pay\w*|earn\w*|revenue|retain|net)|"
        r"remuneration|redevance\w*|partage des revenus|"
        r"reparto de ingresos|regalias|remuneracion|ingresos de los creadores)\b"),
    "monetisation_pricing": near(CHANGE,
        r"\b(?:moneti[sz]\w*|pricing|subscription\w*|paid[ -]downloads?|"
        r"per[ -]issue pric\w*|creator pric\w*|purchase model|payment model|"
        r"abonnement\w*|tarif\w*|monetisation|suscripcion\w*|monetizacion|"
        r"modelo de pago|descargas? de pago)\b"),
    "ownership_download_drm": near(CHANGE,
        r"\b(?:ownership|own comics|permanent access|DRM(?:[ -]free)?|"
        r"downloads?|offline access|propriete|telecharg\w*|acces permanent|"
        r"propiedad|descarga\w*|acceso permanente)\b"),
    "distribution_licensing_partnership": near(
        r"\b(?:partner\w*|agreement\w*|deal|alliance|partenariat\w*|accord\w*|"
        r"acuerdo\w*|alianza\w*)\b",
        r"\b(?:distribut\w*|licens\w*|licenc\w*|platform\w*|catalogue|catalog|"
        r"library|libraries|publishing|publication|plateforme\w*|plataforma\w*)\b"),
    "creator_tools": near(CHANGE,
        r"\b(?:creator\w*.{0,35}(?:tools?|dashboard|editor|upload\w*|publishing (?:tools?|features?|workflow))|"
        r"publishing tools?|comic\w*.{0,25}(?:creation|editor|authoring)|"
        r"lettering tools?|panel editor|outil\w*.{0,30}(?:creat\w*|publication)|"
        r"herramienta\w*.{0,30}(?:creador\w*|publicacion))\b"),
    "reading_technology": near(CHANGE,
        r"\b(?:responsive|adaptive|adaptative|guided[ -]view|panel[ -]by[ -]panel|"
        r"panel.{0,25}(?:layout|navigation)|reading (?:engine|feature\w*)|"
        r"screen reader|lettering.{0,25}(?:scal\w*|reflow)|"
        r"lecture adaptative|lectura adaptativa)\b"),
    "accessibility_localisation": near(CHANGE,
        r"\b(?:accessib\w*|locali[sz]\w*|translation (?:tools?|features?|support)|"
        r"language support|screen[ -]reader\w*|text[ -]to[ -]speech|"
        r"dyslex\w*|multilingual|langues|idiomas|localizacion|accesibilidad)\b"),
    "market_expansion": near(
        r"\b(?:expand\w*|enter\w*|launch\w*|market entry|expansion|"
        r"etend\w*|arrive\w*|debarqu\w*|lanc\w*|entra\w*|llega\w*|lanz\w*)\b",
        # 'GlobalComix' is a company name, not evidence of global expansion.
        r"\b(?:markets?|countries|international\w*|global(?:ly)?|Europe|European|"
        r"UK|US|Canada|Britain|English[ -]language|EU|marches?|pays|"
        r"mercados?|paises|Reino Unido|Etats[ -]Unis|Estados Unidos)\b"),
    "publishing_business": rf"(?:{LAUNCH}\s+{MODIFIERS}|\bnew\s+(?:comics?\s+)?)"
                           r"(?:publishing (?:company|house|platform)|publisher|imprint|"
                           r"maison d.edition|sello editorial)\b",
}

NEGATIVE = {
    "review_recap": r"\b(?:reviews?|recaps?|critique\w*|chronique\w*|resena\w*)\b",
    "bestseller_roundup": r"\b(?:best[ -]?sellers?|best[ -]selling|top \d+|charts?|mas vendidos|meilleures ventes)\b",
    "interview_profile": r"\b(?:interviews?|in conversation|creator (?:profiles?|spotlights?)|spotlight on|entretiens?|entrevistas?|portrait)\b",
    "crowdfunding_spotlight": r"\b(?:crowdfund\w*|kickstarter|indiegogo|funding spotlight|financement participatif|micromecenazgo)\b",
    "title_issue_promo": r"\b(?:new (?:comic|series|issue|title)|issue #?\d+|graphic novel|solicitations?|"
                        r"first look|exclusive reveal|series announcement|nouvel album|nuevo (?:numero|comic))\b",
    "preview": r"\b(?:previews?|sneak peek|teas\w*|apercu|avance)\b",
    "adaptation": r"\b(?:adaptations?|adapted|adapting|adaptacion\w*|film|movie|TV|television|trailer|Netflix|screen rights|screen deal)\b",
    "convention_promotion": r"\b(?:cosplay|convention (?:roundup|appearances?)|signings?|"
                            r"things to read|this week.s comics|new comic book day|promo\w* roundup)\b",
}

POSITIVE = {name: re.compile(pattern, re.I) for name, pattern in POSITIVE.items()}
NEGATIVE = {name: re.compile(pattern, re.I) for name, pattern in NEGATIVE.items()}
TEASER = re.compile(r"\b(?:teas\w*|mystery announcement|more (?:details|information) (?:soon|to come)|"
                    r"details (?:are )?(?:scarce|unavailable)|stay tuned|something big|coming soon)\b", re.I)


def assess_relevance(item, aliases: list[str]) -> dict:
    title = normalise(item.title)
    # Use the same bounded material available to the editor, not the rest of a
    # long page or unrelated footer/sidebar text. Keep titles as separate units.
    sentences = [normalise(s) for s in re.split(r"[.!?\n]+", item.excerpt[:3600]) if s.strip()]
    units = [title] + sentences
    watched = any(re.search(r"(?<!\w)" + re.escape(normalise(name)) + r"(?!\w)", unit)
                  for name in aliases if name.strip() for unit in units)
    positives = [name for name, pattern in POSITIVE.items() if any(pattern.search(unit) for unit in units)]
    # Named competitors can supply the company subject for concrete corporate
    # events, e.g. 'WEBTOON acquires PanelPort' or 'Madefire shuts down'. A bare
    # name still supplies no materiality, and does not assert operating status.
    names = "|".join(re.escape(normalise(name)) for name in aliases if name.strip())
    if names:
        named_events = {
            "acquisition_merger": r"\b(?:acquir\w*|acquisition\w*|merg\w*|rachat\w*|rachet\w*|fusion\w*|adquisicion\w*)\b",
            "closure_restructuring": r"\b(?:shutdown|shut(?:s|ting)? down|clos(?:es|ing|ure)|bankrupt\w*|restructur\w*|layoffs?|fermeture|cierre)\b",
            "watchlist_business_change": r"\b(?:appoint\w*.{0,30}(?:CEO|chief executive)|CEO.{0,25}(?:resigns|steps down)|"
                                        r"board restructur\w*|strategic review)\b|" +
                                        near(CHANGE, r"\b(?:terms of service|publishing terms|creator contracts)\b"),
        }
        for name, event in named_events.items():
            pattern = re.compile(near(rf"(?<!\w)(?:{names})(?!\w)", event), re.I)
            if name not in positives and any(pattern.search(unit) for unit in units):
                positives.append(name)
    title_positives = [name for name in positives if name in POSITIVE and POSITIVE[name].search(title)]
    # Only formats in the title/lead penalise ranking. A passing mention of an
    # interview or a film deep in substantive reporting is not the story's form.
    lead = title + " " + " ".join(sentences[:2])
    negatives = [name for name, pattern in NEGATIVE.items() if pattern.search(lead)]
    # A title promotion in a new market or an adaptation licensing deal alone
    # is not a platform/business development. Other specific signals can rescue it.
    for name in ("market_expansion", "distribution_licensing_partnership"):
        if name in positives and "adaptation" in negatives and not any(
                POSITIVE[name].search(unit) and not NEGATIVE["adaptation"].search(unit) for unit in units):
            positives.remove(name)
    if "title_issue_promo" in negatives and "market_expansion" in positives and not any(
            POSITIVE["market_expansion"].search(unit) and not NEGATIVE["title_issue_promo"].search(unit) for unit in units):
        positives.remove("market_expansion")
    if "crowdfunding_spotlight" in negatives and "funding" in positives and not any(
            POSITIVE["funding"].search(unit) and re.search(
                r"\b(?:funding round|series [a-f]|seed funding|venture capital|platform|company)\b", unit)
            for unit in units):
        positives.remove("funding")
    # An ordinary new title's price/download availability is not a change to
    # the platform's commercial terms. Look for explicit product/economics
    # scope when these weaker signals occur inside routine title coverage.
    if any(n in negatives for n in ("title_issue_promo", "crowdfunding_spotlight", "review_recap")):
        scope = re.compile(r"\b(?:creator[ -]controlled|creator pric\w*|revenue[ -]shar\w*|"
                           r"subscription\w*|paid[ -]download\w*|DRM|permanent|ownership model|"
                           r"pricing (?:policy|model|terms)|abonnement\w*|suscripcion\w*)\b|" +
                           near(PLATFORM, r"\b(?:changes?|revis\w*|raises?|cuts?|removes?|ends?)\b"), re.I)
        for name in ("monetisation_pricing", "ownership_download_drm"):
            if name in positives and not any(POSITIVE[name].search(unit) and scope.search(unit) for unit in units):
                positives.remove(name)
    # An uninformative teaser may name a platform launch without any details.
    teaser_only = bool(TEASER.search(title)) and not any(
        pattern.search(unit) and not TEASER.search(unit)
        for pattern in POSITIVE.values() for unit in sentences)
    material = bool(positives) and not teaser_only
    score = (8 if material else 0) + min(6, len(positives) * 2)
    score += min(4, len([p for p in title_positives if p in positives]) * 2)
    score += (2 if watched else 0) + (1 if item.source_kind == "official" else 0)
    score += {"US": 4, "UK": 3, "CA": 2, "EU": 1}.get(item.region, 0)
    score -= min(6, len(negatives) * 2)
    if not material:
        # Geography, official status and watchlist bonuses never qualify alone.
        score = min(score, 0)
    reason = ("teaser_without_substantive_detail" if teaser_only else
              "routine_without_material_development" if negatives and not material else
              "no_material_development" if not material else "")
    return {"relevance_score": score, "positive_signals": positives,
            "negative_signals": negatives, "business_materiality": material,
            "watchlist_match": watched, "exclusion_reason": reason}
